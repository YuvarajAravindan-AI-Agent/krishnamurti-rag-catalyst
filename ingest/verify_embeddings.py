#!/usr/bin/env python3
"""
Prove the ONNX embedder reproduces the vectors the Netcup box retrieves with.

The whole reason MIN_RELEVANCE = 0.5 survives this migration untouched is
the claim "it's the same model". That claim is worth exactly nothing until
it's measured, so this compares ONNX output against a sample of real
embeddings pulled straight out of the live Chroma collection.

What matters is not that the vectors are bit-identical (they won't be —
different runtimes, different float paths) but that the *cosine similarity*
between old and new vectors for the same text is high enough that a 0.5
threshold lands in the same place. A drift of 0.001 is noise; a drift of
0.05 would mean the threshold has to be recalibrated after all.

    python3 ingest/verify_embeddings.py --sample path/to/embed_sample.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "appsail"))
from embedder import Embedder  # noqa: E402

# Below this, the retrieval threshold carried over from the original is no
# longer defensible and MIN_RELEVANCE has to be re-derived on new vectors.
MIN_ACCEPTABLE_AGREEMENT = 0.99


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True,
                    help="JSON list of {text, embedding} from the live Chroma collection")
    ap.add_argument("--limit", type=int, default=300)
    args = ap.parse_args()

    pairs = json.loads(Path(args.sample).read_text())[:args.limit]
    texts = [p["text"] for p in pairs]
    reference = np.array([p["embedding"] for p in pairs], dtype=np.float32)

    # Ollama returns unnormalised vectors; normalise both sides so we are
    # comparing direction, which is all cosine retrieval ever uses.
    reference /= np.clip(np.linalg.norm(reference, axis=1, keepdims=True), 1e-12, None)

    print(f"comparing {len(texts)} chunks against live Chroma vectors…")
    ours = Embedder().encode(texts)

    if ours.shape != reference.shape:
        print(f"FAIL: shape mismatch {ours.shape} vs {reference.shape}")
        return 1

    agreement = (ours * reference).sum(axis=1)
    worst_idx = int(np.argmin(agreement))

    print()
    print(f"  dimensions:      {ours.shape[1]}")
    print(f"  mean agreement:  {agreement.mean():.6f}")
    print(f"  min agreement:   {agreement.min():.6f}")
    print(f"  p1 agreement:    {np.percentile(agreement, 1):.6f}")
    print(f"  below 0.99:      {int((agreement < 0.99).sum())} / {len(agreement)}")
    print()
    print(f"  worst chunk ({agreement[worst_idx]:.6f}):")
    print(f"    {texts[worst_idx][:160]!r}")
    print()

    if agreement.min() >= MIN_ACCEPTABLE_AGREEMENT:
        print(f"PASS — vectors agree to >= {MIN_ACCEPTABLE_AGREEMENT}.")
        print("MIN_RELEVANCE = 0.5 carries over without recalibration.")
        return 0

    print(f"FAIL — agreement dips below {MIN_ACCEPTABLE_AGREEMENT}.")
    print("The threshold must be re-derived against the new vectors before")
    print("this index is trusted; do not assume 0.5 still separates cleanly.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
