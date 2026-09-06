"""
Refuse questions that name someone the corpus has never heard of.

The shadow test showed a single cosine threshold cannot do this job. Asked
"what did Osho teach about meditation?", the live Netcup app retrieves
Krishnamurti passages at 0.618 and synthesises a confident answer — the
question is *about* meditation, so the passages genuinely are on-topic. The
thing that makes the answer wrong is not topical distance. It's that the
question asks what a specific person said, and that person is not in the
corpus at all.

So this gate asks a different question from the retriever: does the question
name a proper noun the corpus does not contain?

Everything here is derived from the corpus itself. There is no list of
"teachers who aren't Krishnamurti" anywhere in this file — such a list would
be tuned to the golden set's traps and would prove nothing about questions
the set doesn't contain. Instead the index build records which capitalised
tokens actually occur in the talks, and this refuses on the ones that don't.

Consequences worth being explicit about:

  * It fires on unknown proper nouns only. "What is fear?" has none.
  * A name the corpus *does* contain passes through. He discussed the Gita
    and named Buddha and Shankara; questions about those are legitimately
    answerable from his own words, and refusing them would be wrong.
  * It is a precision instrument aimed at one failure mode, not a general
    relevance check. The cosine threshold still does that job.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# A capitalised word, optionally possessive ("Nietzsche's"). Hyphenated and
# accented names are common enough in this material to be worth matching.
CAPITALISED = re.compile(r"\b([A-Z][\w'À-ɏ-]*)")
POSSESSIVE = re.compile(r"['’]s$")

# How often a lowercase form must appear in the talks before we treat a
# capitalised occurrence as an ordinary word that merely started a sentence
# ("Why", "Truth", "Love"). Krishnamurti capitalises abstractions often
# enough that this cannot be a purely positional rule.
COMMON_WORD_MIN = 50

# How often a capitalised token must appear before we accept it as a name
# the corpus genuinely knows. Below this it is a transcription artifact or a
# passing mention too thin to answer a question from.
KNOWN_ENTITY_MIN = 3


class EntityGate:
    def __init__(self, vocab_path: Path | str):
        vocab = json.loads(Path(vocab_path).read_text())
        self.capitalised: dict[str, int] = vocab["capitalised"]
        self.lowercase: dict[str, int] = vocab["lowercase"]

    def unknown_entities(self, question: str) -> list[str]:
        """Proper nouns in the question that the corpus does not contain."""
        unknown = []
        for raw in CAPITALISED.findall(question):
            token = POSSESSIVE.sub("", raw)
            key = token.lower()
            if len(token) < 3:
                continue
            # An ordinary word that happened to be capitalised.
            if self.lowercase.get(key, 0) >= COMMON_WORD_MIN:
                continue
            # A name the talks actually use.
            if self.capitalised.get(key, 0) >= KNOWN_ENTITY_MIN:
                continue
            if token not in unknown:
                unknown.append(token)
        return unknown

    def refusal(self, question: str) -> str | None:
        """A message to show instead of an answer, or None to proceed."""
        unknown = self.unknown_entities(question)
        if not unknown:
            return None
        names = unknown[0] if len(unknown) == 1 else (
            ", ".join(unknown[:-1]) + f" and {unknown[-1]}"
        )
        return (
            f"These talks don't mention {names}. Rather than answer from "
            "passages that are merely on a similar subject, this says nothing "
            "— the archive only contains Krishnamurti's own words."
        )


def build_vocabulary(texts: list[str]) -> dict:
    """Count capitalised and lowercase forms across the corpus."""
    capitalised: dict[str, int] = {}
    lowercase: dict[str, int] = {}
    word = re.compile(r"\b([\w'À-ɏ-]+)")
    for text in texts:
        for tok in word.findall(text):
            key = tok.lower()
            if tok[:1].isupper():
                capitalised[key] = capitalised.get(key, 0) + 1
            else:
                lowercase[key] = lowercase.get(key, 0) + 1
    return {"capitalised": capitalised, "lowercase": lowercase}
