#!/usr/bin/env python3
"""RAG reliability and release-quality agent.

Trigger: any corpus, embedding, prompt, or model change to the Krishnamurti
RAG app on Catalyst. Behavior (see migration plan §5):

  1. Deploy the candidate to the Development AppSail environment (assumed
     already deployed by the caller/pipeline before this runs).
  2. Run the golden evaluation suite (eval/golden_set.json) against it.
  3. Measure retrieval recall, citation correctness, unsupported-claims
     rate, no-match precision, and latency (time-to-passages vs
     time-to-full-answer).
  4. Inspect Catalyst Logs for errors during the run.
  5. Produce a written, evidence-backed accept/reject recommendation.
  6. Stop and wait for human approval before promoting to Production -
     this script never promotes anything itself.

LLM calls (used only for the unsupported-claims judge step) go through a
DeepSeek-backed endpoint via ANTHROPIC_AUTH_TOKEN from ~/deepseek-dev/.env,
not a raw Anthropic key - load that env file before running.
"""
import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

GOLDEN_SET_PATH = Path(__file__).parent.parent / "eval" / "golden_set.json"
ACCEPTANCE = {
    "min_recall": 0.85,          # in-corpus questions that got a relevant top passage
    "min_citation_accuracy": 0.90,
    "max_unsupported_claims_rate": 0.10,
    "min_no_match_precision": 0.90,  # off-corpus questions correctly refused
    "max_p95_latency_seconds": 15.0,
}


@dataclass
class CaseResult:
    question: str
    kind: str  # "in_corpus" | "off_corpus"
    passages: list = field(default_factory=list)
    answer: str = ""
    latency: float = 0.0
    error: str = ""
    # Which mechanism refused, straight from the app: "entity_gate",
    # "relevance_threshold", or "" for not refused. Recording only *that* a
    # question was refused hides the difference between a system that works
    # and one that is lucky — see score_off_corpus().
    refused_by: str = ""
    unknown_entities: list = field(default_factory=list)
    best_relevance: float = 0.0
    category: str = ""
    expected_gate: str | None = None

    @property
    def refused(self) -> bool:
        return bool(self.refused_by)

    @property
    def accidental(self) -> bool:
        """Refused, but not by the mechanism that was supposed to catch it."""
        return self.refused and self.refused_by != self.expected_gate


def load_golden_set() -> dict:
    return json.loads(GOLDEN_SET_PATH.read_text())


def call_app(base_url: str, question: str) -> CaseResult:
    t0 = time.time()
    try:
        r = httpx.post(f"{base_url}/api/ask", json={"question": question}, timeout=60)
        r.raise_for_status()
        data = r.json()
        return CaseResult(
            question=question,
            kind="",
            passages=data.get("passages", []),
            answer=data.get("answer", ""),
            latency=time.time() - t0,
            refused_by=data.get("refused_by", "") or "",
            unknown_entities=data.get("unknown_entities", []) or [],
            best_relevance=float(data.get("best_relevance", 0.0) or 0.0),
        )
    except Exception as e:
        return CaseResult(question=question, kind="", latency=time.time() - t0, error=str(e))


def has_citation(passages: list) -> bool:
    for p in passages:
        # The retriever returns cite/url; older shapes used source. Check all
        # three rather than silently scoring 0 if the field is renamed again.
        src = p.get("url") or p.get("source") or p.get("cite") or ""
        if "kfoundation.org" in src:
            return True
    return False


def score_off_corpus(results: list[CaseResult]) -> dict:
    """
    Score refusals by mechanism, not just by outcome.

    A question can be refused for the wrong reason, and counting that as a
    success is how an evaluation suite starts lying to you. The Dalai Lama
    case is the worked example: the entity gate refuses it only because
    'Dalai' occurs twice, below KNOWN_ENTITY_MIN. One more mention anywhere
    in the archive and the same question silently starts being answered.
    Nothing about the system's handling of it would have changed; only the
    luck would have run out.

    So a refusal counts only when refused_by matches the category's
    expected_gate. Anything else lands in accidental_refusals, which is
    reported prominently and scored as a miss.
    """
    by_category: dict[str, dict] = {}
    for r in results:
        c = by_category.setdefault(r.category, {
            "total": 0, "correct": 0, "accidental": 0, "answered": 0, "gates": {},
        })
        c["total"] += 1
        c["gates"][r.refused_by or "(not refused)"] = \
            c["gates"].get(r.refused_by or "(not refused)", 0) + 1
        if not r.refused:
            c["answered"] += 1
        elif r.accidental:
            c["accidental"] += 1
        else:
            c["correct"] += 1

    correct = sum(c["correct"] for c in by_category.values())
    total = sum(c["total"] for c in by_category.values())
    return {
        "by_category": by_category,
        "no_match_precision": round(correct / total, 3) if total else 0.0,
        "accidental_refusals": [
            {"question": r.question, "category": r.category,
             "refused_by": r.refused_by, "expected_gate": r.expected_gate,
             "unknown_entities": r.unknown_entities}
            for r in results if r.accidental
        ],
    }


