import os
import time

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI()

QUICKML_RAG_URL = os.environ.get("QUICKML_RAG_URL", "")
QUICKML_AUTH_TOKEN = os.environ.get("QUICKML_AUTH_TOKEN", "")
MIN_RELEVANCE = float(os.environ.get("MIN_RELEVANCE", "0.5"))


class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"status": "ok", "quickml_configured": bool(QUICKML_RAG_URL)}


@app.post("/api/ask")
async def ask(req: AskRequest):
    t0 = time.time()
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            QUICKML_RAG_URL,
            headers={
                "Authorization": f"Zoho-oauthtoken {QUICKML_AUTH_TOKEN}",
                "Content-Type": "application/json",
            },
            # NOTE: exact request shape (query key name, top-k, filters) must
            # be verified against a live QuickML RAG call before trusting this
            # - see docs.catalyst.zoho.com "View API" panel on the RAG model.
            json={"query": req.question},
        )
        resp.raise_for_status()
        data = resp.json()

    latency = time.time() - t0
    return {
        "passages": data.get("passages", data.get("sources", [])),
        "answer": data.get("answer", data.get("response", "")),
        "latency_seconds": round(latency, 2),
        "raw": data,  # kept during shadow-testing phase; drop once shape is confirmed
    }


app.mount("/", StaticFiles(directory="static", html=True), name="static")
