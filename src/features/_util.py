"""Общие кирпичики для признаков по истории. Всё считается строго по прошлому.

Операции одной карты с одинаковым временем друг друга не видят: для «ничьих» по времени
берётся значение первой строки группы (card, ts).
"""
import math

import numpy as np
import pandas as pd


def _tie_first(values: pd.Series, df: pd.DataFrame, keys: list[str]) -> pd.Series:
    return values.groupby([df[k] for k in keys] + [df["ts"]], sort=False, observed=True).transform("first")


def prior_count(df: pd.DataFrame, keys: list[str]) -> pd.Series:
    """Сколько операций с теми же keys было строго раньше."""
    c = df.groupby(keys, sort=False, observed=True).cumcount().astype("float64")
    return _tie_first(c, df, keys)


def prior_sum(df: pd.DataFrame, x: pd.Series, keys: list[str]) -> pd.Series:
    """Сумма x по операциям с теми же keys строго раньше."""
    cs = x.groupby([df[k] for k in keys], sort=False, observed=True).cumsum() - x
    return _tie_first(cs, df, keys)


def hours(ts: pd.Series) -> np.ndarray:
    return ts.to_numpy().astype("datetime64[s]").astype("int64") / 3600.0


def ewma_prior(card: np.ndarray, t: np.ndarray, x: np.ndarray, halflife_h: float) -> np.ndarray:
    """Экспоненциально взвешенное среднее x по прошлым операциям карты (вес 1/2 каждые halflife_h часов).

    Массивы упорядочены по (card, t). Нет истории -> NaN.
    """
    lam = math.log(2) / halflife_h
    out = np.full(len(t), np.nan)
    N = D = 0.0
    last_t = cur_t = None
    pend_x = pend_c = 0.0
    prev_card = None
    exp = math.exp
    for i in range(len(t)):
        ci, ti = card[i], t[i]
        if ci != prev_card:
            N = D = 0.0
            last_t = cur_t = None
            pend_x = pend_c = 0.0
            prev_card = ci
        if cur_t is None or ti != cur_t:
            if cur_t is not None:
                dec = exp(-(cur_t - last_t) * lam) if last_t is not None else 1.0
                N = N * dec + pend_x
                D = D * dec + pend_c
                last_t = cur_t
            pend_x = pend_c = 0.0
            cur_t = ti
        if D > 0:
            out[i] = N / D
        pend_x += x[i]
        pend_c += 1.0
    return out


def decayed_sums(card: np.ndarray, t: np.ndarray, x: np.ndarray, tau_h: float) -> np.ndarray:
    """Σ x_j · exp(−(t_i − t_j)/τ) по прошлым операциям карты (строго раньше t_i).

    При x = 1 это затухающая интенсивность — «сколько операций было недавно».
    """
    out = np.zeros(len(t))
    S = 0.0
    last_t = cur_t = None
    pend = 0.0
    prev_card = None
    exp = math.exp
    for i in range(len(t)):
        ci, ti = card[i], t[i]
        if ci != prev_card:
            S = 0.0
            last_t = cur_t = None
            pend = 0.0
            prev_card = ci
        if cur_t is None or ti != cur_t:
            if cur_t is not None:
                S = (S * exp(-(cur_t - last_t) / tau_h) if last_t is not None else 0.0) + pend
                last_t = cur_t
            pend = 0.0
            cur_t = ti
        out[i] = S * exp(-(ti - last_t) / tau_h) if last_t is not None else 0.0
        pend += x[i]
    return out


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(v, dtype="float64")) for v in (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def by_card(df: pd.DataFrame):
    """Порядок строк по (карта, время) и обратная перестановка."""
    order = np.lexsort((df["trans_num"].to_numpy(), df["ts"].to_numpy(), df["cc_num"].to_numpy()))
    return order