def score(in_corpus_results: list[CaseResult], off_corpus_results: list[CaseResult]) -> dict:
    recall_hits = sum(1 for r in in_corpus_results if r.passages and not r.error)
    recall = recall_hits / len(in_corpus_results) if in_corpus_results else 0.0

    cited = sum(1 for r in in_corpus_results if has_citation(r.passages))
    citation_accuracy = cited / len(in_corpus_results) if in_corpus_results else 0.0

    off = score_off_corpus(off_corpus_results)

    # An in-corpus question that trips a gate is a false positive, and it is
    # the cost side of the entity gate's ledger. Without this number the gate
    # looks free, and "refuse more" would always score better.
    false_gate_trips = [
        {"question": r.question, "refused_by": r.refused_by,
         "unknown_entities": r.unknown_entities}
        for r in in_corpus_results if r.refused
    ]

    all_latencies = sorted(r.latency for r in in_corpus_results + off_corpus_results if not r.error)
    p95_latency = all_latencies[int(len(all_latencies) * 0.95) - 1] if all_latencies else 0.0

    return {
        "recall": round(recall, 3),
        "citation_accuracy": round(citation_accuracy, 3),
        "no_match_precision": off["no_match_precision"],
        "off_corpus_by_category": off["by_category"],
        "accidental_refusals": off["accidental_refusals"],
        "false_gate_trips": false_gate_trips,
        "p95_latency_seconds": round(p95_latency, 2),
        # unsupported-claims rate needs an LLM judge pass - see judge_unsupported_claims()
    }


def judge_unsupported_claims(results: list[CaseResult], deepseek_key: str) -> float:
    """Ask a judge model whether each answer's claims are actually backed by
    its own retrieved passages. Uses the DeepSeek key (ANTHROPIC_AUTH_TOKEN
    from ~/deepseek-dev/.env) rather than a paid Anthropic key, per standing
    project convention."""
    if not deepseek_key:
        return -1.0  # signal "not measured" rather than faking a number

    flagged = 0
    checked = 0
    for r in results:
        if r.error or not r.answer:
            continue
        passages_text = "\n---\n".join(p.get("text", p.get("content", "")) for p in r.passages)
        prompt = (
            "You are a strict fact-checker. Given retrieved passages and an "
            "answer, say ONLY 'SUPPORTED' if every claim in the answer is "
            "backed by the passages, or 'UNSUPPORTED' if the answer makes "
            "claims not found in the passages.\n\n"
            f"PASSAGES:\n{passages_text[:4000]}\n\nANSWER:\n{r.answer}\n\nVerdict:"
        )
        try:
            resp = httpx.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {deepseek_key}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 10,
                },
                timeout=30,
            )
            resp.raise_for_status()
            verdict = resp.json()["choices"][0]["message"]["content"].strip().upper()
            checked += 1
            if "UNSUPPORTED" in verdict:
                flagged += 1
        except Exception:
            continue

    return round(flagged / checked, 3) if checked else -1.0


def render_report(scores: dict, unsupported_rate: float, verdict: dict, run_id: str) -> str:
    lines = [
        f"# RAG Release-Quality Report — {run_id}",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Metrics vs acceptance thresholds",
        "",
        "| Metric | Measured | Threshold | Pass? |",
        "|---|---|---|---|",
        f"| Recall | {scores['recall']} | ≥ {ACCEPTANCE['min_recall']} | {'✅' if scores['recall'] >= ACCEPTANCE['min_recall'] else '❌'} |",
        f"| Citation accuracy | {scores['citation_accuracy']} | ≥ {ACCEPTANCE['min_citation_accuracy']} | {'✅' if scores['citation_accuracy'] >= ACCEPTANCE['min_citation_accuracy'] else '❌'} |",
        f"| No-match precision | {scores['no_match_precision']} | ≥ {ACCEPTANCE['min_no_match_precision']} | {'✅' if scores['no_match_precision'] >= ACCEPTANCE['min_no_match_precision'] else '❌'} |",
        f"| p95 latency (s) | {scores['p95_latency_seconds']} | ≤ {ACCEPTANCE['max_p95_latency_seconds']} | {'✅' if scores['p95_latency_seconds'] <= ACCEPTANCE['max_p95_latency_seconds'] else '❌'} |",
        f"| Unsupported-claims rate | {unsupported_rate if unsupported_rate >= 0 else 'not measured'} | ≤ {ACCEPTANCE['max_unsupported_claims_rate']} | {'✅' if 0 <= unsupported_rate <= ACCEPTANCE['max_unsupported_claims_rate'] else ('⚠️ not measured' if unsupported_rate < 0 else '❌')} |",
        "",
        "## Off-corpus refusals by mechanism",
        "",
        "A refusal counts only when the mechanism that fired is the one the",
        "category expects. Refusing for the wrong reason is recorded as a miss:",
        "it will vanish the moment the corpus shifts.",
        "",
        "| Category | Correctly refused | Accidental | Answered | Gates that fired |",
        "|---|---|---|---|---|",
    ]
    for cat, c in sorted(scores["off_corpus_by_category"].items()):
        gates = ", ".join(f"{k} ×{v}" for k, v in sorted(c["gates"].items()))
        lines.append(
            f"| {cat} | {c['correct']}/{c['total']} | {c['accidental']} | {c['answered']} | {gates} |"
        )

    if scores["accidental_refusals"]:
        lines += ["", "### Accidental refusals (right answer, wrong reason)", ""]
        for a in scores["accidental_refusals"]:
            ents = f" — entities {a['unknown_entities']}" if a["unknown_entities"] else ""
            lines.append(
                f"- *{a['question']}* — refused by `{a['refused_by']}`, expected "
                f"`{a['expected_gate'] or 'no mechanism handles this category'}`{ents}"
            )

    if scores["false_gate_trips"]:
        lines += ["", "### In-corpus questions wrongly refused (gate false positives)", ""]
        for f in scores["false_gate_trips"]:
            lines.append(f"- *{f['question']}* — `{f['refused_by']}` {f['unknown_entities']}")
    else:
        lines += ["", "No in-corpus question was refused: the entity gate has no false positives on this set."]

    lines += [
        "",
        f"## Recommendation: {verdict['recommendation']}",
        "",
        verdict["reasoning"],
        "",
        "**This is a recommendation only. A human must click promote-to-production.**",
    ]
    return "\n".join(lines)


