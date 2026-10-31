"""Seeded splits. Always applied AFTER de-duplication (see clean.py)."""
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from src.config import SEED, SPLIT, TEMPORAL_TEST_DAYS, TEMPORAL_TRAIN_DAYS


def random_split(df: pd.DataFrame, seed: int = SEED):
    """Stratified by attack family so rare families appear in every split."""
    idx = np.arange(len(df))
    strat = df["Family"].to_numpy()
    tr, rest = train_test_split(idx, test_size=1 - SPLIT[0], stratify=strat, random_state=seed)
    val_share = SPLIT[1] / (SPLIT[1] + SPLIT[2])
    va, te = train_test_split(rest, test_size=1 - val_share, stratify=strat[rest], random_state=seed)
    return np.sort(tr), np.sort(va), np.sort(te)


def temporal_split(df: pd.DataFrame, seed: int = SEED):
    """Train/val on Mon-Wed, test on Thu-Fri. Thu-Fri attack families never appear in training,
    so this measures how much of the random-split score is memorisation of seen families."""
    days = df["Day"].to_numpy()
    pool = np.where(np.isin(days, TEMPORAL_TRAIN_DAYS))[0]
    te = np.where(np.isin(days, TEMPORAL_TEST_DAYS))[0]
    tr, va = train_test_split(pool, test_size=0.15, stratify=df["Family"].to_numpy()[pool],
                              random_state=seed)
    return np.sort(tr), np.sort(va), np.sort(te)
