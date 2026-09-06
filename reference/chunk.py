#!/usr/bin/env python3
"""
Turn the two sources into one chunked corpus ready for embedding.

  Wikiquote  -> short curated passages, already one idea each.
  Transcripts -> whole talks of ~20k characters, which must be split.

Chunking a Krishnamurti talk needs a little care. He circles a question
for a long stretch, so a chunk cut mid-argument retrieves as nonsense.
We split on paragraph boundaries, pack up to a target size, and carry one
paragraph of overlap so an idea straddling a boundary is still findable.

Dialogue markers ("Krishnamurti:", "Questioner:") are kept — they are
part of how the talks read, and they tell you when someone else is
speaking, which matters for not attributing a questioner's words to him.
"""

import json
import random
import re
from pathlib import Path

DATA = Path(__file__).parent / "data"

# Fixed seed: the shuffle must be reproducible so a resumed index lines up
# with the same chunk order it started with.
SHUFFLE_SEED = 20260805

# all-minilm truncates at 256 tokens, roughly 1000-1100 characters, and
# says nothing when it does. A packed chunk can reach TARGET + OVERLAP, so
# both are sized to keep the worst case inside that window rather than the
# typical case.
TARGET_CHARS = 900
OVERLAP_CHARS = 150
MIN_CHUNK = 250

# "Talks in Bombay 1965 — Part 3", "Ojai 1979, Talk 2" etc.
YEAR = re.compile(r"\b(19[0-9]{2})\b")

# Scanned-page furniture left in the older transcripts ("... intelligently. Page 12").
# Only ~2% of talks, all early ones, but it lands mid-sentence and pollutes chunks.
PAGE_ARTIFACT = re.compile(r"[ \t]*\bpage\s+\d+\b[ \t]*", re.IGNORECASE)


def strip_artifacts(text):
    # Must not touch newlines: chunk_text splits on them, and collapsing
    # them turns a whole talk into one unchunkable blob that the embedder
    # then silently truncates.
    return re.sub(r"[ \t]{2,}", " ", PAGE_ARTIFACT.sub(" ", text)).strip()


SENTENCE_END = re.compile(r"(?<=[.?!])\s+")


def split_long(para):
    """
    Break a paragraph that is itself larger than a chunk.

    Some transcripts carry a whole answer as one unbroken paragraph — the
    longest is over 24,000 characters. Paragraph splitting alone leaves
    those intact, and the embedder truncates at roughly 1,000 characters
    without complaining, so the rest of the passage would be indexed as
    though it did not exist. Fall back to sentence boundaries.
    """
    if len(para) <= TARGET_CHARS:
        return [para]

    out, cur = [], ""
    for sent in SENTENCE_END.split(para):
        if cur and len(cur) + len(sent) + 1 > TARGET_CHARS:
            out.append(cur.strip())
            cur = sent
        else:
            cur = f"{cur} {sent}" if cur else sent
    if cur.strip():
        out.append(cur.strip())

    # A sentence longer than a chunk (rare, but it happens in transcribed
    # speech) still has to be cut somewhere.
    final = []
    for piece in out:
        while len(piece) > TARGET_CHARS:
            cut = piece.rfind(" ", 0, TARGET_CHARS) or TARGET_CHARS
            final.append(piece[:cut].strip())
            piece = piece[cut:].strip()
        if piece:
            final.append(piece)
    return final


def chunk_text(text):
    paras = []
    for p in text.split("\n"):
        p = p.strip()
        if p:
            paras.extend(split_long(p))
    chunks, cur = [], ""

    for p in paras:
        if cur and len(cur) + len(p) + 1 > TARGET_CHARS:
            chunks.append(cur.strip())
            # carry the tail of the previous chunk for continuity
            tail = cur[-OVERLAP_CHARS:]
            cut = tail.find(" ")
            cur = (tail[cut + 1:] if cut > 0 else tail) + "\n" + p
        else:
            cur = f"{cur}\n{p}" if cur else p

    if cur.strip():
        chunks.append(cur.strip())
    return [c for c in chunks if len(c) >= MIN_CHUNK]


def main():
    records = []

    # --- Wikiquote passages -------------------------------------------
    wq_path = DATA / "corpus.json"
    if wq_path.exists():
        for r in json.loads(wq_path.read_text()):
            records.append({
                "text": r["text"],
                "source": r["source"],
                "year": r["year"] or -1,
                "kind": "quote",
                "pre_dissolution": r["pre_dissolution"],
                "url": "https://en.wikiquote.org/wiki/Jiddu_Krishnamurti",
            })

    # --- KFT transcripts ----------------------------------------------
    tr_path = DATA / "transcripts.json"
    if tr_path.exists():
        for t in json.loads(tr_path.read_text()):
            m = YEAR.search(t["title"])
            year = int(m.group(1)) if m else -1
            for c in chunk_text(strip_artifacts(t["text"])):
                records.append({
                    "text": c,
                    "source": t["title"],
                    "year": year,
                    "kind": "transcript",
                    # Transcripts are all from the teaching period.
                    "pre_dissolution": False,
                    "url": t["link"],
                })

    # Shuffle before writing. Transcripts arrive in id order, which is
    # chronological, and indexing takes hours on this machine — so an
    # interrupted run would otherwise hold nothing but his earliest talks.
    # The 1930s are the least representative period of the teaching, and a
    # half-built index of only those would quietly misrepresent him.
    # Shuffling makes any prefix a fair sample of all five decades.
    random.Random(SHUFFLE_SEED).shuffle(records)

    out = DATA / "chunks.json"
    out.write_text(json.dumps(records, ensure_ascii=False))

    by_kind = {}
    for r in records:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    chars = sum(len(r["text"]) for r in records)

    print(f"chunks:     {len(records):,}")
    for k, v in sorted(by_kind.items()):
        print(f"  {k:11} {v:,}")
    print(f"characters: {chars:,}")
    print(f"written to: {out}")


if __name__ == "__main__":
    main()
