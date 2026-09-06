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

import os
import time
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from retriever import Retriever

HERE = Path(__file__).parent
INDEX_DIR = Path(os.environ.get("INDEX_DIR", HERE / "index"))

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


def retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever(INDEX_DIR)
    return _retriever


@app.on_event("startup")
def warm() -> None:
    # Load the index and run one encode at boot. Deferring it to the first
    # request would spend that cost inside AppSail's 30s request budget,
    # where it is a user-visible timeout rather than a slower cold start.
    r = retriever()
    r.embedder.encode_one("warm")
    print(f"index ready: {r.manifest['chunks']:,} chunks from "
          f"{r.manifest['talks']:,} talks (corpus {r.manifest['corpus_fingerprint']})")


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
    t0 = time.time()
    question = body.question.strip()[:MAX_QUESTION_CHARS]
    if not question:
        return {"error": "empty question"}

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


app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(HERE / "static" / "index.html")
