"""Подготовка сырых полей. Это не синтез признаков, а линейка для сравнения (CLAUDE.md, раздел 10)."""
import numpy as np
import pandas as pd

PREFIX = ""
FEATURES = ["amt", "log_amt", "category", "hour", "dow", "is_night", "is_online",
            "age", "gender_m", "log_city_pop"]
CATEGORICAL = ["category"]
MONOTONE: dict = {}
REASONS = {
    "amt": "Крупная сумма: {amt:.2f} у.е.",
    "log_amt": "Крупная сумма: {amt:.2f} у.е.",
    "category": "Рискованная категория: {category}",
    "hour": "Операция в {hour}:00",
    "is_night": "Ночная операция ({hour}:00)",
    "is_online": "Покупка в интернете ({category})",
}


def fit(train_df: pd.DataFrame) -> dict:
    return {"categories": sorted(train_df["category"].dropna().unique().tolist())}


def transform(df: pd.DataFrame, state: dict) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["amt"] = df["amt"].astype("float32")
    out["log_amt"] = np.log1p(df["amt"].clip(lower=0)).astype("float32")
    out["category"] = pd.Categorical(df["category"], categories=state["categories"])
    hour = df["ts"].dt.hour
    out["hour"] = hour.astype("float32")
    out["dow"] = df["ts"].dt.dayofweek.astype("float32")
    out["is_night"] = ((hour >= 22) | (hour <= 3)).astype("float32")
    out["is_online"] = df["category"].astype("str").str.endswith("_net").astype("float32")
    out["age"] = df["age"].astype("float32")
    out["gender_m"] = (df["gender"] == "M").astype("float32")
    out["log_city_pop"] = np.log1p(df["city_pop"].clip(lower=0)).astype("float32")
    return out
