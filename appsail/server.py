"""
Krishnamurti RAG — AppSail service.

Retrieval runs in this process (see retriever.py); only synthesis goes out
to QuickML LLM Serving. That split is not an aesthetic choice:

  * QuickML's Knowledge Base has no ingestion API — console UI only, ten
    files per round — so an agent cannot re-index on a corpus change, and
    "re-index, then evaluate, then recommend" is the whole point of the
    release-quality agent. Retrieval had to live somewhere scriptable.
  * Synthesis had to leave the box for the opposite reason: the original's
    local Ollama run measured up to 47s to first token on hard CPU cases,
    and AppSail's request ceiling is 30s.

The response shape puts passages before the summary and labels the summary
as model-written. That ordering is the product, not a detail — the honest
claim this app can make is "here is what he said, and here is where he said
it", and a synthesised paragraph presented first would quietly replace that
with "here is what a model says he meant".
"""

from __future__ import annotations

import hmac
import os
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import index_store
from entity_gate import EntityGate
from retriever import Retriever

HERE = Path(__file__).parent
INDEX_DIR = Path(os.environ.get("INDEX_DIR", HERE / "index"))

# The named-entity gate is switchable so the agent can measure what it is
# worth. Its whole justification is a number — no-match precision with it
# versus without — and a gate you cannot turn off is a gate you cannot
# evaluate.
ENTITY_GATE = os.environ.get("ENTITY_GATE", "1") not in ("0", "false", "")

# Carried over from the Netcup original unchanged, and that is defensible
# only because the embedder is the same model in the same cosine space —
# measured, not assumed, by ingest/verify_embeddings.py (mean agreement
# 0.999998 against the live Chroma vectors). If the embedding model ever
# changes, this number is meaningless until it is re-derived.
MIN_RELEVANCE = float(os.environ.get("MIN_RELEVANCE", "0.5"))
N_PASSAGES = int(os.environ.get("N_PASSAGES", "4"))
MAX_QUESTION_CHARS = 500

# Set in the AppSail console — custom-runtime env vars cannot be supplied
# through app-config.json or the CLI (plan §3.2).
# Guards the re-index endpoint. This is a secret we mint, not a Zoho
# credential — it authorises "may push an index", nothing else, and it is
# what the agent holds. Unset means the endpoint is closed, so a container
# that is missing its config refuses writes instead of accepting anonymous
# ones.
INDEX_PUSH_TOKEN = os.environ.get("INDEX_PUSH_TOKEN", "")

QUICKML_LLM_URL = os.environ.get("QUICKML_LLM_URL", "")
QUICKML_AUTH_TOKEN = os.environ.get("QUICKML_AUTH_TOKEN", "")
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "20"))

SYSTEM_PROMPT = (
    "You are summarising passages from J. Krishnamurti's recorded talks. "
    "Use only the numbered passages given. Do not add teachings, examples, "
    "or conclusions that are not in them. If the passages do not answer the "
    "question, say so plainly. Never write in his voice or invent quotations."
)

app = FastAPI(title="Krishnamurti RAG (Catalyst)")

_retriever: Retriever | None = None
_gate: EntityGate | None = None

# Set when startup could not obtain an index. Non-empty means /api/ask is
# unavailable but the container is alive and can be repaired through
# /admin/index — see warm().
_degraded: str = ""


def retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever(INDEX_DIR)
    return _retriever


def gate() -> EntityGate | None:
    global _gate
    if not ENTITY_GATE:
        return None
    if _gate is None:
        _gate = EntityGate(INDEX_DIR / "vocabulary.json")
    return _gate


