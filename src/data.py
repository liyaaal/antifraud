"""Чтение и очистка транзакций Sparkov.

Один и тот же код используется в обучении и в score.py, чтобы признаки
считались одинаково.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
TRAIN_CSV = DATA_DIR / "fraudTrain.csv"

# Персональные данные и поля, которые не используем (см. CLAUDE.md, раздел 2).
DROP_COLS = ["first", "last", "street", "zip", "job", "unix_time"]

READ_DTYPES = {
    "cc_num": "int64",
    "merchant": "str",
    "category": "str",
    "amt": "float64",
    "gender": "str",
    "city": "str",
    "state": "str",
    "lat": "float64",
    "long": "float64",
    "city_pop": "float64",
    "trans_num": "str",
    "merch_lat": "float64",
    "merch_long": "float64",
}

KEEP_COLS = [
    "trans_num", "ts", "cc_num", "merchant", "category", "amt", "gender",
    "city", "state", "lat", "long", "city_pop", "age", "merch_lat", "merch_long",
]


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    """Сырые поля -> рабочая таблица. Метка is_fraud сохраняется, если она есть."""
    df = raw.copy()
    unnamed = [c for c in df.columns if c.startswith("Unnamed") or c == ""]
    df = df.drop(columns=unnamed + [c for c in DROP_COLS if c in df.columns])

    # Единственный источник времени — trans_date_trans_time (unix_time в Sparkov сдвинут).
    df["ts"] = pd.to_datetime(df["trans_date_trans_time"], errors="coerce")
    df = df.drop(columns=["trans_date_trans_time"])

    # У всех мерчантов префикс fraud_ — это артефакт генератора, а не метка.
    df["merchant"] = df["merchant"].astype("str").str.removeprefix("fraud_")

    dob = pd.to_datetime(df["dob"], errors="coerce")
    df["age"] = ((df["ts"] - dob).dt.days / 365.25).astype("float32")
    df = df.drop(columns=["dob"])

    for c in ["amt", "lat", "long", "city_pop", "merch_lat", "merch_long"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float32")
    df["cc_num"] = pd.to_numeric(df["cc_num"], errors="coerce").fillna(-1).astype("int64")
    df["trans_num"] = df["trans_num"].astype("str")

    cols = KEEP_COLS + (["is_fraud"] if "is_fraud" in df.columns else [])
    df = df[cols]
    if "is_fraud" in df.columns:
        df["is_fraud"] = df["is_fraud"].astype("int8")

    df = df.sort_values(["ts", "trans_num"], kind="mergesort").reset_index(drop=True)
    return df


def read_csv(path) -> pd.DataFrame:
    raw = pd.read_csv(path, dtype=READ_DTYPES, low_memory=False)
    return clean(raw)


def load_train() -> pd.DataFrame:
    """fraudTrain.csv в очищенном виде; кэшируется в parquet."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / "train_clean.parquet"
    if cache.exists() and cache.stat().st_mtime > TRAIN_CSV.stat().st_mtime:
        return pd.read_parquet(cache)
    df = read_csv(TRAIN_CSV)
    df.to_parquet(cache, index=False)
    return df


def card_order(df: pd.DataFrame) -> np.ndarray:
    """Порядок строк: по карте, внутри карты по времени. Нужен рекурсивным признакам."""
    return np.lexsort((df["trans_num"].to_numpy(), df["ts"].to_numpy(), df["cc_num"].to_numpy()))