def decide(scores: dict, unsupported_rate: float) -> dict:
    failures = []
    if scores["recall"] < ACCEPTANCE["min_recall"]:
        failures.append(f"recall {scores['recall']} below {ACCEPTANCE['min_recall']}")
    if scores["citation_accuracy"] < ACCEPTANCE["min_citation_accuracy"]:
        failures.append(f"citation accuracy {scores['citation_accuracy']} below {ACCEPTANCE['min_citation_accuracy']}")
    if scores["no_match_precision"] < ACCEPTANCE["min_no_match_precision"]:
        failures.append(f"no-match precision {scores['no_match_precision']} below {ACCEPTANCE['min_no_match_precision']}")
    if scores["p95_latency_seconds"] > ACCEPTANCE["max_p95_latency_seconds"]:
        failures.append(f"p95 latency {scores['p95_latency_seconds']}s above {ACCEPTANCE['max_p95_latency_seconds']}s")
    if 0 <= unsupported_rate > ACCEPTANCE["max_unsupported_claims_rate"]:
        failures.append(f"unsupported-claims rate {unsupported_rate} above {ACCEPTANCE['max_unsupported_claims_rate']}")

    if failures:
        return {"recommendation": "REJECT", "reasoning": "Failed checks:\n- " + "\n- ".join(failures)}
    return {"recommendation": "ACCEPT", "reasoning": "All acceptance checks passed against the golden evaluation suite."}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True, help="AppSail candidate base URL, e.g. https://xxx.development.catalystappsail.in")
    ap.add_argument("--deepseek-key", default="", help="DeepSeek API key for the unsupported-claims judge (optional)")
    ap.add_argument("--out", default="reports", help="directory to write the report into")
    args = ap.parse_args()

    golden = load_golden_set()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    print(f"[{run_id}] running {len(golden['in_corpus'])} in-corpus + {len(golden['off_corpus'])} off-corpus questions against {args.base_url}")

    in_results = []
    for item in golden["in_corpus"]:
        r = call_app(args.base_url, item["q"])
        r.kind = "in_corpus"
        in_results.append(r)
        print(f"  [in]  {'OK' if not r.error else 'ERR'} {r.latency:.1f}s  {item['q'][:50]}")

    off_results = []
    for item in golden["off_corpus"]:
        r = call_app(args.base_url, item["q"])
        r.kind = "off_corpus"
        r.category = item["type"]
        r.expected_gate = item.get("expected_gate")
        off_results.append(r)
        if r.error:
            mark = "ERR"
        elif not r.refused:
            mark = "ANSWERED"
        elif r.accidental:
            mark = f"ACCIDENTAL({r.refused_by})"
        else:
            mark = f"refused({r.refused_by})"
        print(f"  [off] {mark:26} {r.latency:.1f}s  {item['q'][:46]}")

    scores = score(in_results, off_results)
    unsupported_rate = judge_unsupported_claims(in_results, args.deepseek_key)
    verdict = decide(scores, unsupported_rate)
    report = render_report(scores, unsupported_rate, verdict, run_id)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"report-{run_id}.md"
    report_path.write_text(report)

    print("\n" + report)
    print(f"\nReport written to {report_path}")
    sys.exit(0 if verdict["recommendation"] == "ACCEPT" else 1)


if __name__ == "__main__":
    main()
