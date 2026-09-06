#!/usr/bin/env python3
"""Find a relevance floor that separates real questions from off-corpus ones.

Vector search always returns the nearest N vectors; it has no concept of "no
match". Asking about something absent from the corpus still yields passages,
just bad ones. This measures where the two populations actually sit so the
cutoff is chosen from data rather than guessed.
"""
import time

import chromadb
import requests

IN_CORPUS = [
    "what is fear?",
    "what is truth?",
    "what is love?",
    "what is meditation?",
    "the observer is the observed",
    "why do we compare ourselves to others?",
    "what is the nature of thought?",
    "can the mind be free of conditioning?",
]

OFF_CORPUS = [
    "osho",
    "how do I install postgresql?",
    "bitcoin price prediction",
    "who won the 1998 world cup?",
    "recipe for banana bread",
    "kubernetes ingress controller",
    "what is the capital of France?",
    "python list comprehension syntax",
]


def main():
    client = chromadb.PersistentClient(path="data/chroma")
    coll = client.get_collection("krishnamurti")

    def emb(text):
        r = requests.post(
            "http://127.0.0.1:11434/api/embeddings",
            json={"model": "all-minilm", "prompt": text},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["embedding"]

    print(f"{'query':<42}{'top':>7}{'2nd':>7}{'3rd':>7}{'time':>8}")
    print("-" * 71)
    stats = {}
    for label, queries in (("IN-CORPUS", IN_CORPUS), ("OFF-CORPUS", OFF_CORPUS)):
        print(f"--- {label} ---")
        tops = []
        for q in queries:
            t0 = time.time()
            res = coll.query(
                query_embeddings=[emb(q)],
                n_results=3,
                where={"pre_dissolution": False},
            )
            rels = [round(1 - d, 3) for d in res["distances"][0]]
            dt = time.time() - t0
            tops.append(rels[0])
            print(f"{q:<42}{rels[0]:>7}{rels[1]:>7}{rels[2]:>7}{dt:>7.2f}s")
        stats[label] = tops

    print("-" * 71)
    lo = min(stats["IN-CORPUS"])
    hi = max(stats["OFF-CORPUS"])
    print(f"lowest in-corpus top score : {lo}")
    print(f"highest off-corpus top score: {hi}")
    if lo > hi:
        print(f"SEPARABLE -- any threshold between {hi} and {lo} works; "
              f"suggest {round((lo + hi) / 2, 3)}")
    else:
        print("OVERLAP -- no clean threshold; the populations intersect")


if __name__ == "__main__":
    main()
