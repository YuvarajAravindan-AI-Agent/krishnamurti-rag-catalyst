#!/usr/bin/env python3
"""
Build the corpus from the Wikiquote page (CC-BY-SA), preserving the
attribution Wikiquote already carries: which work a passage came from
and when.

Two filters matter here and are easy to get wrong:

1. "Quotes about Krishnamurti" is other people talking about him. Those
   are not his words and must never end up in the retrieval index.

2. Anything before 1929 is the Theosophical period, written while he was
   being groomed as the World Teacher — "At the Feet of the Master" was
   published under the name Alcyone when he was sixteen. In 1929 he
   dissolved the Order of the Star and repudiated all of it. It is kept
   here because it is historically real, but tagged so it can be excluded
   from anything claiming to represent the teaching.
"""

import json
import re
from pathlib import Path

DATA = Path(__file__).parent / "data"

# Sections that are not Krishnamurti speaking.
EXCLUDED_TOP = {"Quotes about Krishnamurti", "See also", "External links"}

# Below this length a line is almost always an edition note or a stray
# fragment rather than a quote.
MIN_QUOTE_CHARS = 60

# Wikiquote editorial furniture that can exceed the length threshold:
# edition notes, "full text" links, translator credits.
NOISE = re.compile(
    r"(full text|multiple formats|written using the pseudonym|"
    r"\bedition\b\s*\)?$|^translated by|^as quoted in|^variant:)",
    re.IGNORECASE,
)

BREAK_YEAR = 1929  # dissolution of the Order of the Star


def parse_header(line):
    """Return (level, title) for a '== title ==' style line, else None."""
    m = re.match(r"^(={2,5})\s*(.*?)\s*\1$", line.strip())
    if not m:
        return None
    return len(m.group(1)), m.group(2).strip()


def extract_year(title):
    """First 4-digit year in a section title, e.g. 'Meditations (1979)'."""
    m = re.search(r"\b(18|19|20)\d{2}\b", title)
    return int(m.group(0)) if m else None


def main():
    text = (DATA / "wikiquote.txt").read_text()

    top = None          # current '==' section
    decade = None       # current '===' section, usually '1970s'
    work = None         # current '====' section, a named book or talk
    records = []

    for raw in text.split("\n"):
        header = parse_header(raw)
        if header:
            level, title = header
            if level == 2:
                top, decade, work = title, None, None
            elif level == 3:
                decade, work = title, None
            elif level == 4:
                work = title
            continue

        if top != "Quotes":
            continue

        line = raw.strip()
        if len(line) < MIN_QUOTE_CHARS or NOISE.search(line):
            continue

        year = extract_year(work or "") or extract_year(decade or "")
        source = work or decade or "Uncollected"

        records.append({
            "text": line,
            "source": source,
            "period": decade,
            "year": year,
            # Pre-1929 material is the Theosophical period he later rejected.
            "pre_dissolution": bool(year and year < BREAK_YEAR),
        })

    out = DATA / "corpus.json"
    out.write_text(json.dumps(records, indent=2, ensure_ascii=False))

    early = sum(r["pre_dissolution"] for r in records)
    chars = sum(len(r["text"]) for r in records)
    print(f"passages:            {len(records)}")
    print(f"  pre-1929 (tagged): {early}")
    print(f"  teaching period:   {len(records) - early}")
    print(f"total characters:    {chars:,}")
    print(f"distinct sources:    {len({r['source'] for r in records})}")
    print(f"written to:          {out}")


if __name__ == "__main__":
    main()
