"""Блок E — «Эпизод захвата карты» (неделя 2, reports/week2/3_error_analysis.md).

Откуда блок. Разбор эпизодов показал: мошенничество в данных — это двухсуточный захват карты
(≈10 операций, ночные волны 00–03 и вечерние 22–23, крупные суммы), а обычные операции владельца
на эти двое суток пропадают. Ложные срабатывания v1 — наоборот, одиночная крупная покупка
честного клиента на фоне его обычной жизни.

Поэтому признаки смотрят на окно 48 часов (длина эпизода), а не на «сессию до 3 часов паузы»
блока B: вечерняя и ночная волны одного эпизода разделены паузой до 20 часов, и сессия B
между ними обрывается.

Всё — по операциям карты строго раньше текущей (операции с тем же временем друг друга не видят).
Метки не используются.
"""
import numpy as np
import pandas as pd

from src.features._util import by_card, hours

PREFIX = "e_"
WINDOW_H = 48.0       # длина эпизода в данных: 97% эпизодов укладываются в 2 календарных дня
BIG_AMT = 200.0       # «крупная» операция: 78% операций эпизода и 98% его денег
M_USUAL = 7.0         # сглаживание обычного темпа «будничных» операций карты к популяции, дней
NO_BIG_H = 24.0 * 60  # «крупных операций не было» = 60 дней

FEATURES = [
    "e_big_48h", "e_night_48h", "e_cats_48h", "e_amt_48h_log", "e_h_since_big",
    "e_big_rate_hist", "e_usual_48h", "e_usual_ratio",
]
INFO = ["e_info_usual_exp"]
REASONS = {
    "e_big_48h": "За двое суток по карте уже {e_big:.0f} крупных операций",
    "e_night_48h": "За двое суток уже {e_night:.0f} ночных операций",
    "e_cats_48h": "За двое суток покупки в {e_cats:.0f} разных категориях",
    "e_amt_48h_log": "За двое суток по карте списано около {e_amt:.0f} у.е.",
    "e_h_since_big": "Предыдущая крупная операция была совсем недавно",
    "e_big_rate_hist": "Клиент обычно не делает крупных покупок",
    "e_usual_48h": "Обычные повседневные покупки клиента пропали",
    "e_usual_ratio": "Обычные повседневные покупки клиента пропали",
}


def _usual(df: pd.DataFrame) -> np.ndarray:
    """«Будничная» операция владельца: небольшая сумма днём (6–21 ч)."""
    h = df["ts"].dt.hour.to_numpy()
    return ((df["amt"].to_numpy() < 100) & (h >= 6) & (h <= 21)).astype("float64")


def fit(train_df: pd.DataFrame) -> dict:
    big = (train_df["amt"].to_numpy() >= BIG_AMT).mean()
    usual = _usual(train_df)
    g = pd.DataFrame({"cc": train_df["cc_num"].to_numpy(), "ts": train_df["ts"].to_numpy(), "u": usual}) \
        .groupby("cc").agg(u=("u", "sum"), lo=("ts", "min"), hi=("ts", "max"))
    days = ((g["hi"] - g["lo"]).dt.total_seconds() / 86400).clip(lower=1)
    return {"big_rate_pop": float(big), "usual_per_day_pop": float(np.median(g["u"] / days))}


def transform(df: pd.DataFrame, state: dict) -> pd.DataFrame:
    order = by_card(df)
    card_raw = df["cc_num"].to_numpy()[order]
    card = pd.factorize(card_raw)[0].astype("float64")
    t = hours(df["ts"])[order]
    amt = df["amt"].to_numpy(dtype="float64")[order]
    hour = df["ts"].dt.hour.to_numpy()[order]
    night = ((hour >= 22) | (hour <= 3)).astype("float64")
    big = (amt >= BIG_AMT).astype("float64")
    usual = _usual(df)[order]
    cat = pd.factorize(df["category"].astype("str"))[0][order]
    n = len(t)

    # Ключ «карта, время» возрастает по строкам; searchsorted даёт границы окон без циклов.
    key = card * 1e7 + (t - t.min())
    vis = np.searchsorted(key, key, side="left")             # строки [.., vis) строго раньше
    lo = np.searchsorted(key, key - WINDOW_H, side="left")   # ... и не раньше чем 48 ч назад
    start = np.searchsorted(card, card, side="left")         # первая строка карты

    def cs(x):
        return np.concatenate([[0.0], np.cumsum(x)])

    c_big, c_night, c_usual, c_amt = cs(big), cs(night), cs(usual), cs(amt)
    o = {}
    o["e_big_48h"] = c_big[vis] - c_big[lo]
    o["e_night_48h"] = c_night[vis] - c_night[lo]
    amt48 = c_amt[vis] - c_amt[lo]
    o["e_amt_48h_log"] = np.log1p(amt48)

    cats = np.zeros(n)
    for k in np.unique(cat):
        ck = cs((cat == k).astype("float64"))
        cats += (ck[vis] - ck[lo]) > 0
    o["e_cats_48h"] = cats

    # Часы с последней крупной операции строго раньше.
    big_t = np.where(big > 0, t, np.nan)
    last_big = pd.Series(big_t).groupby(card).ffill().to_numpy()
    prev = vis - 1
    has_prev = prev >= start
    lb = np.where(has_prev, last_big[np.clip(prev, 0, None)], np.nan)
    o["e_h_since_big"] = np.where(np.isnan(lb), NO_BIG_H, np.minimum(t - lb, NO_BIG_H))

    prior_n = vis - start
    prior_big = c_big[vis] - c_big[start]
    a = 20.0
    o["e_big_rate_hist"] = (prior_big + a * state["big_rate_pop"]) / (prior_n + a)

    usual48 = c_usual[vis] - c_usual[lo]
    o["e_usual_48h"] = usual48
    prior_usual = c_usual[vis] - c_usual[start]
    days = np.maximum((t - t[start]) / 24.0, 0.0)
    rate = (prior_usual + M_USUAL * state["usual_per_day_pop"]) / (days + M_USUAL)
    exp48 = rate * WINDOW_H / 24.0
    o["e_usual_ratio"] = (usual48 + 1.0) / (exp48 + 1.0)
    o["e_info_usual_exp"] = exp48

    out = pd.DataFrame(index=df.index)
    inv = np.empty(n, dtype=np.int64)
    inv[order] = np.arange(n)
    for k, v in o.items():
        out[k] = np.asarray(v, dtype="float64")[inv]
    return out
