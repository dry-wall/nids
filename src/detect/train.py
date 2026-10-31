"""P1.3 - train LR / RF / DNN on de-duplicated CIC-IDS2017, choose thresholds on validation,
evaluate once on the held-out test split, run the temporal leakage check, export the bundle.

Usage:  python -m src.detect.train            (full run, 3 seeds)
        python -m src.detect.train --quick    (5 % subsample, 1 seed - smoke test only)
Writes: artifacts/model_bundle/*, artifacts/metrics.json, artifacts/tables/*, artifacts/figures/*
"""
import argparse
import datetime as dt
import hashlib
import json
import platform
import time

import joblib
import numpy as np
import pandas as pd
import sklearn

from src.config import (ARTIFACTS, BUNDLE_DIR, FEATURES, LABEL_COL, MODEL_SEEDS, PROCESSED_DIR,
                        SEED, TABLES_DIR, TARGET_FPR)
from src.data.split import random_split, temporal_split
from src.detect.features import Preprocessor
from src.detect.models import (MODEL_NAMES, LinearModel, NumpyMLP, SklearnProba, keras_to_arrays,
                               make_lr, make_rf, train_dnn)
from src.eval.detection import (binary_metrics, choose_threshold, per_family, pr_points,
                                roc_points, threshold_sweep)
from src.explain.zscore import BenignBaseline

BUNDLE_VERSION = "phase1-v1"


def fit_model(name, seed, Ztr, ytr, Zva, yva):
    """Returns (serving predictor, extra info, raw estimator for the bundle)."""
    t0 = time.time()
    if name == "lr":
        est = make_lr(seed).fit(Ztr, ytr)
        pred = LinearModel(est.coef_[0], est.intercept_[0])
        info, raw = {}, {"coef": est.coef_[0].tolist(), "intercept": float(est.intercept_[0])}
    elif name == "rf":
        est = make_rf(seed).fit(Ztr, ytr)
        est.n_jobs = 1  # serving: avoid thread fan-out per request
        pred, info, raw = SklearnProba(est), {}, est
    else:
        model, info = train_dnn(Ztr, ytr, Zva, yva, seed)
        arrays = keras_to_arrays(model)
        pred = NumpyMLP(arrays)
        sample = Zva[:4096]
        diff = float(np.max(np.abs(pred.predict_proba(sample) - model.predict(sample, verbose=0).ravel())))
        assert diff < 1e-4, f"numpy MLP diverges from Keras by {diff}"
        info["numpy_vs_keras_max_abs_diff"] = diff
        raw = (model, arrays)
    info["fit_seconds"] = round(time.time() - t0, 1)
    return pred, info, raw


def latency_ms_per_10k(pred, pre: Preprocessor, X_raw_sample, repeats=7):
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        pred.predict_proba(pre.transform(X_raw_sample))
        times.append((time.perf_counter() - t0) * 1000)
    return {"p50": round(float(np.percentile(times, 50)), 2), "p95": round(float(np.percentile(times, 95)), 2)}


def mean_std(rows, key):
    v = np.array([r[key] for r in rows if r.get(key) is not None], dtype=float)
    return {"mean": float(v.mean()), "std": float(v.std(ddof=0)), "values": v.tolist()}


