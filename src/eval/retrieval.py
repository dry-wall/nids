"""Retrieval evaluation on 20 hand-labelled analyst queries (Phase 1 prototype; 60-100 in Phase 2).

Relevance is defined by metadata, not by chunk ID, so it survives re-chunking:
  ("T", "T1110")   -> any ATT&CK chunk of technique T1110 or its sub-techniques
  ("csf", "RS.MI") -> any NIST chunk whose CSF element starts with RS.MI
  ("sec", "2.2")   -> any NIST prose chunk from section 2.2
"""
from __future__ import annotations

import json

import numpy as np
from sklearn.feature_extraction.text import CountVectorizer

from src.config import KB_DIR

QUERIES = [
    ("flood of HTTP requests exhausting web server threads", [("T", "T1499")]),
    ("slow partial HTTP requests hold connections open until the server runs out of capacity", [("T", "T1499")]),
    ("volumetric traffic from many sources saturating network bandwidth", [("T", "T1498")]),
    ("reflection and amplification using spoofed UDP requests", [("T", "T1498")]),
    ("enumerate listening services and open ports on remote hosts", [("T", "T1046")]),
    ("repeated password guessing against SSH logins", [("T", "T1110")]),
    ("credential stuffing with leaked username and password pairs", [("T", "T1110")]),
    ("account lockout after failed login attempts", [("T", "T1110")]),
    ("SQL injection against an internet-facing web application", [("T", "T1190")]),
    ("exploit a vulnerability in a public web server for initial access", [("T", "T1190")]),
    ("web application firewall to block exploitation attempts", [("T", "T1190")]),
    ("malware command and control over HTTP blending with normal web traffic", [("T", "T1071")]),
    ("bot beaconing to a remote controller over an application layer protocol", [("T", "T1071")]),
    ("filter network traffic upstream to mitigate denial of service", [("T", "T1498"), ("T", "T1499")]),
    ("networks and network services are monitored to find potentially adverse events", [("csf", "DE.CM")]),
    ("contain the incident to stop it from spreading", [("csf", "RS.MI")]),
    ("eradicate the incident and remove attacker persistence", [("csf", "RS.MI")]),
    ("analyse the incident to establish what happened and its root cause", [("csf", "RS.AN")]),
    ("restore systems and confirm normal operations after an incident", [("csf", "RC.RP")]),
    ("incident response roles and responsibilities in an organisation", [("sec", "2.2")]),
]
KS = (1, 3, 5, 10)


def relevant(c: dict, rules) -> bool:
    for kind, val in rules:
        if kind == "T" and (c.get("technique_id") or "").split(".")[0] == val:
            return True
        if kind == "csf" and (c["section"].split(" ")[-1]).startswith(val) and c["doc_type"] == "csf-element":
            return True
        if kind == "sec" and c["section"] == val and c["doc_type"] == "guidance":
            return True
    return False


class BM25:
    def __init__(self, chunks, k1=1.5, b=0.75):
        self.cv = CountVectorizer(stop_words="english")
        docs = [f"{c['title']} {c['section']} {c['text']}" for c in chunks]
        self.tf = self.cv.fit_transform(docs).tocsc().astype(np.float32)
        self.dl = np.asarray(self.tf.sum(axis=1)).ravel()
        self.avgdl = self.dl.mean()
        df = np.diff(self.tf.indptr)
        n = self.tf.shape[0]
        self.idf = np.log((n - df + 0.5) / (df + 0.5) + 1.0)
        self.k1, self.b = k1, b

    def scores(self, query: str) -> np.ndarray:
        s = np.zeros(self.tf.shape[0], dtype=np.float64)
        norm = self.k1 * (1 - self.b + self.b * self.dl / self.avgdl)
        for term in self.cv.build_analyzer()(query):
            j = self.cv.vocabulary_.get(term)
            if j is None:
                continue
            col = self.tf.getcol(j)
            rows, tf = col.indices, col.data
            s[rows] += self.idf[j] * tf * (self.k1 + 1) / (tf + norm[rows])
        return s


def _metrics(ranked_rel: list[list[bool]], n_rel: list[int]) -> dict:
    out = {}
    for k in KS:
        out[f"recall@{k}"] = float(np.mean([any(r[:k]) for r in ranked_rel]))
        ndcg = []
        for r, nr in zip(ranked_rel, n_rel):
            dcg = sum(1 / np.log2(i + 2) for i, x in enumerate(r[:k]) if x)
            idcg = sum(1 / np.log2(i + 2) for i in range(min(nr, k)))
            ndcg.append(dcg / idcg if idcg else 0.0)
        out[f"ndcg@{k}"] = float(np.mean(ndcg))
        out[f"precision@{k}"] = float(np.mean([sum(r[:k]) / k for r in ranked_rel]))
    mrr = [next((1 / (i + 1) for i, x in enumerate(r) if x), 0.0) for r in ranked_rel]
    out["mrr"] = float(np.mean(mrr))
    return out


def evaluate(index) -> dict:
    chunks = index.chunks
    bm25 = BM25(chunks)
    systems = {
        "TF-IDF (1-2 gram)": lambda q: (index.matrix @ index.vectorizer.transform([q]).T).toarray().ravel(),
        "BM25": bm25.scores,
    }
    results, per_query = {}, []
    n_rel = [sum(relevant(c, rules) for c in chunks) for _, rules in QUERIES]
    for name, score_fn in systems.items():
        ranked_rel = []
        for qi, (q, rules) in enumerate(QUERIES):
            top = np.argsort(-score_fn(q), kind="stable")[:max(KS)]
            rr = [relevant(chunks[i], rules) for i in top]
            ranked_rel.append(rr)
            if name.startswith("TF-IDF"):
                per_query.append({"query": q, "relevant_if": [f"{k}:{v}" for k, v in rules],
                                  "n_relevant": n_rel[qi], "first_hit_rank": next((i + 1 for i, x in enumerate(rr) if x), None),
                                  "top3": [chunks[i]["chunk_id"] for i in top[:3]]})
        results[name] = _metrics(ranked_rel, n_rel)
    best_k = min((k for k in KS if results["TF-IDF (1-2 gram)"][f"recall@{k}"] >= 0.9), default=max(KS))
    report = {"n_queries": len(QUERIES), "systems": results, "per_query": per_query,
              "recommended_k": best_k, "note": "Phase-1 prototype; hybrid BM25 + dense + FAISS in Phase 2."}
    (KB_DIR / "retrieval_eval.json").write_text(json.dumps(report, indent=2))
    for name, m in results.items():
        print(f"{name:20s} " + "  ".join(f"{k}={v:.3f}" for k, v in m.items() if not k.startswith("precision")))
    for pq in per_query:
        print(f"  [{pq['first_hit_rank'] or '-':>2}] {pq['query'][:70]}")
    return report