@app.on_event("startup")
def warm() -> None:
    # Load the index and run one encode at boot. Deferring it to the first
    # request would spend that cost inside AppSail's 30s request budget,
    # where it is a user-visible timeout rather than a slower cold start.
    # Startup must survive having no index at all. On a first deploy the
    # bucket is empty, and the only route that can fill it is /admin/index
    # on this very container — so a startup that exits on a missing index
    # deadlocks the bootstrap: no index means no app, and no app means no
    # way to push one. Degraded-but-listening is the only state that can
    # dig itself out.
    global _degraded
    try:
        print(f"index fetch: {index_store.ensure_index(INDEX_DIR)}")
    except Exception as e:
        _degraded = f"{type(e).__name__}: {e}"
        print(f"NO INDEX — serving /health and /admin only: {_degraded}")
        return

    r = retriever()
    r.embedder.encode_one("warm")
    g = gate()
    print(f"index ready: {r.manifest['chunks']:,} chunks from "
          f"{r.manifest['talks']:,} talks (corpus {r.manifest['corpus_fingerprint']})")
    print(f"entity gate: {'on, ' + format(len(g.capitalised), ',') + ' known names' if g else 'off'}")


class Ask(BaseModel):
    question: str
    include_early: bool = False


def build_prompt(question: str, passages: list[dict]) -> str:
    blocks = "\n\n".join(
        f"[{i + 1}] {p['cite']}\n{p['text']}" for i, p in enumerate(passages)
    )
    return f"{blocks}\n\nQuestion: {question}"


