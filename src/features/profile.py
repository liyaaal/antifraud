"""Блок A — «Сколько бит неожиданности»: профиль хозяина карты (tasks/TASK_A.md).

Каждая операция сравнивается с прошлым поведением именно этой карты. Профиль новой карты
сглажен к «среднему клиенту», поэтому пропусков нет по построению.
"""
import math

import numpy as np
import pandas as pd

from src.features._util import by_card, ewma_prior, haversine_km, hours, prior_count, prior_sum

PREFIX = "a_"
ALPHA = 20.0      # сила сглаживания долей к популяции (A1, A2)
K_AMT = 10.0      # сила сглаживания суммы к популяции категории (A3)
LN2 = math.log(2)

FEATURES = [
    "a_cat_bits", "a_time_bits", "a_amt_z", "a_amt_up", "a_amt_down", "a_surprise_total",
    "a_cat_x_amt", "a_time_x_amt", "a_profile_log_n", "a_drift",
    "a_new_merchant", "a_geo_km",
]
INFO = ["a_info_cat_share", "a_info_time_share", "a_info_typical_amt", "a_info_n"]
MONOTONE: dict = {}
REASONS = {
    "a_cat_bits": "Клиент редко покупает в категории «{category}»: {cat_share:.0%} его прошлых операций",
    "a_time_bits": "Клиент почти не платит в это время суток ({time_band}): {time_share:.0%} его операций",
    "a_amt_z": "Сумма {amt:.0f} у.е. — в {amt_ratio:.1f} раза больше обычной для клиента в этой категории (~{typical:.0f} у.е.)",
    "a_amt_up": "Сумма {amt:.0f} у.е. — в {amt_ratio:.1f} раза больше обычной для клиента в этой категории (~{typical:.0f} у.е.)",
    "a_amt_down": "Нетипично маленькая сумма для клиента в этой категории ({amt:.2f} у.е.)",
    "a_surprise_total": "Операция совсем не похожа на обычное поведение клиента",
    "a_drift": "За последние дни клиент стал тратить заметно крупнее обычного",
    "a_profile_log_n": "Мало истории по карте ({n:.0f} операций) — профиль ещё не сложился",
    "a_new_merchant": "Первая покупка у этого продавца",
    "a_geo_km": "Продавец далеко от привычных мест клиента",
}
# Взаимодействия раскладываются на исходные причины (TASK_A, reasons.py).
REASON_PARTS = {"a_cat_x_amt": ["a_cat_bits", "a_amt_up"], "a_time_x_amt": ["a_time_bits", "a_amt_up"]}

TIME_BANDS = ["00–04", "04–08", "08–12", "12–16", "16–20", "20–24"]


def fit(train_df: pd.DataFrame) -> dict:
    x = np.log1p(train_df["amt"].astype("float64"))
    bucket = train_df["ts"].dt.hour // 4
    g = x.groupby(train_df["category"].astype("str"))
    d = haversine_km(train_df["lat"], train_df["long"], train_df["merch_lat"], train_df["merch_long"])
    return {
        "p_cat": train_df["category"].astype("str").value_counts(normalize=True).to_dict(),
        "p_time": bucket.value_counts(normalize=True).to_dict(),
        "mu_cat": g.mean().to_dict(),
        "var_cat": g.var(ddof=0).to_dict(),
        "mu_all": float(x.mean()),
        "var_all": float(x.var(ddof=0)),
        "geo_median": float(np.median(d)),
    }


def _smoothed_bits(n_key, n_all, p_pop):
    p = (n_key + ALPHA * p_pop) / (n_all + ALPHA)
    return -np.log2(p), p


