"""Блок B — «Атака как всплеск»: интенсивность и сессии (tasks/TASK_B.md).

Смотрим не на что тратят, а на ритм операций карты. Всё — по операциям строго раньше текущей.
"""
import numpy as np
import pandas as pd

from src.features._util import by_card, decayed_sums, hours

PREFIX = "b_"
SESSION_GAP_H = 3.0     # новая сессия, если пауза больше 3 часов (B5)
M_RATE = 7.0            # сглаживание обычного темпа карты к популяции, дней (B4)

FEATURES = [
    "b_gap_log_h", "b_is_first", "b_int_1h", "b_int_24h", "b_amt_int_24h", "b_act_ratio",
    "b_sess_pos", "b_sess_cum_amt", "b_sess_escalation", "b_sess_night_share", "b_sess_cat_n",
    "b_amt_rank10", "b_online_streak", "b_cnt_24h_window",
]
INFO = ["b_info_sess_cnt", "b_info_rate"]
MONOTONE = {"b_int_1h": 1, "b_int_24h": 1, "b_amt_int_24h": 1, "b_act_ratio": 1,
            "b_sess_pos": 1, "b_sess_cum_amt": 1}
REASONS = {
    "b_gap_log_h": "Операция почти сразу после предыдущей ({gap_min:.0f} мин)",
    "b_int_1h": "Серия операций за последний час",
    "b_int_24h": "Много операций за последние сутки",
    "b_amt_int_24h": "За последние сутки по карте уже потрачено ~{amt_24h:.0f} у.е.",
    "b_act_ratio": "Карта в {act_ratio:.1f} раза активнее, чем обычно для этого клиента",
    "b_sess_pos": "Уже {sess_pos:.0f}-я операция подряд без перерыва",
    "b_sess_cum_amt": "В этой серии уже потрачено {sess_cum:.0f} у.е.",
    "b_sess_escalation": "Сумма резко выросла внутри серии операций",
    "b_sess_night_share": "Серия операций ночью",
    "b_sess_cat_n": "В серии покупки в {sess_cat_n:.0f} разных категориях",
    "b_amt_rank10": "Сумма больше, чем во всех последних операциях клиента",
    "b_online_streak": "{streak:.0f} онлайн-покупок подряд",
    "b_cnt_24h_window": "Много операций за последние сутки",
}


def fit(train_df: pd.DataFrame) -> dict:
    g = train_df.groupby("cc_num")["ts"].agg(["size", "min", "max"])
    span_days = ((g["max"] - g["min"]).dt.total_seconds() / 86400).clip(lower=1)
    return {"rate_pop": float(np.median(g["size"] / span_days))}


