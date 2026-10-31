"""P1.4 - "why was this flow flagged": distance of each feature from the benign baseline.

z_j = (x_j - mu_benign_j) / sigma_benign_j, computed in the model's transformed feature space
(signed log + standardised), with mu/sigma estimated on BENIGN flows of the training split only.
This says which features are unusual; it is not a causal attribution of the model (SHAP: Phase 2).
"""
from __future__ import annotations

import numpy as np

from src.config import FEATURES


class BenignBaseline:
    def __init__(self, mean, std, raw_median, raw_p05, raw_p95):
        self.mean = np.asarray(mean, dtype=np.float64)
        self.std = np.maximum(np.asarray(std, dtype=np.float64), 1e-6)
        self.raw_median = np.asarray(raw_median, dtype=np.float64)
        self.raw_p05 = np.asarray(raw_p05, dtype=np.float64)
        self.raw_p95 = np.asarray(raw_p95, dtype=np.float64)

    @classmethod
    def fit(cls, Z_benign: np.ndarray, X_raw_benign: np.ndarray) -> "BenignBaseline":
        q = np.nanpercentile(X_raw_benign, [5, 50, 95], axis=0)
        return cls(Z_benign.mean(0), Z_benign.std(0), q[1], q[0], q[2])

    def z(self, Z: np.ndarray) -> np.ndarray:
        return (np.asarray(Z, dtype=np.float64) - self.mean) / self.std

    def top_k(self, Z_row: np.ndarray, X_raw_row: np.ndarray, k: int = 5) -> list[dict]:
        z = self.z(Z_row[None, :])[0]
        order = np.argsort(-np.abs(z), kind="stable")[:k]
        return [{
            "feature": FEATURES[j],
            "value": _num(X_raw_row[j]),
            "z": round(float(z[j]), 2),
            "direction": "above" if z[j] > 0 else "below",
            "benign_median": _num(self.raw_median[j]),
            "benign_p05": _num(self.raw_p05[j]),
            "benign_p95": _num(self.raw_p95[j]),
        } for j in order]

    def to_dict(self) -> dict:
        return {k: getattr(self, k).tolist() for k in ("mean", "std", "raw_median", "raw_p05", "raw_p95")}

    @classmethod
    def from_dict(cls, d: dict) -> "BenignBaseline":
        return cls(d["mean"], d["std"], d["raw_median"], d["raw_p05"], d["raw_p95"])


def _num(v) -> float | None:
    v = float(v)
    return None if not np.isfinite(v) else round(v, 4)