def transform(df: pd.DataFrame, state: dict) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    cat = df["category"].astype("str")
    w = pd.DataFrame({"cc_num": df["cc_num"], "ts": df["ts"], "cat": cat, "merchant": df["merchant"],
                      "tb": (df["ts"].dt.hour // 4).astype("int8")}, index=df.index)
    eps = 1e-4
    n = prior_count(w, ["cc_num"])

    # A1. Неожиданность категории.
    p_pop_cat = cat.map(state["p_cat"]).astype("float64").fillna(eps)
    out["a_cat_bits"], cat_share = _smoothed_bits(prior_count(w, ["cc_num", "cat"]), n, p_pop_cat)

    # A2. Неожиданность времени суток (6 интервалов по 4 часа).
    p_pop_tb = w["tb"].map(state["p_time"]).astype("float64").fillna(eps)
    out["a_time_bits"], time_share = _smoothed_bits(prior_count(w, ["cc_num", "tb"]), n, p_pop_tb)

    # A3. Отклонение суммы внутри категории со сжатием к популяции категории.
    x = np.log1p(df["amt"].astype("float64").clip(lower=0))
    n_cc = prior_count(w, ["cc_num", "cat"])
    s1 = prior_sum(w, x, ["cc_num", "cat"])
    s2 = prior_sum(w, x * x, ["cc_num", "cat"])
    mu_pop = cat.map(state["mu_cat"]).astype("float64").fillna(state["mu_all"])
    var_pop = cat.map(state["var_cat"]).astype("float64").fillna(state["var_all"])
    ss_within = (s2 - np.where(n_cc > 0, s1 * s1 / n_cc.replace(0, 1), 0.0)).clip(lower=0)
    mu = (s1 + K_AMT * mu_pop) / (n_cc + K_AMT)
    sigma = np.sqrt((ss_within + K_AMT * var_pop) / (n_cc + K_AMT)).clip(lower=0.05)
    z = ((x - mu) / sigma).clip(-10, 10)
    out["a_amt_z"] = z

    # A4. Отклонение вверх и вниз отдельно: линейная модель не умеет «опасно в одну сторону».
    out["a_amt_up"] = z.clip(lower=0)
    out["a_amt_down"] = (-z).clip(lower=0)

    # A5. Единая шкала странности.
    out["a_surprise_total"] = out["a_cat_bits"] + out["a_time_bits"] + out["a_amt_up"] / LN2

    # A6. Взаимодействия для линейной модели.
    out["a_cat_x_amt"] = out["a_cat_bits"] * out["a_amt_up"]
    out["a_time_x_amt"] = out["a_time_bits"] * out["a_amt_up"]

    # A7. Надёжность профиля.
    out["a_profile_log_n"] = np.log1p(n)

    # A8. Сдвиг привычек: короткое EWMA против длинного (по прошлым операциям карты).
    order = by_card(df)
    card_o = df["cc_num"].to_numpy()[order]
    t_o = hours(df["ts"])[order]
    x_o = x.to_numpy()[order]
    short = np.empty(len(df))
    long_ = np.empty(len(df))
    short[order] = ewma_prior(card_o, t_o, x_o, halflife_h=72.0)
    long_[order] = ewma_prior(card_o, t_o, x_o, halflife_h=24.0 * 60)
    out["a_drift"] = np.nan_to_num(short - long_, nan=0.0)

    # A9 (контроль). Первая покупка у мерчанта.
    out["a_new_merchant"] = (prior_count(w, ["cc_num", "merchant"]) == 0).astype("float64")

    # A10 (контроль). Расстояние от мерчанта до центра прошлых мерчантов карты.
    n_safe = n.replace(0, np.nan)
    c_lat = prior_sum(w, df["merch_lat"].astype("float64"), ["cc_num"]) / n_safe
    c_lon = prior_sum(w, df["merch_long"].astype("float64"), ["cc_num"]) / n_safe
    geo = haversine_km(c_lat, c_lon, df["merch_lat"], df["merch_long"])
    out["a_geo_km"] = np.nan_to_num(geo, nan=state["geo_median"])

    # Служебные поля для текста причин (в модель не идут).
    out["a_info_cat_share"] = cat_share
    out["a_info_time_share"] = time_share
    out["a_info_typical_amt"] = np.expm1(mu)
    out["a_info_n"] = n
    return out.astype("float64")
