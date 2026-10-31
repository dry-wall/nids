"""Operating-point selection and held-out detection metrics."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve


def choose_threshold(y_val, p_val, target_fpr: float) -> dict:
    """Max-F1 threshold on VALIDATION among those whose benign FPR <= target_fpr."""
    fpr, tpr, thr = roc_curve(y_val, p_val, drop_intermediate=False)
    P, N = int(y_val.sum()), int(len(y_val) - y_val.sum())
    tp, fp = tpr * P, fpr * N
    prec = np.divide(tp, tp + fp, out=np.ones_like(tp), where=(tp + fp) > 0)
    f1 = np.divide(2 * prec * tpr, prec + tpr, out=np.zeros_like(tp), where=(prec + tpr) > 0)
    finite = np.isfinite(thr)
    ok = (fpr <= target_fpr) & finite
    if ok.any():
        i = np.flatnonzero(ok)[np.argmax(f1[ok])]
    else:  # no threshold reaches the target: take the lowest FPR, best F1 among ties
        cand = np.flatnonzero(finite & (fpr == fpr[finite].min()))
        i = cand[np.argmax(f1[cand])]
    return {"threshold": float(min(thr[i], 1.0)), "target_met": bool(fpr[i] <= target_fpr),
            "val_fpr": float(fpr[i]), "val_recall": float(tpr[i]), "val_precision": float(prec[i]),
            "val_f1": float(f1[i]), "target_fpr": target_fpr}


def binary_metrics(y, p, threshold: float) -> dict:
    pred = p >= threshold
    tp = int((pred & (y == 1)).sum()); fp = int((pred & (y == 0)).sum())
    fn = int((~pred & (y == 1)).sum()); tn = int((~pred & (y == 0)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    mcc_den = np.sqrt(float(tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return {
        "precision": precision, "recall": recall, "f1": f1,
        "fpr": fp / (fp + tn) if fp + tn else 0.0,
        "accuracy": (tp + tn) / len(y),
        "mcc": ((tp * tn - fp * fn) / mcc_den) if mcc_den else 0.0,
        "roc_auc": float(roc_auc_score(y, p)) if 0 < y.sum() < len(y) else None,
        "pr_auc": float(average_precision_score(y, p)) if y.sum() else None,
        "confusion": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "n": int(len(y)), "threshold": threshold,
    }


def per_family(families: np.ndarray, p: np.ndarray, threshold: float) -> list[dict]:
    """Share of each ground-truth family flagged (detection rate; for Benign this is the FPR)."""
    out = []
    for fam in sorted(set(families)):
        m = families == fam
        out.append({"family": fam, "n": int(m.sum()), "flagged": int((p[m] >= threshold).sum()),
                    "rate": float((p[m] >= threshold).mean())})
    return out


def roc_points(y, p, n=160) -> list[dict]:
    fpr, tpr, _ = roc_curve(y, p)
    grid = np.unique(np.concatenate([[0.0], np.logspace(-5, 0, n)]))
    return [{"fpr": float(f), "tpr": float(np.interp(f, fpr, tpr))} for f in grid]


def pr_points(y, p, n=120) -> list[dict]:
    order = np.argsort(-p, kind="stable")
    ys = y[order]
    tp = np.cumsum(ys); fp = np.cumsum(1 - ys)
    prec, rec = tp / (tp + fp), tp / max(ys.sum(), 1)
    # interpolated precision: best precision achievable at recall >= r
    prec_interp = np.maximum.accumulate(prec[::-1])[::-1]
    grid = np.linspace(0, 1, n + 1)
    idx = np.clip(np.searchsorted(rec, grid, side="left"), 0, len(rec) - 1)
    return [{"recall": float(r), "precision": float(prec_interp[i])} for r, i in zip(grid, idx)]


def threshold_sweep(y, p, n=241) -> dict:
    """Confusion counts at thresholds spaced evenly in logit space (scores pile up near 0 and 1)."""
    t = 1 / (1 + np.exp(-np.linspace(-12, 12, n)))
    ps0, ps1 = np.sort(p[y == 0]), np.sort(p[y == 1])
    fp = len(ps0) - np.searchsorted(ps0, t, side="left")
    tp = len(ps1) - np.searchsorted(ps1, t, side="left")
    logit = np.log(np.clip(p, 1e-12, 1 - 1e-12) / np.clip(1 - p, 1e-12, 1))
    edges = np.linspace(-14, 14, 57)
    h0, _ = np.histogram(np.clip(logit[y == 0], -14, 14), edges)
    h1, _ = np.histogram(np.clip(logit[y == 1], -14, 14), edges)
    return {"thresholds": t.tolist(), "tp": tp.tolist(), "fp": fp.tolist(),
            "n_pos": int(len(ps1)), "n_neg": int(len(ps0)),
            "hist": {"logit_edges": edges.tolist(), "benign": h0.tolist(), "attack": h1.tolist()}}
