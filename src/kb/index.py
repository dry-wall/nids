"""TF-IDF retrieval prototype (Phase 1). Hybrid BM25 + dense + FAISS replaces it in Phase 2."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


class TfidfIndex:
    def __init__(self, chunks: list[dict], vectorizer=None, matrix=None):
        self.chunks = chunks
        self.vectorizer = vectorizer
        self.matrix = matrix

    @staticmethod
    def _doc(c: dict) -> str:
        return f"{c['title']} {c['title']} {c['section']} {c['text']}"  # light title boost

    def build(self) -> "TfidfIndex":
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True,
                                          min_df=1, max_df=0.6, dtype=np.float32)
        self.matrix = self.vectorizer.fit_transform([self._doc(c) for c in self.chunks])
        return self

    def search(self, query: str, k: int = 5, technique: str | None = None, source: str | None = None) -> list[dict]:
        scores = (self.matrix @ self.vectorizer.transform([query]).T).toarray().ravel()
        mask = np.ones(len(self.chunks), dtype=bool)
        if technique:
            mask &= np.array([(c.get("technique_id") or "").split(".")[0] == technique.split(".")[0]
                              for c in self.chunks])
        if source:
            mask &= np.array([c["source"] == source for c in self.chunks])
        scores = np.where(mask, scores, -1.0)
        top = np.argsort(-scores, kind="stable")[:k]
        return [{**self.chunks[i], "score": round(float(scores[i]), 4)} for i in top if scores[i] > 0]

    def save(self, d: Path) -> None:
        d.mkdir(parents=True, exist_ok=True)
        (d / "chunks.json").write_text(json.dumps(self.chunks))
        joblib.dump({"vectorizer": self.vectorizer, "matrix": self.matrix}, d / "tfidf.joblib", compress=3)

    @classmethod
    def load(cls, d: Path) -> "TfidfIndex":
        obj = joblib.load(d / "tfidf.joblib")
        return cls(json.loads((d / "chunks.json").read_text()), obj["vectorizer"], obj["matrix"])
