#!/usr/bin/env python3
"""Pick a representative ~80-talk subset from data/documents/ for demo-scale
QuickML Knowledge Base ingestion (full 3,014-doc ingestion is a follow-up
batch job - console UI caps uploads at 10 files/round, no bulk API exists).

Selection: a few talks per golden-set theme (matched by keyword in the talk
text) plus a spread across decades, so the demo corpus isn't lopsided.
"""
import json
import random
import re
import shutil
from pathlib import Path

DOCS = Path("data/documents")
OUT = Path("data/demo_subset")
GOLDEN = json.loads(Path("eval/golden_set.json").read_text())

THEME_KEYWORDS = {
    "fear": ["fear"],
    "authority": ["authority", "guru"],
    "self-knowledge": ["self-knowledge", "observer"],
    "relationship": ["relationship"],
    "awareness": ["awareness", "meditation", "conditioning"],
    "thought": ["thought", "thinker"],
    "love": ["love", "desire"],
    "comparison": ["comparison", "compare"],
    "truth": ["truth"],
    "memory": ["memory", "the past"],
    "freedom": ["freedom", "the known"],
}


def main():
    random.seed(42)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    files = list(DOCS.glob("*.txt"))
    picked = set()

    # ~4 talks per theme, matched by keyword hit in the body text
    for theme, keywords in THEME_KEYWORDS.items():
        candidates = []
        for f in files:
            if f in picked:
                continue
            text = f.read_text().lower()
            if any(kw in text for kw in keywords):
                candidates.append(f)
        random.shuffle(candidates)
        for f in candidates[:4]:
            picked.add(f)

    # decade spread: sample a few talks per decade from remaining files
    def year_of(f):
        m = re.search(r"(19|20)\d{2}", f.name)
        return int(m.group(0)) if m else None

    by_decade = {}
    for f in files:
        if f in picked:
            continue
        y = year_of(f)
        if y is None:
            continue
        by_decade.setdefault(y // 10 * 10, []).append(f)

    for decade, group in by_decade.items():
        random.shuffle(group)
        for f in group[:3]:
            picked.add(f)

    for f in picked:
        shutil.copy(f, OUT / f.name)

    print(f"selected {len(picked)} talks into {OUT}")


if __name__ == "__main__":
    main()
