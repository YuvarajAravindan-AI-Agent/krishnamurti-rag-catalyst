#!/usr/bin/env python3
"""Split transcripts.json into per-talk .txt files for QuickML Knowledge Base ingest.

Each output file embeds title/date/URL in the content itself (QuickML surfaces
whatever text it's given, no separate metadata channel assumed until verified
live), keeping citations recoverable from the chunked text alone.
"""
import json
import re
import sys
from pathlib import Path

MAX_BYTES = 480_000  # stay under QuickML's 500 KB/doc limit with headroom

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "data/transcripts.json")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "data/documents")


def slugify(title: str, talk_id: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]
    return f"{talk_id}-{slug}.txt"


def extract_date(title: str) -> str:
    m = re.search(r"(\d{1,2}\s+\w+\s+\d{4})$", title.strip())
    return m.group(1) if m else "unknown date"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    talks = json.loads(SRC.read_text())
    written, split_count = 0, 0

    for talk in talks:
        title = talk["title"]
        link = talk["link"]
        date = extract_date(title)
        header = f"Title: {title}\nDate: {date}\nSource: {link}\n\n"
        body = talk["text"]
        content = header + body

        if len(content.encode()) <= MAX_BYTES:
            (OUT / slugify(title, talk["id"])).write_text(content)
            written += 1
        else:
            # rare: a talk long enough to exceed the per-doc limit - split on
            # paragraph boundaries, each part re-carries the same header
            paras = body.split("\n\n")
            parts, cur = [], ""
            for p in paras:
                if len((header + cur + p).encode()) > MAX_BYTES and cur:
                    parts.append(cur)
                    cur = p
                else:
                    cur = f"{cur}\n\n{p}" if cur else p
            if cur:
                parts.append(cur)
            for i, part in enumerate(parts, 1):
                name = slugify(f"{title} part {i}", talk["id"])
                (OUT / name).write_text(f"{header}[Part {i}/{len(parts)}]\n\n{part}")
                written += 1
            split_count += 1

    print(f"talks processed: {len(talks)}")
    print(f"files written:   {written}")
    print(f"talks split (oversized): {split_count}")


if __name__ == "__main__":
    main()
