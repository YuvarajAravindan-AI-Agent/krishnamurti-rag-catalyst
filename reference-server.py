#!/usr/bin/env python3
"""
Web front end for the Krishnamurti corpus: ask a question over a WebSocket,
get his actual words back immediately, and a summary of them shortly after.

Two things drive the design, and both are deliberate.

First, the passages go out before the model is even called. Retrieval takes
about 30 ms; generation takes seconds (see the handoff, 4.4b — prompt
processing on this box runs at 44-117 tok/s, so a large context costs real
time before a single token appears). Sending his words first means the page is
useful in under a second instead of showing a spinner, and it puts the source
above the summary, which is the right order for this material anyway.

Second, the model summarises the passages and nothing else. It does not speak
as Krishnamurti. He spent sixty years refusing that role -- no authority, no
method, "truth is a pathless land" -- and a bot in his voice would quietly
invent teachings he never gave. The passages are checkable; a synthesis is not.
So the synthesis is labelled as such and is explicitly forbidden first person.
"""

import asyncio
import json
import time
from collections import defaultdict, deque
from pathlib import Path

import chromadb
import httpx
from chromadb.config import Settings as ChromaSettings
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).parent
DATA = HERE / "data"
CHROMA_DIR = DATA / "chroma"
COLLECTION = "krishnamurti"

OLLAMA = "http://127.0.0.1:11434"
EMBED_MODEL = "all-minilm"
CHAT_MODEL = "qwen3:1.7b"

# Three, not eight. Prefill time is close to linear in context length, and it
# dominates time-to-first-token on CPU: ~7 s at 800 tokens against ~18 s at
# 2100. Retrieving more actively makes the product worse here.
N_PASSAGES = 3

# Long enough to be useful, short enough that the wait stays bounded.
MAX_TOKENS = 320

# Vector search has no concept of "no match" -- it always returns the nearest
# N vectors, so a question about something absent from the corpus still gets
# passages, just bad ones. Left unchecked the model then tries to answer from
# them, which is the fabrication mode this whole project exists to avoid.
#
# Measured with calibrate.py over 8 real and 8 off-corpus questions:
#   in-corpus  top scores: 0.682 - 0.812
#   off-corpus top scores: 0.168 - 0.362
# The populations separate cleanly, so 0.5 sits in open space with margin on
# both sides. Re-run calibrate.py if the corpus or embedding model changes.
MIN_RELEVANCE = 0.5

# --- limits ---------------------------------------------------------------
# One question costs roughly 12 s across all four cores. Two at once do not
# run at half speed, they thrash: the box has no spare capacity to interleave
# them. So generation is serialised globally and the queue is kept short --
# better to refuse quickly than to accept work and answer it in two minutes.
MAX_CONCURRENT = 1
MAX_QUEUED = 3

# Per-IP, over a rolling window. Generous for a human reading the answers,
# useless for anyone trying to keep all four cores busy.
RATE_MAX = 6
RATE_WINDOW = 60.0

MAX_QUESTION_CHARS = 400

_gen_slot = asyncio.Semaphore(MAX_CONCURRENT)
_queued = 0
_hits: dict[str, deque] = defaultdict(deque)


def client_ip(sock: WebSocket) -> str:
    """Real client address. Caddy sets X-Forwarded-For; we are always behind
    it, so the first entry is the origin."""
    xff = sock.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return sock.client.host if sock.client else "unknown"


def rate_limited(ip: str) -> bool:
    now = time.monotonic()
    q = _hits[ip]
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    if len(q) >= RATE_MAX:
        return True
    q.append(now)
    # Keep the dict from growing without bound on a long-lived process.
    if len(_hits) > 4096:
        for k in [k for k, v in _hits.items() if not v][:2048]:
            _hits.pop(k, None)
    return False

SYSTEM_PROMPT = """You are a careful research assistant working with a corpus \
of talks by J. Krishnamurti.

You will be given several passages from those talks and a question.

Rules, all of them absolute:
- Summarise only what the passages actually say. Add nothing from outside them.
- Never write as Krishnamurti. Never use "I" to mean him. Refer to him in the \
third person.
- Never invent, extend, or smooth over a teaching. If the passages do not \
address the question, say plainly that they do not.
- Do not offer advice, method, or instruction in his name. He refused to give \
any, and that refusal is the substance of his teaching.
- Be brief. Three or four sentences."""

app = FastAPI(title="krishnamurti-rag")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

_client = None
_coll = None


def _clear_chroma_cache():
    """Drop Chroma's process-wide System cache.

    Constructing a second PersistentClient for the same path returns a new
    wrapper around the *same* cached System, so it keeps the stale segment
    readers and reopening alone does not help. This is the only way to
    genuinely start over inside one process.
    """
    try:
        from chromadb.api.shared_system_client import SharedSystemClient
    except ImportError:  # older layout
        from chromadb.api.client import SharedSystemClient
    SharedSystemClient.clear_system_cache()


def _collection(fresh: bool = False):
    """Chroma's client is sync and not cheap to build, so keep one.

    But a cached handle goes stale if another process writes the collection --
    which happens whenever index.py runs against a live app. The symptom is an
    opaque "Internal error: Error finding id" on query, while a brand new
    reader in a separate process works perfectly. Callers retry once with
    fresh=True.
    """
    global _client, _coll
    if fresh:
        _coll = None
        _client = None
        _clear_chroma_cache()
    if _coll is None:
        # Chroma enables anonymised PostHog telemetry by default -- it opens
        # an outbound HTTPS connection and reports usage. Nothing should leave
        # this box; the whole point is that it is self-contained.
        _client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        _coll = _client.get_collection(COLLECTION)
    return _coll


