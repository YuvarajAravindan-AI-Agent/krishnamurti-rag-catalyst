#!/usr/bin/env python3
"""Run the golden set's retrieval half against the live Netcup Chroma collection.

Retrieval only — no synthesis, so this costs the box embeddings and a vector
search per question rather than twelve seconds of CPU each, and it isolates
the thing being compared.
"""
import json
import sys

import chromadb
import requests
from chromadb.config import Settings
from pathlib import Path

DATA = Path.home() / "krishnamurti-rag" / "data"
coll = chromadb.PersistentClient(
    path=str(DATA / "chroma"),
    settings=Settings(anonymized_telemetry=False),
).get_collection("krishnamurti")

gold = json.load(open("/tmp/golden_set.json"))


def emb(text):
    r = requests.post(
        "http://127.0.0.1:11434/api/embeddings",
        json={"model": "all-minilm", "prompt": text},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["embedding"]


out = {"chunks": coll.count(), "in_corpus": [], "off_corpus": []}
for key in ("in_corpus", "off_corpus"):
    for g in gold[key]:
        res = coll.query(
            query_embeddings=[emb(g["q"])],
            n_results=4,
            where={"pre_dissolution": False},
        )
        best = round(1 - res["distances"][0][0], 3) if res["distances"][0] else 0.0
        out[key].append({**g, "best": best,
                         "top_source": res["metadatas"][0][0]["source"] if res["metadatas"][0] else ""})
        print(f"  {best:.3f}  {g['q'][:60]}", file=sys.stderr)

Path("/tmp/shadow_netcup.json").write_text(json.dumps(out, indent=2))
print("written /tmp/shadow_netcup.json", file=sys.stderr)