async def synthesise(question: str, passages: list[dict]) -> tuple[str, str | None]:
    """
    Returns (answer, error). An empty answer with no error means synthesis is
    not configured — the app still serves passages, which is the part that is
    actually load-bearing.
    """
    if not (QUICKML_LLM_URL and QUICKML_AUTH_TOKEN):
        return "", None

    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(question, passages)},
        ],
        "temperature": 0.2,
    }
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            r = await client.post(
                QUICKML_LLM_URL,
                headers={"Authorization": f"Zoho-oauthtoken {QUICKML_AUTH_TOKEN}"},
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        # Synthesis failing must not take the passages down with it.
        return "", f"{type(e).__name__}: {e}"

    # NOTE: QuickML's LLM Serving response shape is not documented and has
    # not yet been observed against a live endpoint. Until it has been, this
    # walks the plausible shapes and falls back to returning the raw body
    # rather than guessing — a wrong .get() chain here would surface as an
    # empty summary that looks like a model refusal (plan §3.4).
    for path in (
        ("choices", 0, "message", "content"),
        ("data", "response"),
        ("output",),
        ("response",),
    ):
        cur = data
        try:
            for key in path:
                cur = cur[key]
            if isinstance(cur, str) and cur.strip():
                return cur.strip(), None
        except (KeyError, IndexError, TypeError):
            continue
    return "", f"unrecognised response shape: {str(data)[:300]}"


@app.get("/health")
def health() -> dict:
    if _degraded:
        return {"ok": False, "degraded": True, "error": _degraded,
                "index_push_configured": bool(INDEX_PUSH_TOKEN)}
    try:
        r = retriever()
        return {
            "ok": True,
            "chunks": r.manifest["chunks"],
            "talks": r.manifest["talks"],
            "corpus_fingerprint": r.manifest["corpus_fingerprint"],
            "embedding_model": r.manifest["embedding_model"],
            "min_relevance": MIN_RELEVANCE,
            "synthesis_configured": bool(QUICKML_LLM_URL and QUICKML_AUTH_TOKEN),
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@app.post("/api/ask")
async def ask(body: Ask) -> dict:
    if _degraded:
        raise HTTPException(503, f"index unavailable: {_degraded}")
    t0 = time.time()
    question = body.question.strip()[:MAX_QUESTION_CHARS]
    if not question:
        return {"error": "empty question"}

    # Before retrieval, not after: if the question asks what someone absent
    # from the corpus said, no passage can answer it, however well it scores.
    g = gate()
    refusal = g.refusal(question) if g else None
    if refusal:
        return {
            "no_match": True,
            "refused_by": "entity_gate",
            "unknown_entities": g.unknown_entities(question),
            "question": question,
            "best_relevance": 0.0,
            "passages": [],
            "answer": refusal,
            "latency_seconds": round(time.time() - t0, 2),
        }

    passages = retriever().search(
        question, n_results=N_PASSAGES, include_early=body.include_early
    )
    best = passages[0]["relevance"] if passages else 0.0

    if not passages or best < MIN_RELEVANCE:
        # Say so plainly and do not synthesise. Handing weak passages to the
        # model invites it to invent a teaching to fit the question — which
        # is precisely what the off-corpus half of the golden set tests for.
        return {
            "no_match": True,
            "refused_by": "relevance_threshold",
            "question": question,
            "best_relevance": best,
            "passages": passages,
            "answer": "",
            "latency_seconds": round(time.time() - t0, 2),
        }

    answer, error = await synthesise(question, passages)
    return {
        "no_match": False,
        "question": question,
        "best_relevance": best,
        "passages": passages,
        "answer": answer,
        "synthesis_error": error,
        "latency_seconds": round(time.time() - t0, 2),
    }


def _authorise(key: str, token: str) -> None:
    """
    Guard shared by every index-write route.

    These routes exist because the container is the only place with Catalyst
    credentials: the SDK derives them from headers Catalyst injects into the
    inbound request. A laptop cannot write to Stratus without an OAuth
    client; the running app can, without one.

    Note what none of them do: swap the live index. They write to object
    storage and stop. Promotion is a separate, human-approved step — a
    re-index that cut over in the same call would let the agent ship an
    unevaluated corpus to production, the exact failure the release gate
    exists to prevent.
    """
    if not INDEX_PUSH_TOKEN:
        raise HTTPException(503, "index push is not configured on this instance")
    # compare_digest rather than ==: token comparison should not leak its
    # answer through timing, cheap as that attack is here.
    if not hmac.compare_digest(token, INDEX_PUSH_TOKEN):
        raise HTTPException(403, "bad index push token")
    if key not in index_store.OBJECTS:
        raise HTTPException(400, f"unexpected object {key!r}; expected one of {index_store.OBJECTS}")


def _sdk_call(fn, *args, **kwargs) -> dict:
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        # Surface the SDK's own error text: failures here are almost always
        # the credential-header question, and a generic 500 would hide the
        # one detail worth reading.
        raise HTTPException(500, f"{type(e).__name__}: {e}") from e


@app.put("/admin/index/{key}")
async def push_index_object(
    key: str, request: Request, x_index_token: str = Header(default="")
) -> dict:
    """Single-shot write. Only safe for the small objects — see below."""
    _authorise(key, x_index_token)
    body = await request.body()
    if not body:
        raise HTTPException(400, "empty body")
    return _sdk_call(index_store.put_object, request, key, body)


@app.post("/admin/index/{key}/initiate")
async def initiate_index_upload(
    key: str, request: Request, x_index_token: str = Header(default="")
) -> dict:
    """
    Begin a multipart upload.

    The large objects cannot go up in one request: vectors.f16.npy is
    126 MB, and AppSail's request ceiling is 30 seconds, so on any ordinary
    uplink a single-shot PUT is killed mid-body. Parts sized to fit inside
    that budget are the only shape that works.

    The upload id Stratus returns is held server-side, which is what makes
    this safe across instances — successive parts may well be answered by
    different containers, and none of them need to share local state.
    """
    _authorise(key, x_index_token)
    return _sdk_call(index_store.initiate_multipart, request, key)


@app.put("/admin/index/{key}/part/{part_number}")
async def upload_index_part(
    key: str,
    part_number: int,
    upload_id: str,
    request: Request,
    x_index_token: str = Header(default=""),
) -> dict:
    _authorise(key, x_index_token)
    body = await request.body()
    if not body:
        raise HTTPException(400, "empty part body")
    return _sdk_call(index_store.upload_part, request, key, upload_id, part_number, body)


@app.post("/admin/index/{key}/complete")
async def complete_index_upload(
    key: str,
    upload_id: str,
    request: Request,
    x_index_token: str = Header(default=""),
) -> dict:
    _authorise(key, x_index_token)
    return _sdk_call(index_store.complete_multipart, request, key, upload_id)


app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(HERE / "static" / "index.html")
