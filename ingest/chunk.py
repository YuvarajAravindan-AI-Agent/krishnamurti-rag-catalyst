"""
Chunking, carried over unchanged from the Netcup original's chunk.py.

This file is deliberately a faithful port rather than an improvement. The
migration's shadow test only means something if retrieval differs by the
serving stack alone; quietly "fixing" the chunker would make the two
systems incomparable and hide whichever change actually mattered.

Chunking a Krishnamurti talk needs care. He circles a question for a long
stretch, so a chunk cut mid-argument retrieves as nonsense. We split on
paragraph boundaries, pack up to a target size, and carry one paragraph of
overlap so an idea straddling a boundary is still findable.

Dialogue markers ("Krishnamurti:", "Questioner:") are kept — they are part
of how the talks read, and they tell you when someone else is speaking,
which matters for not attributing a questioner's words to him.
"""

from __future__ import annotations

import re

# all-minilm truncates at 256 tokens, roughly 1000-1100 characters, and says
# nothing when it does. A packed chunk can reach TARGET + OVERLAP, so both
# are sized to keep the worst case inside that window, not the typical case.
TARGET_CHARS = 900
OVERLAP_CHARS = 150
MIN_CHUNK = 250

YEAR = re.compile(r"\b(19[0-9]{2})\b")

# Scanned-page furniture left in the older transcripts ("... intelligently.
# Page 12"). Only ~2% of talks, all early ones, but it lands mid-sentence.
PAGE_ARTIFACT = re.compile(r"[ \t]*\bpage\s+\d+\b[ \t]*", re.IGNORECASE)

SENTENCE_END = re.compile(r"(?<=[.?!])\s+")


def strip_artifacts(text: str) -> str:
    # Must not touch newlines: chunk_text splits on them, and collapsing them
    # turns a whole talk into one unchunkable blob that the embedder then
    # silently truncates.
    return re.sub(r"[ \t]{2,}", " ", PAGE_ARTIFACT.sub(" ", text)).strip()


def split_long(para: str) -> list[str]:
    """
    Break a paragraph that is itself larger than a chunk.

    Some transcripts carry a whole answer as one unbroken paragraph — the
    longest is over 24,000 characters. Paragraph splitting alone leaves those
    intact, and the embedder truncates at roughly 1,000 characters without
    complaining, so the rest would be indexed as though it did not exist.
    """
    if len(para) <= TARGET_CHARS:
        return [para]

    out: list[str] = []
    cur = ""
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
    final: list[str] = []
    for piece in out:
        while len(piece) > TARGET_CHARS:
            cut = piece.rfind(" ", 0, TARGET_CHARS) or TARGET_CHARS
            final.append(piece[:cut].strip())
            piece = piece[cut:].strip()
        if piece:
            final.append(piece)
    return final


def chunk_text(text: str) -> list[str]:
    paras: list[str] = []
    for p in text.split("\n"):
        p = p.strip()
        if p:
            paras.extend(split_long(p))

    chunks: list[str] = []
    cur = ""
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
