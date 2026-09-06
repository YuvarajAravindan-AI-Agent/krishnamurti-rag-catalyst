#!/usr/bin/env python3
"""
Build the retrieval index the AppSail container serves from.

This is the step QuickML's Knowledge Base could not give us. Its ingestion
is console-only — no API, ten files per round — which means an agent cannot
re-index on a corpus change, and "re-index then evaluate" is the entire
premise of the release-quality agent. So retrieval moved into the app and
ingestion became this: one command, no clicking, exit code you can branch on.

Output is a directory holding
    vectors.npy   float32 (n, 384), L2-normalised — cosine is a dot product
    chunks.jsonl  one record per row of vectors.npy, same order
    manifest.json corpus fingerprint, model, chunker settings, counts

The manifest exists so the agent can tell *why* an index changed. A drop in
recall means something different if the chunker settings moved than if only
the document set did.

    python3 ingest/build_index.py --transcripts data/transcripts.json \\
        --subset data/demo_subset --out index/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "appsail"))

from chunk import MIN_CHUNK, OVERLAP_CHARS, TARGET_CHARS, YEAR, chunk_text, strip_artifacts  # noqa: E402
from embedder import Embedder  # noqa: E402

MODEL_NAME = "all-MiniLM-L6-v2 (onnx)"


def subset_ids(subset_dir: Path) -> set[str]:
    """Talk ids from the staged filenames — '68193-public-talk-2-…' -> '68193'."""
    ids = set()
    for f in subset_dir.glob("*.txt"):
        m = re.match(r"(\d+)-", f.name)
        if m:
            ids.add(m.group(1))
    return ids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcripts", required=True, type=Path)
    ap.add_argument("--subset", type=Path, default=None,
                    help="directory of staged .txt files; restricts the index to those talks")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--batch-size", type=int, default=32)
    args = ap.parse_args()

    talks = json.loads(args.transcripts.read_text())
    if args.subset:
        keep = subset_ids(args.subset)
        talks = [t for t in talks if str(t["id"]) in keep]
        if len(talks) != len(keep):
            # Loud, not a warning buried in a log: an index quietly missing
            # documents produces plausible answers with real citations and
            # is close to undetectable downstream.
            print(f"ERROR: subset lists {len(keep)} talks but only {len(talks)} matched "
                  f"{args.transcripts}", file=sys.stderr)
            return 1

    print(f"talks:  {len(talks):,}")

    records = []
    for t in talks:
        m = YEAR.search(t["title"])
        year = int(m.group(1)) if m else -1
        for c in chunk_text(strip_artifacts(t["text"])):
            records.append({
                "text": c,
                "source": t["title"],
                "year": year,
                "kind": "transcript",
                # Transcripts are all from the teaching period; the
                # pre-dissolution Theosophical material he repudiated only
                # ever entered the corpus through the Wikiquote source.
                "pre_dissolution": False,
                "url": t["link"],
            })

    if not records:
        print("ERROR: no chunks produced — refusing to write an empty index", file=sys.stderr)
        return 1

    print(f"chunks: {len(records):,}")
    print(f"chars:  {sum(len(r['text']) for r in records):,}")

    embedder = Embedder()
    t0 = time.time()
    vectors = np.zeros((len(records), 384), dtype=np.float32)
    for start in range(0, len(records), args.batch_size):
        batch = records[start:start + args.batch_size]
        vectors[start:start + len(batch)] = embedder.encode(
            [r["text"] for r in batch], batch_size=args.batch_size
        )
        done = start + len(batch)
        print(f"\r  embedding {done:,}/{len(records):,} "
              f"({100 * done / len(records):.1f}%)", end="", flush=True)
    elapsed = time.time() - t0
    print(f"\n  done in {elapsed:.1f}s ({len(records) / elapsed:.0f} chunks/sec)")

    args.out.mkdir(parents=True, exist_ok=True)
    np.save(args.out / "vectors.npy", vectors)
    with (args.out / "chunks.jsonl").open("w") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    fingerprint = hashlib.sha256(
        "".join(sorted(str(t["id"]) for t in talks)).encode()
    ).hexdigest()[:16]

    manifest = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "talks": len(talks),
        "chunks": len(records),
        "dimensions": int(vectors.shape[1]),
        "embedding_model": MODEL_NAME,
        "corpus_fingerprint": fingerprint,
        "chunker": {
            "target_chars": TARGET_CHARS,
            "overlap_chars": OVERLAP_CHARS,
            "min_chunk": MIN_CHUNK,
        },
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"\nwritten to {args.out}/")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
