"""Detection service: loads the versioned bundle once, scores uploaded flow CSVs, keeps recent analyses."""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from collections import Counter, OrderedDict

import joblib
import numpy as np
import pandas as pd

from src.config import BUNDLE_DIR, FAMILY_OF_LABEL, FEATURES, LABEL_COL
from src.detect.features import Preprocessor, raw_matrix, strip_columns
from src.detect.models import MODEL_NAMES, LinearModel, NumpyMLP, SklearnProba
from src.explain.zscore import BenignBaseline

MAX_ANALYSES = 6
TIMELINE_BINS = 120


def logit(p):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return np.log(p / (1 - p))


def band_of(margin: float) -> str:
    """Uncalibrated score margin above the operating threshold, in logit units."""
    if margin >= 6:
        return "strong"
    if margin >= 2.5:
        return "moderate"
    return "marginal"


def normalise_label(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("", "nan", "none") else re.sub(r"\s*[^\x00-\x7f]+\s*", " - ", s)


def prompt_safe(name: str, limit: int = 60) -> str:
    """The file name reaches the LLM prompt; keep it to inert characters so it cannot carry instructions."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:limit] or "upload"


class Bundle:
    def __init__(self):
        self.manifest = json.loads((BUNDLE_DIR / "manifest.json").read_text())
        self.pre = Preprocessor.from_dict(json.loads((BUNDLE_DIR / "preprocess.json").read_text()))
        self.baseline = BenignBaseline.from_dict(json.loads((BUNDLE_DIR / "baseline.json").read_text()))
        lr = json.loads((BUNDLE_DIR / "lr.json").read_text())
        self.models = {
            "lr": LinearModel(lr["coef"], lr["intercept"]),
            "rf": SklearnProba(joblib.load(BUNDLE_DIR / "rf.joblib")),
            "dnn": NumpyMLP(dict(np.load(BUNDLE_DIR / "dnn.npz"))),
        }
        self.thresholds = {k: v["threshold"] for k, v in self.manifest["models"].items()}
        self.default = self.manifest.get("default_model", "dnn")


class Analysis:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class DetectorService:
    def __init__(self):
        self.bundle = Bundle()
        self.analyses: OrderedDict[str, Analysis] = OrderedDict()
        self.lock = threading.Lock()

    # ------------------------------------------------------------------ detect
    def analyze(self, df: pd.DataFrame, file_name: str, model_key: str, t_parse_ms: float) -> Analysis:
        b = self.bundle
        if model_key not in b.models:
            raise ValueError(f"unknown model '{model_key}'")
        t0 = time.perf_counter()
        df = strip_columns(df)
        X = raw_matrix(df)
        n_missing_values = int(np.isnan(X).sum())
        Z = b.pre.transform(X)
        t1 = time.perf_counter()
        p = b.models[model_key].predict_proba(Z)
        t2 = time.perf_counter()
        thr = b.thresholds[model_key]
        flagged = np.flatnonzero(p >= thr)
        zf = b.baseline.z(Z[flagged]) if len(flagged) else np.zeros((0, len(FEATURES)))
        top1 = np.argmax(np.abs(zf), axis=1) if len(flagged) else np.array([], dtype=int)
        top5 = np.argsort(-np.abs(zf), axis=1)[:, :5] if len(flagged) else np.zeros((0, 5), dtype=int)
        top1_z = zf[np.arange(len(flagged)), top1] if len(flagged) else np.array([])
        t3 = time.perf_counter()

        labels = None
        if LABEL_COL in df.columns:
            labels = df[LABEL_COL].map(normalise_label).to_numpy(dtype=object)
            if not any(labels):
                labels = None

        a = Analysis(
            id=uuid.uuid4().hex[:10], file_name=file_name, created=time.time(), model=model_key,
            threshold=thr, X=X, Z=Z, p=p, flagged=flagged, top1=top1, top1_z=top1_z, top5=top5,
            labels=labels, n=len(df), n_missing_values=n_missing_values,
            timings={"parse_ms": round(t_parse_ms, 1), "preprocess_ms": round((t1 - t0) * 1000, 1),
                     "inference_ms": round((t2 - t1) * 1000, 1), "explain_ms": round((t3 - t2) * 1000, 1)},
        )
        a.timings["total_ms"] = round(sum(a.timings.values()), 1)
        a.summary = self._summary(a)
        with self.lock:
            self.analyses[a.id] = a
            while len(self.analyses) > MAX_ANALYSES:
                self.analyses.popitem(last=False)
        return a

    def get(self, aid: str) -> Analysis | None:
        with self.lock:
            return self.analyses.get(aid)

    # ------------------------------------------------------------------ summary
    def _summary(self, a: Analysis) -> dict:
        b = self.bundle
        n, nf = a.n, len(a.flagged)
        lg = logit(a.p)
        edges = np.linspace(-14, 14, 57)
        hist, _ = np.histogram(np.clip(lg, -14, 14), edges)
        margins = lg[a.flagged] - logit(np.array([a.threshold]))[0]
        bands = Counter(band_of(m) for m in margins)
        # file order is capture order in CICFlowMeter output: a coarse timeline of alert density
        bins = np.array_split(np.arange(n), min(TIMELINE_BINS, max(n, 1)))
        is_f = np.zeros(n, dtype=bool); is_f[a.flagged] = True
        timeline = [{"start": int(ix[0]) + 1, "end": int(ix[-1]) + 1, "total": int(len(ix)),
                     "flagged": int(is_f[ix].sum())} for ix in bins if len(ix)]
        top_counts = Counter(FEATURES[j] for row in a.top5 for j in row)
        top1_counts = Counter(FEATURES[j] for j in a.top1)

        gt = None
        if a.labels is not None:
            lab = a.labels
            known = np.array([bool(v) for v in lab])          # rows with no label are left out
            is_atk = np.array([bool(v) and v.upper() != "BENIGN" for v in lab])
            is_ben = known & ~is_atk
            tp = int((is_f & is_atk).sum()); fp = int((is_f & is_ben).sum())
            fn = int((~is_f & is_atk).sum()); tn = int((~is_f & is_ben).sum())
            prec = tp / (tp + fp) if tp + fp else None
            rec = tp / (tp + fn) if tp + fn else None
            f1 = 2 * prec * rec / (prec + rec) if prec and rec else None
            per_label = []
            for v, cnt in Counter(lab[known]).most_common():
                m = lab == v
                per_label.append({"label": v, "family": FAMILY_OF_LABEL.get(v, "Other"), "n": int(cnt),
                                  "flagged": int(is_f[m].sum())})
            gt = {"confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn}, "precision": prec, "recall": rec,
                  "f1": f1, "fpr": fp / (fp + tn) if fp + tn else None, "per_label": per_label,
                  "attack_rows": int(is_atk.sum()), "unlabelled_rows": int((~known).sum())}

        return {
            "id": a.id, "file_name": a.file_name, "model": a.model, "model_name": MODEL_NAMES[a.model],
            "threshold": a.threshold, "total": n, "flagged": nf, "benign": n - nf,
            "flag_rate": nf / n if n else 0.0, "missing_values_imputed": a.n_missing_values,
            "timings": a.timings, "throughput_fps": round(n / (max(a.timings["total_ms"], 0.1) / 1000), 0) if n else 0,
            "score_hist": {"logit_edges": edges.tolist(), "counts": hist.tolist(),
                           "threshold_logit": float(logit(np.array([a.threshold]))[0])},
            "bands": {k: bands.get(k, 0) for k in ("strong", "moderate", "marginal")},
            "timeline": timeline,
            "top_features": [{"feature": f, "count": c, "top1": top1_counts.get(f, 0)} for f, c in top_counts.most_common()],
            "ground_truth": gt, "bundle_version": b.manifest["version"],
        }

    # ------------------------------------------------------------------ listing / records
    def detections(self, a: Analysis, page: int, size: int, band: str | None, label: str | None,
                   q: str | None, sort: str, decisions: dict[int, str]) -> dict:
        lg_thr = logit(np.array([a.threshold]))[0]
        idx = np.arange(len(a.flagged))
        scores = a.p[a.flagged]
        margins = logit(scores) - lg_thr
        if band:
            idx = idx[[band_of(margins[i]) == band for i in idx]]
        if label and a.labels is not None:
            idx = idx[a.labels[a.flagged[idx]] == label]
        if q:
            digits = re.sub(r"\D", "", q)
            if digits:
                idx = idx[[str(a.flagged[i] + 1).startswith(digits) for i in idx]]
        if sort == "record":
            order = idx[np.argsort(a.flagged[idx], kind="stable")]
        else:
            order = idx[np.argsort(-scores[idx], kind="stable")]
        total = len(order)
        sl = order[(page - 1) * size: page * size]
        rows = []
        for i in sl:
            r = int(a.flagged[i])
            rows.append({
                "record": r + 1, "score": float(scores[i]), "margin": round(float(margins[i]), 2),
                "band": band_of(margins[i]), "top_feature": FEATURES[int(a.top1[i])],
                "top_z": round(float(a.top1_z[i]), 2),
                "top_features": [FEATURES[int(j)] for j in a.top5[i][:3]],
                "ground_truth": (a.labels[r] or None) if a.labels is not None else None,
                "decision": decisions.get(r + 1),
            })
        return {"total": total, "page": page, "size": size, "rows": rows}

    def record(self, a: Analysis, record_no: int) -> dict:
        b = self.bundle
        r = record_no - 1
        if r < 0 or r >= a.n:
            raise IndexError(record_no)
        z = b.baseline.z(a.Z[r:r + 1])[0]
        feats = []
        for j, f in enumerate(FEATURES):
            v = a.X[r, j]
            feats.append({"feature": f, "value": None if np.isnan(v) else float(v),
                          "imputed": bool(np.isnan(v)), "z": round(float(z[j]), 2),
                          "benign_median": float(b.baseline.raw_median[j]),
                          "benign_p05": float(b.baseline.raw_p05[j]), "benign_p95": float(b.baseline.raw_p95[j])})
        models = []
        for k, m in b.models.items():
            p = float(m.predict_proba(a.Z[r:r + 1])[0])
            models.append({"key": k, "name": MODEL_NAMES[k], "score": p, "threshold": b.thresholds[k],
                           "flagged": p >= b.thresholds[k], "active": k == a.model})
        score = float(a.p[r])
        margin = float(logit(np.array([score]))[0] - logit(np.array([a.threshold]))[0])
        return {
            "analysis_id": a.id, "record": record_no, "file_name": a.file_name,
            "model": a.model, "model_name": MODEL_NAMES[a.model], "score": score, "threshold": a.threshold,
            "flagged": score >= a.threshold, "margin": round(margin, 2),
            "band": band_of(margin) if score >= a.threshold else None,
            "ground_truth": (a.labels[r] or None) if a.labels is not None else None,
            "deviations": b.baseline.top_k(a.Z[r], a.X[r], 5),
            "features": feats, "models": models,
        }

    def facts(self, a: Analysis, record_no: int) -> dict:
        rec = self.record(a, record_no)
        return {"record_id": f"{prompt_safe(a.file_name)}#{record_no}", "model_name": rec["model_name"],
                "score": rec["score"], "threshold": rec["threshold"], "deviations": rec["deviations"]}
