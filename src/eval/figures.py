"""Report-ready tables (CSV + Markdown) and figures (PNG) generated from artifacts/metrics.json.

Usage: python -m src.eval.figures
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.config import ARTIFACTS, FIGURES_DIR, TABLES_DIR  # noqa: E402

COLORS = {"lr": "#8b93a7", "rf": "#2f9e8f", "dnn": "#3b6fd8"}


def _pm(s, k, pct=False):
    m, sd = s[k]["mean"], s[k]["std"]
    return f"{100*m:.2f} ± {100*sd:.2f}" if pct else f"{m:.4f} ± {sd:.4f}"


def write_tables(metrics):
    rows = []
    for key, m in metrics["models"].items():
        s = m["summary"]
        rows.append({"Model": m["name"], "Precision": _pm(s, "precision"), "Recall": _pm(s, "recall"),
                     "F1": _pm(s, "f1"), "ROC-AUC": _pm(s, "roc_auc"), "PR-AUC": _pm(s, "pr_auc"),
                     "FPR (%)": _pm(s, "fpr", pct=True),
                     "Threshold (seed 42)": f"{m['primary_seed']['threshold']:.4f}",
                     "ms / 10k flows (p50)": m["latency_ms_per_10k"]["p50"]})
    t = pd.DataFrame(rows)
    t.to_csv(TABLES_DIR / "model_comparison.csv", index=False)
    (TABLES_DIR / "model_comparison.md").write_text(t.to_markdown(index=False), encoding="utf-8")

    if metrics.get("temporal"):
        rows = [{"Model": metrics["models"][k]["name"], "Precision": f"{v['precision']:.4f}",
                 "Recall": f"{v['recall']:.4f}", "F1": f"{v['f1']:.4f}",
                 "ROC-AUC": f"{v['roc_auc']:.4f}", "FPR (%)": f"{100*v['fpr']:.2f}"}
                for k, v in metrics["temporal"].items()]
        tt = pd.DataFrame(rows)
        tt.to_csv(TABLES_DIR / "temporal_split.csv", index=False)
        (TABLES_DIR / "temporal_split.md").write_text(tt.to_markdown(index=False), encoding="utf-8")

    fam = {m["name"]: {r["family"]: r["rate"] for r in m["primary_seed"]["per_family_test"]}
           for m in metrics["models"].values()}
    pf = pd.DataFrame(fam).round(4)
    pf.index.name = "Ground-truth family (Benign row = FPR)"
    pf.to_csv(TABLES_DIR / "per_family_detection.csv")
    (TABLES_DIR / "per_family_detection.md").write_text(pf.to_markdown(), encoding="utf-8")


def write_figures(metrics):
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    ms = metrics["models"]

    fig, ax = plt.subplots(figsize=(5.2, 4.2))
    for k, m in ms.items():
        r = m["primary_seed"]["roc"]
        ax.plot([p["fpr"] for p in r], [p["tpr"] for p in r], color=COLORS[k], lw=2,
                label=f"{m['name']} (AUC {m['summary']['roc_auc']['mean']:.4f})")
    ax.set_xscale("log"); ax.set_xlim(1e-5, 1); ax.set_xlabel("False positive rate (log)")
    ax.set_ylabel("True positive rate"); ax.set_title("ROC - held-out test split")
    ax.axvline(metrics["manifest"]["target_fpr"], color="#c44", ls=":", lw=1)
    ax.legend(loc="lower right", frameon=False); fig.tight_layout()
    fig.savefig(FIGURES_DIR / "roc_test.png", dpi=200); plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.2, 4.2))
    for k, m in ms.items():
        r = m["primary_seed"]["pr"]
        ax.plot([p["recall"] for p in r], [p["precision"] for p in r], color=COLORS[k], lw=2,
                label=f"{m['name']} (AP {m['summary']['pr_auc']['mean']:.4f})")
    ax.set_xlabel("Recall"); ax.set_ylabel("Precision"); ax.set_title("Precision-recall - test split")
    ax.legend(loc="lower left", frameon=False); fig.tight_layout()
    fig.savefig(FIGURES_DIR / "pr_test.png", dpi=200); plt.close(fig)

    for k, m in ms.items():
        c = m["runs"][0]["confusion"]
        mat = np.array([[c["tn"], c["fp"]], [c["fn"], c["tp"]]])
        fig, ax = plt.subplots(figsize=(4, 3.6))
        ax.imshow(mat / mat.sum(1, keepdims=True), cmap="Blues", vmin=0, vmax=1)
        for i in range(2):
            for j in range(2):
                ax.text(j, i, f"{mat[i, j]:,}\n({100*mat[i, j]/mat[i].sum():.2f}%)", ha="center",
                        va="center", color="white" if i == j else "#123")
        ax.set_xticks([0, 1], ["Benign", "Attack"]); ax.set_yticks([0, 1], ["Benign", "Attack"])
        ax.set_xlabel("Predicted"); ax.set_ylabel("Ground truth")
        ax.set_title(f"{m['name']} - test (thr {m['runs'][0]['threshold']:.3f})")
        fig.tight_layout(); fig.savefig(FIGURES_DIR / f"confusion_{k}.png", dpi=200); plt.close(fig)

    card = json.loads((ARTIFACTS / "data_card.json").read_text())
    cc = pd.DataFrame(card["class_counts"]).set_index("label")[["raw", "after_cleaning"]]
    fig, ax = plt.subplots(figsize=(7, 4.6))
    cc.sort_values("raw").plot.barh(ax=ax, logx=True, color=["#c9d3e6", "#3b6fd8"], width=0.8)
    ax.set_xlabel("Flows (log scale)"); ax.set_ylabel(""); ax.set_title("CIC-IDS2017 class counts before / after cleaning")
    ax.legend(["raw", "after de-duplication"], frameon=False); fig.tight_layout()
    fig.savefig(FIGURES_DIR / "class_counts.png", dpi=200); plt.close(fig)


def write_all(metrics):
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    write_tables(metrics)
    write_figures(metrics)
    print(f"tables -> {TABLES_DIR}\nfigures -> {FIGURES_DIR}")


if __name__ == "__main__":
    write_all(json.loads((ARTIFACTS / "metrics.json").read_text()))