def _loops(card, t, amt, night, online, cat):
    """Всё, что считается одним проходом по карте в порядке времени."""
    n = len(t)
    gap = np.full(n, np.nan)
    first_t = np.empty(n)
    prior_n = np.zeros(n)
    sess_pos = np.ones(n)
    sess_cum = np.zeros(n)
    sess_min = np.full(n, np.nan)
    sess_night = np.zeros(n)
    sess_cats = np.zeros(n)
    rank10 = np.full(n, 0.5)
    streak = np.zeros(n)

    prev_card = None
    for i in range(n):
        if card[i] != prev_card:
            prev_card = card[i]
            start = i                  # первая строка карты
            c_first = t[i]
            last_t = None              # время последней «видимой» операции (строго раньше)
            vis = i                    # строки [start, vis) видны текущей строке
            s_start = i                # начало текущей сессии
            s_cum = 0.0
            s_min = np.inf
            s_night = 0.0
            s_cats = set()
            k_streak = 0
        # Сделать видимыми все операции карты строго раньше t[i] (ничьи по времени не видят друг друга).
        while vis < i and t[vis] < t[i]:
            j = vis
            # Операция j видна: сначала решаем, открывает ли она новую сессию.
            if last_t is not None and t[j] - last_t > SESSION_GAP_H:
                s_start, s_cum, s_min, s_night, s_cats = j, 0.0, np.inf, 0.0, set()
            s_cum += amt[j]
            s_min = min(s_min, amt[j])
            s_night += night[j]
            s_cats.add(cat[j])
            k_streak = k_streak + 1 if online[j] else 0
            last_t = t[j]
            vis += 1
        first_t[i] = c_first
        prior_n[i] = vis - start
        if last_t is None:
            streak[i] = 0
            continue
        gap[i] = t[i] - last_t
        streak[i] = k_streak
        lo = max(start, vis - 10)
        rank10[i] = float(np.mean(amt[lo:vis] < amt[i]))
        if gap[i] > SESSION_GAP_H:        # текущая операция открывает новую сессию
            sess_night[i] = night[i]
            sess_cats[i] = 1
            continue
        pos = vis - s_start
        sess_pos[i] = pos + 1
        sess_cum[i] = s_cum
        sess_min[i] = s_min
        sess_night[i] = (s_night + night[i]) / (pos + 1)
        sess_cats[i] = len(s_cats | {cat[i]})
    sess_night = np.where(sess_pos == 1, night, sess_night)
    sess_cats = np.where(sess_pos == 1, 1, sess_cats)
    return gap, first_t, prior_n, sess_pos, sess_cum, sess_min, sess_night, sess_cats, rank10, streak


def transform(df: pd.DataFrame, state: dict) -> pd.DataFrame:
    order = by_card(df)
    card = df["cc_num"].to_numpy()[order]
    t = hours(df["ts"])[order]
    amt = df["amt"].to_numpy(dtype="float64")[order]
    hour = df["ts"].dt.hour.to_numpy()[order]
    night = ((hour >= 22) | (hour <= 3)).astype("float64")
    online = df["category"].astype("str").str.endswith("_net").to_numpy()[order]
    cat = pd.factorize(df["category"].astype("str"))[0][order]

    (gap, first_t, prior_n, sess_pos, sess_cum, sess_min, sess_night, sess_cats,
     rank10, streak) = _loops(card, t, amt, night, online, cat)

    o = {}
    o["b_gap_log_h"] = np.log1p(gap)
    o["b_is_first"] = (prior_n == 0).astype("float64")
    o["b_int_1h"] = decayed_sums(card, t, np.ones(len(t)), tau_h=1.0)
    o["b_int_24h"] = decayed_sums(card, t, np.ones(len(t)), tau_h=24.0)
    o["b_amt_int_24h"] = decayed_sums(card, t, amt, tau_h=24.0)
    days = (t - first_t) / 24.0
    rate = (prior_n + M_RATE * state["rate_pop"]) / (days + M_RATE)
    o["b_act_ratio"] = o["b_int_24h"] / rate
    o["b_sess_pos"] = sess_pos
    o["b_sess_cum_amt"] = sess_cum
    o["b_sess_escalation"] = np.where(sess_pos > 1, np.log(np.maximum(amt, 0.01) / np.maximum(sess_min, 0.01)), 0.0)
    o["b_sess_night_share"] = sess_night
    o["b_sess_cat_n"] = sess_cats
    o["b_amt_rank10"] = np.where(prior_n == 0, 0.5, rank10)
    o["b_online_streak"] = streak

    # B10 (контроль): классическое окно «число операций за 24 часа», строго раньше текущей.
    key = pd.factorize(card)[0] * 1e7 + t
    o["b_cnt_24h_window"] = (np.searchsorted(key, key, side="left")
                             - np.searchsorted(key, key - 24.0, side="left")).astype("float64")

    o["b_info_sess_cnt"] = sess_pos
    o["b_info_rate"] = rate
    out = pd.DataFrame(index=df.index)
    inv = np.empty(len(order), dtype=np.int64)
    inv[order] = np.arange(len(order))
    for k, v in o.items():
        out[k] = np.asarray(v, dtype="float64")[inv]
    return out
