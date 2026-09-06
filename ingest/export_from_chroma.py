#!/usr/bin/env python3
"""
Export the Netcup box's Chroma collection into the index format AppSail serves.

Runs *on jk-box*, against the live collection. Re-embedding the full archive
would take about nine hours on the migration laptop and would produce
vectors we have already shown to be the same ones — verify_embeddings.py
measured 0.999998 mean cosine agreement between the ONNX embedder and these
exact vectors. So the honest, cheap move is to carry them over rather than
recompute them and pretend that was a validation step.

Two things this does that a naive dump would not:

  * L2-normalises. Ollama returns unnormalised vectors and Chroma stored
    them that way, applying cosine distance at query time. The AppSail
    retriever scores with a plain dot product, which is only cosine if the
    vectors are unit length. Skipping this would not error — it would just
    silently rank by magnitude as much as by direction.
  * Carries pre_dissolution through. It gates the Theosophical material
    Krishnamurti repudiated, and losing it would quietly start serving
    passages the original deliberately withheld.

    ./.venv/bin/python export_from_chroma.py --out /tmp/index-full
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import chromadb
import numpy as np
from chromadb.config import Settings

BATCH = 5000


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chroma", type=Path,
                    default=Path.home() / "krishnamurti-rag" / "data" / "chroma")
    ap.add_argument("--collection", default="krishnamurti")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    coll = chromadb.PersistentClient(
        path=str(args.chroma),
        settings=Settings(anonymized_telemetry=False),
    ).get_collection(args.collection)

    total = coll.count()
    print(f"collection holds {total:,} chunks")

    args.out.mkdir(parents=True, exist_ok=True)
    vectors: np.ndarray | None = None
    written = 0
    sources: set[str] = set()
    t0 = time.time()

    with (args.out / "chunks.jsonl").open("w") as fh:
        for offset in range(0, total, BATCH):
            res = coll.get(
                limit=BATCH,
                offset=offset,
                include=["documents", "embeddings", "metadatas"],
            )
            emb = np.asarray(res["embeddings"], dtype=np.float32)
            if vectors is None:
                vectors = np.zeros((total, emb.shape[1]), dtype=np.float32)

            emb /= np.clip(np.linalg.norm(emb, axis=1, keepdims=True), 1e-12, None)
            vectors[offset:offset + len(emb)] = emb

            for doc, meta in zip(res["documents"], res["metadatas"]):
                fh.write(json.dumps({
                    "text": doc,
                    "source": meta["source"],
                    "year": meta["year"],
                    "kind": meta["kind"],
                    "pre_dissolution": bool(meta["pre_dissolution"]),
                    "url": meta.get("url") or "",
                }, ensure_ascii=False) + "\n")
                sources.add(str(meta["source"]))
            written += len(res["documents"])
            print(f"\r  {written:,}/{total:,} ({100 * written / total:.1f}%)",
                  end="", flush=True)

    print(f"\n  exported in {time.time() - t0:.0f}s")

    if written != total or vectors is None or len(vectors) != total:
        # An index quietly missing chunks still answers plausibly, with real
        # citations, and is close to undetectable downstream. Fail loudly.
        print(f"ERROR: expected {total:,} chunks, wrote {written:,}")
        return 1

    np.save(args.out / "vectors.npy", vectors)

    manifest = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "talks": len(sources),
        "chunks": total,
        "dimensions": int(vectors.shape[1]),
        "embedding_model": "all-MiniLM-L6-v2 (ollama all-minilm, carried over)",
        "corpus_fingerprint": hashlib.sha256(
            "".join(sorted(sources)).encode()
        ).hexdigest()[:16],
        "provenance": "exported from the Netcup Chroma collection, L2-normalised",
        "chunker": {"target_chars": 900, "overlap_chars": 150, "min_chunk": 250},
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
