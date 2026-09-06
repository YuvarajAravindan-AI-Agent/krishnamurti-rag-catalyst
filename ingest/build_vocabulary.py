#!/usr/bin/env python3
"""
Record which proper nouns the corpus actually contains.

Feeds appsail/entity_gate.py. Kept as a separate step from build_index.py so
it can be regenerated against an index that was exported rather than built
(the full archive's vectors came straight out of the Netcup Chroma
collection — see export_from_chroma.py).

    python3 ingest/build_vocabulary.py --index index-full/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "appsail"))
from entity_gate import build_vocabulary  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True, type=Path)
    ap.add_argument("--min-count", type=int, default=2,
                    help="drop tokens rarer than this to keep the file small")
    args = ap.parse_args()

    texts = []
    with (args.index / "chunks.jsonl").open() as fh:
        for line in fh:
            texts.append(json.loads(line)["text"])
    print(f"reading {len(texts):,} chunks…")

    vocab = build_vocabulary(texts)
    for key in ("capitalised", "lowercase"):
        before = len(vocab[key])
        vocab[key] = {k: v for k, v in vocab[key].items() if v >= args.min_count}
        print(f"  {key}: {before:,} -> {len(vocab[key]):,} tokens "
              f"(>= {args.min_count} occurrences)")

    out = args.index / "vocabulary.json"
    out.write_text(json.dumps(vocab))
    print(f"written {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
