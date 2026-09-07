#!/usr/bin/env python3
"""
Produce the JSON/markdown the demo video is rendered from.

Every number in the video comes from here, so that a wrong number in the
video means a wrong capture rather than a typo in a slide.

Two sources are possible and they are not interchangeable:

  --url <appsail>   query the live deployment over HTTP
  --index <dir>     run the same retrieval locally against the index

The local path exists because the deployment can be unreachable (quota,
redeploy, an unwired synthesis endpoint) while the numbers being shown are
about retrieval, which is deterministic given the index. Latency is the one
figure that genuinely differs between the two, so the local path omits it
rather than passing off a laptop timing as a production one.

    python3 scripts/capture_demo_assets.py --index index-full --out demo-assets
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MIN_RELEVANCE = 0.5
IN_CORPUS_Q = "what is the root of fear?"
OFF_CORPUS_Q = "what did Osho teach about meditation?"
CATEGORY_ORDER = ["random", "absent-person", "mentioned-not-taught"]


def capture_local(index_dir: Path, out: Path) -> None:
    sys.path.insert(0, str(Path(__file__).parent.parent / "appsail"))
    from entity_gate import EntityGate
    from retriever import Retriever

    r = Retriever(index_dir)
    gate = EntityGate(index_dir / "vocabulary.json")
    m = r.manifest

    def refusal_for(question: str) -> tuple[str, list[str], float]:
        unknown = gate.unknown_entities(question)
        best = r.search(question, n_results=4)[0]["relevance"]
        if unknown:
            return "entity_gate", unknown, best
        if best < MIN_RELEVANCE:
            return "relevance_threshold", [], best
        return "", [], best

    (out / "health.json").write_text(json.dumps({
        "ok": True,
        "chunks": len(r.chunks),
        "talks": m["talks"],
        "corpus_fingerprint": m["corpus_fingerprint"],
        "embedding_model": m["embedding_model"],
        "min_relevance": MIN_RELEVANCE,
    }, indent=2))

    passages = r.search(IN_CORPUS_Q, n_results=4)
    (out / "ask_in.json").write_text(json.dumps({
        "question": IN_CORPUS_Q,
        "best_relevance": passages[0]["relevance"],
        "passages": passages,
        "refused_by": "",
    }, indent=2))

    fired, unknown, best = refusal_for(OFF_CORPUS_Q)
    (out / "ask_off.json").write_text(json.dumps({
        "question": OFF_CORPUS_Q,
        "refused_by": fired,
        "unknown_entities": unknown,
        "best_relevance": best,
    }, indent=2))

    # The scoreboard. A refusal counts only when the mechanism that fired is
    # the one the category expected — scoring by outcome alone treats a lucky
    # refusal as a win, which is the failure this whole column exists to show.
    golden = json.loads((Path(__file__).parent.parent / "eval" / "golden_set.json").read_text())
    rows: dict[str, dict] = {}
    cases = []
    for case in golden["off_corpus"]:
        fired, unknown, best = refusal_for(case["q"])
        expected = case.get("expected_gate")
        row = rows.setdefault(case["type"], {"n": 0, "correct": 0, "accidental": 0, "answered": 0})
        row["n"] += 1
        if not fired:
            row["answered"] += 1
        elif fired == expected:
            row["correct"] += 1
        else:
            row["accidental"] += 1
        cases.append({
            "q": case["q"], "category": case["type"], "expected_gate": expected,
            "fired": fired or None, "best_relevance": best, "unknown_entities": unknown,
        })

    lines = ["| Category | Correct | Accidental | Answered |", "| --- | --- | --- | --- |"]
    for cat in CATEGORY_ORDER:
        if cat in rows:
            d = rows[cat]
            lines.append(f"| {cat} | {d['correct']}/{d['n']} | {d['accidental']} | {d['answered']} |")
    (out / "report.md").write_text("\n".join(lines) + "\n")
    (out / "off_corpus_detail.json").write_text(
        json.dumps({"by_category": rows, "cases": cases}, indent=2))

    total = sum(d["n"] for d in rows.values())
    correct = sum(d["correct"] for d in rows.values())
    print("\n".join(lines))
    print(f"\nno-match precision = {correct}/{total} = {correct / total:.3f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    capture_local(args.index, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