def main(quick: bool):
    t_start = time.time()
    cols = FEATURES + [LABEL_COL, "Family", "IsAttack", "Day"]
    df = pd.read_parquet(PROCESSED_DIR / "flows.parquet", columns=cols)
    if quick:
        df = df.groupby("Family", group_keys=False).apply(
            lambda g: g.sample(frac=0.05, random_state=SEED) if len(g) > 200 else g).reset_index(drop=True)
    seeds = MODEL_SEEDS[:1] if quick else MODEL_SEEDS
    X_raw = df[FEATURES].to_numpy(dtype=np.float64)
    X_raw[~np.isfinite(X_raw)] = np.nan
    y = df["IsAttack"].to_numpy().astype(np.int32)
    fam = df["Family"].to_numpy()
    print(f"rows={len(df):,} attacks={y.sum():,} seeds={seeds}")

    # ---------------- random stratified split (primary result) ----------------
    tr, va, te = random_split(df)
    if not quick:
        np.savez_compressed(PROCESSED_DIR / "splits.npz", train=tr, val=va, test=te)
    pre = Preprocessor().fit(X_raw[tr])
    Z = pre.transform(X_raw)
    baseline = BenignBaseline.fit(Z[tr][y[tr] == 0], X_raw[tr][y[tr] == 0])

    runs = {m: [] for m in MODEL_NAMES}
    primary = {}
    for seed in seeds:
        for name in MODEL_NAMES:
            print(f"\n=== {MODEL_NAMES[name]}  seed={seed}")
            pred, info, raw = fit_model(name, seed, Z[tr], y[tr], Z[va], y[va])
            p_va, p_te = pred.predict_proba(Z[va]), pred.predict_proba(Z[te])
            op = choose_threshold(y[va], p_va, TARGET_FPR)
            m = binary_metrics(y[te], p_te, op["threshold"])
            m.update(seed=seed, operating_point=op, **info)
            runs[name].append(m)
            print(f"thr={op['threshold']:.4f}  test P={m['precision']:.4f} R={m['recall']:.4f} "
                  f"F1={m['f1']:.4f} FPR={m['fpr']:.4%} ROC-AUC={m['roc_auc']:.5f} ({info['fit_seconds']}s)")
            if seed == SEED:
                primary[name] = {
                    "pred": pred, "raw": raw, "threshold": op["threshold"],
                    "roc": roc_points(y[te], p_te), "pr": pr_points(y[te], p_te),
                    "sweep_val": threshold_sweep(y[va], p_va),
                    "per_family_test": per_family(fam[te], p_te, op["threshold"]),
                }

    # ---------------- temporal split: train Mon-Wed, test Thu-Fri ----------------
    temporal = {}
    if not quick:
        ttr, tva, tte = temporal_split(df)
        tpre = Preprocessor().fit(X_raw[ttr])
        TZ = tpre.transform(X_raw)
        for name in MODEL_NAMES:
            print(f"\n=== temporal {MODEL_NAMES[name]}")
            pred, info, _ = fit_model(name, SEED, TZ[ttr], y[ttr], TZ[tva], y[tva])
            p_va, p_te = pred.predict_proba(TZ[tva]), pred.predict_proba(TZ[tte])
            op = choose_threshold(y[tva], p_va, TARGET_FPR)
            m = binary_metrics(y[tte], p_te, op["threshold"])
            m.update(operating_point=op, per_family=per_family(fam[tte], p_te, op["threshold"]), **info)
            temporal[name] = m
            print(f"temporal test P={m['precision']:.4f} R={m['recall']:.4f} F1={m['f1']:.4f} FPR={m['fpr']:.4%}")

    # ---------------- latency of the exact serving path ----------------
    sample = X_raw[te][:10_000]
    latency = {n: latency_ms_per_10k(primary[n]["pred"], pre, sample) for n in MODEL_NAMES}

    if quick:  # smoke test only: report and stop, never overwrite the served bundle or the report metrics
        out = {n: {k: runs[n][0][k] for k in ("precision", "recall", "f1", "fpr", "roc_auc")} for n in MODEL_NAMES}
        (ARTIFACTS / "metrics_quick.json").write_text(json.dumps(out, indent=2))
        print(f"\nQuick run done in {round(time.time() - t_start)}s (bundle untouched)")
        return

    # ---------------- bundle ----------------
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    (BUNDLE_DIR / "preprocess.json").write_text(json.dumps(pre.to_dict()))
    (BUNDLE_DIR / "baseline.json").write_text(json.dumps(baseline.to_dict()))
    (BUNDLE_DIR / "lr.json").write_text(json.dumps(primary["lr"]["raw"]))
    joblib.dump(primary["rf"]["raw"], BUNDLE_DIR / "rf.joblib", compress=3)
    keras_model, arrays = primary["dnn"]["raw"]
    np.savez(BUNDLE_DIR / "dnn.npz", **arrays)
    keras_model.save(BUNDLE_DIR / "dnn.keras")
    data_hash = hashlib.sha256((PROCESSED_DIR / "flows.parquet").read_bytes()).hexdigest()[:16]

    def summary(name):
        rs = runs[name]
        return {k: mean_std(rs, k) for k in ("precision", "recall", "f1", "fpr", "roc_auc", "pr_auc", "mcc", "accuracy")}

    import tensorflow as tf
    manifest = {
        "version": BUNDLE_VERSION,
        "created": dt.datetime.now().isoformat(timespec="seconds"),
        "features": FEATURES, "default_model": "dnn",
        "models": {n: {"name": MODEL_NAMES[n], "threshold": primary[n]["threshold"]} for n in MODEL_NAMES},
        "target_fpr": TARGET_FPR, "split_seed": SEED, "model_seeds": list(seeds),
        "data_sha256_16": data_hash,
        "rows": {"train": int(len(tr)), "val": int(len(va)), "test": int(len(te))},
        "versions": {"python": platform.python_version(), "numpy": np.__version__,
                     "pandas": pd.__version__, "scikit-learn": sklearn.__version__,
                     "tensorflow": tf.__version__},
    }
    (BUNDLE_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))

    metrics = {
        "manifest": manifest,
        "models": {n: {
            "name": MODEL_NAMES[n],
            "summary": summary(n),
            "runs": runs[n],
            "primary_seed": {k: v for k, v in primary[n].items() if k not in ("pred", "raw")},
            "latency_ms_per_10k": latency[n],
        } for n in MODEL_NAMES},
        "temporal": temporal,
        "elapsed_seconds": round(time.time() - t_start),
    }
    (ARTIFACTS / "metrics.json").write_text(json.dumps(metrics))
    from src.eval.figures import write_all
    write_all(metrics)
    print(f"\nDone in {metrics['elapsed_seconds']}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    main(ap.parse_args().quick)
