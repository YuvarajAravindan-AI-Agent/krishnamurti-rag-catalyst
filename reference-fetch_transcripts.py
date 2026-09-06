#!/usr/bin/env python3
"""
Fetch official talk transcripts from the Krishnamurti Foundation Trust's
own public WordPress API.

Why this source and not the others:
  - KFT holds the rights, so this is the authentic published text.
  - kfoundation.org/robots.txt allows all agents (Crawl-delay: 5).
  - It is their public REST API, not screen-scraping around anything.

We honour the 5-second crawl delay, request 25 records per call rather
than hammering per-item endpoints, and cache to disk so a re-run costs
the server nothing. ~3000 transcripts at 25/page and 5s/page is roughly
ten minutes — deliberately slow. Resume is automatic.

The text stays local, for personal study. It remains KFT's copyright;
this is not a redistribution.
"""

import argparse
import html
import json
import re
import time
from pathlib import Path

import requests

DATA = Path(__file__).parent / "data"
OUT = DATA / "transcripts.json"

API = "https://kfoundation.org/wp-json/wp/v2/kft_transcript"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
CRAWL_DELAY = 5      # from kfoundation.org/robots.txt
PER_PAGE = 25

TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"[ \t]+")
BLANKS = re.compile(r"\n{3,}")


def clean(rendered):
    """WordPress HTML -> plain text, keeping paragraph breaks."""
    text = re.sub(r"</p>|<br\s*/?>", "\n", rendered, flags=re.I)
    text = TAG.sub("", text)
    text = html.unescape(text)
    text = WS.sub(" ", text)
    return BLANKS.sub("\n\n", text).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=0,
                    help="stop after N pages (0 = all); useful for a trial run")
    args = ap.parse_args()

    records = {}
    if OUT.exists():
        records = {r["id"]: r for r in json.loads(OUT.read_text())}
        print(f"resuming with {len(records)} already fetched")

    session = requests.Session()
    session.headers["User-Agent"] = UA

    page = 1
    while True:
        if args.max_pages and page > args.max_pages:
            break
        try:
            r = session.get(API, params={"per_page": PER_PAGE, "page": page,
                                         "orderby": "id", "order": "asc"},
                            timeout=60)
        except requests.RequestException as e:
            print(f"  page {page}: {e} — retrying once after 15s")
            time.sleep(15)
            continue

        if r.status_code == 400:
            break                      # past the last page
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break

        for p in batch:
            body = clean(p.get("content", {}).get("rendered", ""))
            if len(body) < 200:        # stubs and placeholders
                continue
            records[p["id"]] = {
                "id": p["id"],
                "title": html.unescape(TAG.sub("", p.get("title", {}).get("rendered", ""))),
                "link": p.get("link"),
                "text": body,
            }

        total_pages = int(r.headers.get("x-wp-totalpages", 0) or 0)
        print(f"  page {page}/{total_pages or '?'} — {len(records)} transcripts")

        OUT.write_text(json.dumps(list(records.values()), ensure_ascii=False))

        if total_pages and page >= total_pages:
            break
        page += 1
        time.sleep(CRAWL_DELAY)

    chars = sum(len(r["text"]) for r in records.values())
    print(f"\ntranscripts: {len(records)}")
    print(f"characters:  {chars:,}")
    print(f"written to:  {OUT}")


if __name__ == "__main__":
    main()
