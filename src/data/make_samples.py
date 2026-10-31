"""Demo CSVs drawn ONLY from the held-out test split, written with the original CICFlowMeter headers
(leading spaces included) so the demo exercises the same schema handling as a real upload.

Usage: python -m src.data.make_samples
"""
import json

import numpy as np
import pandas as pd

from src.config import PROCESSED_DIR, RAW_DIR, SAMPLES_DIR, SEED

EXTRA = ["Day", "SourceFile", "Family", "IsAttack"]


def original_headers() -> list[str]:
    with open(RAW_DIR / "Monday-WorkingHours.pcap_ISCX.csv", encoding="latin-1") as f:
        return f.readline().rstrip("\n").split(",")


def write(df: pd.DataFrame, name: str, title: str, desc: str, headers: list[str]) -> dict:
    out = df.drop(columns=EXTRA)
    out.columns = headers
    path = SAMPLES_DIR / name
    out.to_csv(path, index=False)
    fam = df["Family"].value_counts().to_dict()
    return {"name": name, "title": title, "description": desc, "rows": len(df),
            "attacks": int(df["IsAttack"].sum()), "families": {k: int(v) for k, v in fam.items()},
            "size_kb": round(path.stat().st_size / 1024)}


def main():
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(PROCESSED_DIR / "flows.parquet")
    test = np.load(PROCESSED_DIR / "splits.npz")["test"]
    t = df.iloc[test]
    headers = original_headers()
    assert len(headers) == df.shape[1] - len(EXTRA), "header count mismatch"
    rng = np.random.default_rng(SEED)
    meta = []

    # 1) mixed: every attack family represented, benign majority, capture order preserved
    parts = [t[t.Family == "Benign"].sample(1400, random_state=SEED)]
    quota = {"DoS": 170, "DDoS": 150, "PortScan": 60, "Brute Force": 80, "Web Attack": 70, "Bot": 50,
             "Infiltration": 10, "Heartbleed": 5}
    for fam, k in quota.items():
        pool = t[t.Family == fam]
        parts.append(pool.sample(min(k, len(pool)), random_state=SEED))
    mixed = pd.concat(parts).sort_index()
    meta.append(write(mixed, "demo_mixed_2k.csv", "Mixed week - 2k flows",
                      "A cross-section of the whole week, including every attack type.", headers))

    # 2) a contiguous slice of Wednesday (DoS day), as a SOC would see it
    wed = t[t.Day == "Wednesday"]
    start = int(rng.integers(0, max(len(wed) - 8000, 1)))
    meta.append(write(wed.iloc[start:start + 8000], "wednesday_slice_8k.csv", "Wednesday - 8k flows",
                      "Held-out flows from one stretch of Wednesday, when the denial-of-service attacks ran.", headers))

    # 3) throughput demo
    big = t.sample(50_000, random_state=SEED).sort_index()
    meta.append(write(big, "test_sample_50k.csv", "Large file - 50k flows",
                      "Fifty thousand flows in their natural mix, to see how fast it runs.", headers))

    (SAMPLES_DIR / "samples.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
