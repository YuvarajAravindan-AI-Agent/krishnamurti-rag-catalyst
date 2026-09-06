#!/usr/bin/env python3
"""
Embed the chunked corpus into a local Chroma collection.

Resumable by design. The full archive is ~121k chunks and this machine
manages roughly 6 chunks/sec, so a complete run takes hours. It records
progress after every batch, so you can stop it with Ctrl-C, close the
laptop, and start it again later without losing or repeating work.

Embeddings come from Ollama's all-minilm. Note that model truncates at
256 tokens (~1000 characters), which is why chunk.py targets 1100 —
anything much larger is silently cut off, and you would never see it in
the output, only in worse retrieval.

    python3 index.py                # run until done (resumable)
    python3 index.py --limit 5000   # do a slice now, more later
    python3 index.py --reset        # start over
"""

import argparse
import json
import sys
from pathlib import Path

import chromadb
import requests

DATA = Path(__file__).parent / "data"
CHROMA_DIR = DATA / "chroma"
COLLECTION = "krishnamurti"

OLLAMA = "http://localhost:11434"
EMBED_MODEL = "all-minilm"
BATCH = 64


def embed_batch(texts):
    r = requests.post(
        f"{OLLAMA}/api/embed",
        json={"model": EMBED_MODEL, "input": texts},
        timeout=600,
    )
    r.raise_for_status()
    return r.json()["embeddings"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="index at most N new chunks this run (0 = all)")
    ap.add_argument("--reset", action="store_true", help="drop and rebuild")
    args = ap.parse_args()

    records = json.loads((DATA / "chunks.json").read_text())

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    existing = [c.name for c in client.list_collections()]
    if args.reset and COLLECTION in existing:
        client.delete_collection(COLLECTION)
        existing.remove(COLLECTION)
    coll = (client.get_collection(COLLECTION) if COLLECTION in existing
            else client.create_collection(COLLECTION,
                                          metadata={"hnsw:space": "cosine"}))

    done = coll.count()
    if done >= len(records):
        print(f"already complete: {done:,} chunks indexed")
        return

    todo = records[done:]
    if args.limit:
        todo = todo[:args.limit]

    print(f"indexed so far: {done:,} / {len(records):,}")
    print(f"this run:       {len(todo):,} chunks")

    for start in range(0, len(todo), BATCH):
        batch = todo[start:start + BATCH]
        try:
            vecs = embed_batch([r["text"] for r in batch])
        except (requests.RequestException, KeyError) as e:
            print(f"\nstopped at {done + start:,}: {e}")
            print("progress is saved — re-run to resume")
            sys.exit(1)

        offset = done + start
        coll.add(
            ids=[f"c{offset + i:06d}" for i in range(len(batch))],
            documents=[r["text"] for r in batch],
            metadatas=[{
                "source": r["source"],
                "year": r["year"],
                "kind": r["kind"],
                "pre_dissolution": r["pre_dissolution"],
                "url": r["url"],
            } for r in batch],
            embeddings=vecs,
        )

        total = offset + len(batch)
        pct = 100 * total / len(records)
        print(f"\r  {total:,}/{len(records):,}  ({pct:.1f}%)", end="", flush=True)

    print(f"\ndone this run. collection now holds {coll.count():,} chunks")


if __name__ == "__main__":
    main()
