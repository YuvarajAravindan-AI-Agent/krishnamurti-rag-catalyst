"""
In-process cosine retrieval over the prebuilt index.

Replaces Chroma. At the scale this app runs at — 2.7k chunks for the demo
subset, ~164k for the full archive — an exact dot product against a
normalised float32 matrix is both faster and more predictable than an ANN
index, and it has no recall error to reason about when the agent is trying
to attribute a metric change to a cause. 164k x 384 floats is ~250 MB
resident, which an AppSail container carries comfortably.

Scores here are cosine similarity in exactly the sense the Netcup original
used it (Chroma collection built with hnsw:space=cosine, relevance
reported as 1 - distance), which is what lets MIN_RELEVANCE cross over
untouched. See ingest/verify_embeddings.py for the measurement.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np

from embedder import Embedder


class Retriever:
    def __init__(self, index_dir: Path | str, embedder: Embedder | None = None):
        index_dir = Path(index_dir)

        # Two layouts: the unpacked one build_index.py writes locally, and the
        # packed one shipped through Stratus (float16 vectors, gzipped text).
        # float16 halves the download; it is widened back to float32 here
        # because numpy's float16 matmul is far slower than the conversion.
        packed = index_dir / "vectors.f16.npy"
        if packed.exists():
            self.vectors: np.ndarray = np.load(packed).astype(np.float32)
        else:
            self.vectors = np.load(index_dir / "vectors.npy")

        chunks_gz = index_dir / "chunks.jsonl.gz"
        if chunks_gz.exists():
            text = gzip.decompress(chunks_gz.read_bytes()).decode()
        else:
            text = (index_dir / "chunks.jsonl").read_text()
        self.chunks: list[dict] = [json.loads(line) for line in text.splitlines()]

        self.manifest: dict = json.loads((index_dir / "manifest.json").read_text())

        if len(self.chunks) != self.vectors.shape[0]:
            raise ValueError(
                f"index is inconsistent: {self.vectors.shape[0]} vectors vs "
                f"{len(self.chunks)} chunks — rebuild it rather than serving from it"
            )

        self.embedder = embedder or Embedder()

    def search(self, question: str, n_results: int = 4, include_early: bool = False) -> list[dict]:
        """
        Mirrors the original server's search(), including the pre-1929 exclusion.

        pre_dissolution is the Theosophical period he repudiated when he
        dissolved the Order of the Star. Excluded unless explicitly asked for.
        """
        q = self.embedder.encode_one(question)
        scores = self.vectors @ q  # both sides normalised -> cosine similarity

        if not include_early:
            mask = np.array([not c["pre_dissolution"] for c in self.chunks])
            scores = np.where(mask, scores, -np.inf)

        # argpartition rather than a full sort: at 164k rows the sort is the
        # dominant cost of a query and we only ever want the top handful.
        k = min(n_results, len(self.chunks))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]

        out = []
        for i in top:
            if not np.isfinite(scores[i]):
                continue
            c = self.chunks[int(i)]
            cite = c["source"]
            # Decade sections ("1970s") already carry their date; only a
            # named work needs the year appended.
            if c["year"] != -1 and str(c["year"]) not in cite:
                cite += f" ({c['year']})"
            out.append({
                "text": c["text"],
                "cite": cite,
                "url": c.get("url") or "",
                "year": c["year"],
                "relevance": round(float(scores[i]), 3),
            })
        return out
