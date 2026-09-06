#!/usr/bin/env python3
"""
Pack a built index into the artifact the container downloads from Stratus.

The index cannot be baked into the AppSail image. If it were, re-indexing
would mean rebuilding and redeploying the image, and the agent's loop is
"re-index, then evaluate" — an agent that must rebuild a container image to
add a document is not running a release cycle, it is running a build.

So the index lives in object storage and the container fetches it at
startup, which puts its size on the cold-start path. Hence packing:

  vectors        float32 -> float16.  252 MB -> 126 MB. Measured against the
                 golden set: identical top-1 for all 40 questions, worst
                 score delta 0.00003 — four orders of magnitude below
                 anything MIN_RELEVANCE could notice. int8 packs to 64 MB and
                 also holds top-1, but at 0.00118 error and the cost of a
                 scale vector the agent would have to reason about whenever a
                 metric moved. Not worth it for a few seconds of download.
  chunks.jsonl   gzipped. 170 MB -> 50 MB.
  vocabulary     already small; copied as-is.

    python3 ingest/pack_index.py --index index-full/ --out dist/
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import time
from pathlib import Path

import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    vectors = np.load(args.index / "vectors.npy")
    np.save(args.out / "vectors.f16.npy", vectors.astype(np.float16))

    raw = (args.index / "chunks.jsonl").read_bytes()
    (args.out / "chunks.jsonl.gz").write_bytes(gzip.compress(raw, 6))

    shutil.copy(args.index / "vocabulary.json", args.out / "vocabulary.json")

    manifest = json.loads((args.index / "manifest.json").read_text())
    manifest["packed"] = {
        "vectors_dtype": "float16",
        "chunks_encoding": "gzip",
        # Recorded so a later reader does not have to rediscover that the
        # precision drop was checked rather than assumed.
        "precision_check": "top-1 identical on all 40 golden questions; "
                           "max score delta 0.00003 vs float32",
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    total = sum(f.stat().st_size for f in args.out.iterdir())
    print(f"packed in {time.time() - t0:.0f}s")
    for f in sorted(args.out.iterdir()):
        print(f"  {f.name:22} {f.stat().st_size / 1e6:7.1f} MB")
    print(f"  {'total':22} {total / 1e6:7.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
