"""P1.2 - load the eight MachineLearningCVE CSVs, clean, de-duplicate, and save one parquet.

Usage:  python -m src.data.clean
Writes: data/processed/flows.parquet, artifacts/tables/class_counts.csv, artifacts/data_card.json
"""
import json
import re
import time

import numpy as np
import pandas as pd

from src.config import (ARTIFACTS, DAY_OF_FILE, FAMILY_OF_LABEL, FEATURES, LABEL_COL,
                        PROCESSED_DIR, RAW_DIR, TABLES_DIR)


def normalise_label(s: pd.Series) -> pd.Series:
    # Thursday's web-attack labels carry a cp1252 en dash; fold any non-ascii run into "-".
    return s.astype(str).str.strip().map(lambda v: re.sub(r"\s*[^\x00-\x7f]+\s*", " - ", v))


def load_raw() -> pd.DataFrame:
    frames = []
    for name, day in DAY_OF_FILE.items():
        path = RAW_DIR / name
        if not path.exists():
            raise FileNotFoundError(f"missing {path} - see README 'Data'")
        df = pd.read_csv(path, encoding="latin-1", low_memory=False)
        df.columns = [c.strip() for c in df.columns]
        df["Day"], df["SourceFile"] = day, name
        frames.append(df)
        print(f"  {name:62s} {len(df):>9,} rows")
    return pd.concat(frames, ignore_index=True)


def main():
    t0 = time.time()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading raw CSVs")
    df = load_raw()
    df[LABEL_COL] = normalise_label(df[LABEL_COL])
    unknown = sorted(set(df[LABEL_COL]) - set(FAMILY_OF_LABEL))
    if unknown:
        raise ValueError(f"unmapped labels: {unknown}")

    numeric = [c for c in df.columns if c not in (LABEL_COL, "Day", "SourceFile")]
    df[numeric] = df[numeric].apply(pd.to_numeric, errors="coerce")
    counts_raw = df[LABEL_COL].value_counts()
    n_raw = len(df)

    # +-inf -> NaN. Imputation happens later with TRAIN-split medians only (no leakage).
    n_inf = int(np.isinf(df[FEATURES].to_numpy()).any(axis=1).sum())
    df[numeric] = df[numeric].replace([np.inf, -np.inf], np.nan)
    n_nan_rows = int(df[FEATURES].isna().any(axis=1).sum())

    # 1) exact duplicates over every flow column (capture metadata excluded)
    before = len(df)
    df = df.drop_duplicates(subset=numeric + [LABEL_COL])
    n_dup_exact = before - len(df)
    # 2) duplicates in the model's own input space: identical 12 features + same label.
    #    Leaving these in lets the same vector sit in train and test and inflates scores.
    before = len(df)
    df = df.drop_duplicates(subset=FEATURES + [LABEL_COL])
    n_dup_feature = before - len(df)
    # Same 12 features but different labels: inherently ambiguous; kept, but counted.
    grp = df.groupby(FEATURES, dropna=False)[LABEL_COL].nunique()
    n_conflict_vectors = int((grp > 1).sum())

    df["Family"] = df[LABEL_COL].map(FAMILY_OF_LABEL)
    df["IsAttack"] = (df["Family"] != "Benign").astype(np.int8)
    df = df.reset_index(drop=True)
    float_cols = [c for c in numeric]
    df[float_cols] = df[float_cols].astype(np.float32)
    df.to_parquet(PROCESSED_DIR / "flows.parquet", index=False)

    counts_clean = df[LABEL_COL].value_counts()
    table = pd.DataFrame({"raw": counts_raw, "after_cleaning": counts_clean}).fillna(0).astype(int)
    table["family"] = table.index.map(FAMILY_OF_LABEL)
    table["removed"] = table["raw"] - table["after_cleaning"]
    table["removed_pct"] = (100 * table["removed"] / table["raw"]).round(2)
    table = table.sort_values("raw", ascending=False)
    table.index.name = "label"
    table.to_csv(TABLES_DIR / "class_counts.csv")

    by_day = df.groupby(["Day", "Family"]).size().unstack(fill_value=0)
    by_day.to_csv(TABLES_DIR / "family_by_day.csv")

    card = {
        "dataset": "CIC-IDS2017 MachineLearningCVE (8 daily CSVs)",
        "rows_raw": n_raw, "rows_with_inf_in_features": n_inf,
        "rows_with_missing_features_after_inf_to_nan": n_nan_rows,
        "exact_duplicates_removed": n_dup_exact,
        "feature_space_duplicates_removed": n_dup_feature,
        "ambiguous_feature_vectors_multi_label": n_conflict_vectors,
        "rows_clean": len(df), "attack_rows_clean": int(df["IsAttack"].sum()),
        "benign_rows_clean": int((df["IsAttack"] == 0).sum()),
        "features": FEATURES, "n_columns_total": len(numeric),
        "class_counts": table.reset_index().to_dict(orient="records"),
        "family_by_day": {d: {k: int(v) for k, v in r.items()} for d, r in by_day.iterrows()},
    }
    (ARTIFACTS / "data_card.json").write_text(json.dumps(card, indent=2))
    print(table.to_string())
    print(json.dumps({k: v for k, v in card.items() if isinstance(v, int)}, indent=2))
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