async def embed(text: str, client: httpx.AsyncClient) -> list[float]:
    r = await client.post(
        f"{OLLAMA}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["embedding"]


def search(vec: list[float], include_early: bool):
    """Mirrors ask.py, including the pre-1929 exclusion."""
    kwargs = {"query_embeddings": [vec], "n_results": N_PASSAGES}
    if not include_early:
        # The Theosophical period he repudiated when he dissolved the Order
        # of the Star. Excluded unless asked for.
        kwargs["where"] = {"pre_dissolution": False}
    try:
        res = _collection().query(**kwargs)
    except Exception:
        # Handle may be stale against a collection written by another
        # process; reopen once before giving up.
        res = _collection(fresh=True).query(**kwargs)
    out = []
    for doc, meta, dist in zip(
        res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        cite = meta["source"]
        # Decade sections ("1970s") already carry their date; only a named
        # work needs the year appended.
        if meta["year"] != -1 and str(meta["year"]) not in cite:
            cite += f" ({meta['year']})"
        out.append({
            "text": doc,
            "cite": cite,
            "url": meta.get("url") or "",
            "year": meta["year"],
            "relevance": round(1 - dist, 3),
        })
    return out


def build_prompt(question: str, passages: list[dict]) -> str:
    blocks = "\n\n".join(
        f"[{i + 1}] {p['cite']}\n{p['text']}" for i, p in enumerate(passages)
    )
    return f"{blocks}\n\nQuestion: {question}"


@app.get("/")
async def index():
    return FileResponse(HERE / "static" / "index.html")


@app.get("/healthz")
async def healthz():
    try:
        return {"ok": True, "chunks": _collection().count()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    async with httpx.AsyncClient() as client:
        try:
            while True:
                raw = await sock.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                question = (msg.get("question") or "").strip()
                if not question:
                    continue
                if len(question) > MAX_QUESTION_CHARS:
                    question = question[:MAX_QUESTION_CHARS]
                include_early = bool(msg.get("include_early"))

                if rate_limited(client_ip(sock)):
                    await sock.send_json({
                        "type": "busy",
                        "message": (
                            f"That's {RATE_MAX} questions in a minute. "
                            "Give it a moment — each answer costs this small "
                            "box about twelve seconds of full CPU."
                        ),
                    })
                    await sock.send_json({"type": "done"})
                    continue

                # --- his words first, before the model is touched ---
                try:
                    vec = await embed(question, client)
                    passages = await asyncio.to_thread(
                        search, vec, include_early
                    )
                except Exception as e:
                    await sock.send_json({"type": "error", "message": str(e)})
                    continue

                best = passages[0]["relevance"] if passages else 0.0
                if not passages or best < MIN_RELEVANCE:
                    # Say so plainly and do not synthesise. Handing weak
                    # passages to the model invites it to invent a teaching
                    # to fit the question.
                    await sock.send_json({
                        "type": "no_match",
                        "question": question,
                        "best": best,
                        "passages": passages,
                    })
                    await sock.send_json({"type": "done"})
                    continue

                await sock.send_json({
                    "type": "passages",
                    "question": question,
                    "passages": passages,
                })

                # --- then the summary, streamed ---
                # Passages are already delivered, so a queue here costs the
                # user nothing they can see except a later summary.
                global _queued
                if _queued >= MAX_QUEUED:
                    await sock.send_json({
                        "type": "busy",
                        "message": ("The box is answering other questions. "
                                    "The passages above are the substance; "
                                    "try again shortly for a summary."),
                    })
                    await sock.send_json({"type": "done"})
                    continue

                _queued += 1
                try:
                    async with _gen_slot:
                        await _generate(sock, client, question, passages)
                finally:
                    _queued -= 1

                await sock.send_json({"type": "done"})

        except WebSocketDisconnect:
            pass


async def _generate(sock: WebSocket, client: httpx.AsyncClient,
                    question: str, passages: list[dict]) -> None:
    """Stream the summary. Split out so the semaphore's scope is obvious.

    Raises on client disconnect, deliberately: unwinding out of the httpx
    stream context closes the connection to Ollama, and that is what actually
    stops it generating an answer nobody will read.
    """
    await sock.send_json({"type": "synthesis_start"})
    payload = {
        "model": CHAT_MODEL,
        "system": SYSTEM_PROMPT,
        "prompt": build_prompt(question, passages),
        # Non-negotiable: with thinking on, qwen3 spends the whole token
        # budget reasoning and never reaches an answer.
        "think": False,
        "stream": True,
        "options": {
            "num_predict": MAX_TOKENS,
            "temperature": 0.3,
        },
    }
    try:
        async with client.stream(
            "POST", f"{OLLAMA}/api/generate", json=payload, timeout=None,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                tok = chunk.get("response", "")
                if tok:
                    await sock.send_json({"type": "token", "text": tok})
                if chunk.get("done"):
                    break
    except (WebSocketDisconnect, RuntimeError):
        raise
    except Exception as e:
        await sock.send_json({"type": "error", "message": str(e)})
