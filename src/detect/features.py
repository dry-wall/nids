"""Preprocessing shared by training and serving: impute -> signed log -> standardise.

All fitted state is plain numbers stored as JSON, so the API never unpickles preprocessing code.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import FEATURES


class MissingColumns(ValueError):
    def __init__(self, missing):
        super().__init__(f"missing required columns: {missing}")
        self.missing = missing


def strip_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]  # CICFlowMeter pads names with spaces
    return df


def raw_matrix(df: pd.DataFrame) -> np.ndarray:
    missing = [f for f in FEATURES if f not in df.columns]
    if missing:
        raise MissingColumns(missing)
    X = df[FEATURES].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float64)
    X[~np.isfinite(X)] = np.nan
    return X


def signed_log(X: np.ndarray) -> np.ndarray:
    """Flow features are heavy-tailed and Flow Bytes/s can be negative in CIC-IDS2017."""
    return np.sign(X) * np.log1p(np.abs(X))


class Preprocessor:
    def __init__(self, medians=None, mean=None, scale=None):
        self.medians = None if medians is None else np.asarray(medians, dtype=np.float64)
        self.mean = None if mean is None else np.asarray(mean, dtype=np.float64)
        self.scale = None if scale is None else np.asarray(scale, dtype=np.float64)

    def fit(self, X_raw: np.ndarray) -> "Preprocessor":
        self.medians = np.nanmedian(X_raw, axis=0)
        L = signed_log(self._impute(X_raw))
        self.mean = L.mean(axis=0)
        self.scale = L.std(axis=0)
        self.scale[self.scale == 0] = 1.0
        return self

    def _impute(self, X_raw: np.ndarray) -> np.ndarray:
        X = X_raw.copy()
        r, c = np.where(np.isnan(X))
        X[r, c] = self.medians[c]
        return X

    def transform(self, X_raw: np.ndarray) -> np.ndarray:
        return ((signed_log(self._impute(X_raw)) - self.mean) / self.scale).astype(np.float32)

    def to_dict(self) -> dict:
        return {"features": FEATURES, "medians": self.medians.tolist(),
                "mean": self.mean.tolist(), "scale": self.scale.tolist()}

    @classmethod
    def from_dict(cls, d: dict) -> "Preprocessor":
        if d["features"] != FEATURES:
            raise ValueError("bundle feature list does not match src/config.py FEATURES")
        return cls(d["medians"], d["mean"], d["scale"])
