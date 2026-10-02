"""Разбиение по времени: train / valid / holdout (CLAUDE.md, раздел 3)."""
import pandas as pd

VALID_DAYS = 61
HOLDOUT_DAYS = 61


def boundaries(ts: pd.Series) -> dict:
    """Границы по календарным дням. holdout — последние 61 день, valid — 61 день до него."""
    last_day = ts.max().normalize()
    holdout_start = last_day - pd.Timedelta(days=HOLDOUT_DAYS - 1)
    valid_start = holdout_start - pd.Timedelta(days=VALID_DAYS)
    return {"valid_start": valid_start, "holdout_start": holdout_start, "last_day": last_day}


def assign(ts: pd.Series, b: dict | None = None) -> pd.Series:
    b = b or boundaries(ts)
    part = pd.Series("train", index=ts.index, dtype="object")
    part[ts >= b["valid_start"]] = "valid"
    part[ts >= b["holdout_start"]] = "holdout"
    return part
