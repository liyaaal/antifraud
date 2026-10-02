"""Экономика решения: стоимость, дневной лимит аналитиков, политики (CLAUDE.md, раздел 4).

Операция, отправленная аналитику, стоит 3 у.е. за проверку; если она оказалась честной —
ещё 25 у.е. за задержку добросовестного клиента. Пропущенный фрод стоит amt + 5.
"""
import numpy as np
import pandas as pd

REVIEW = 3.0
FALSE_BLOCK = 25.0
MISS_EXTRA = 5.0
CAPACITY = 0.003


def daily_cap(day: pd.Series, capacity: float = CAPACITY) -> pd.Series:
    """k_d = floor(capacity · n_d) для каждой строки."""
    n = day.map(day.value_counts())
    return np.floor(capacity * n).astype(int)


def top_k_per_day(day: pd.Series, score: np.ndarray, eligible=None, capacity: float = CAPACITY) -> np.ndarray:
    """Каждый день отправить не больше k_d операций с наибольшим score (только из eligible)."""
    s = pd.Series(np.asarray(score, dtype="float64"), index=day.index)
    if eligible is not None:
        s = s.where(np.asarray(eligible), -np.inf)
    order = pd.DataFrame({"day": day.values, "s": s.values}).sort_values(["day", "s"], ascending=[True, False],
                                                                           kind="mergesort")
    rank = order.groupby("day").cumcount()
    cap = daily_cap(order["day"], capacity)
    chosen = (rank < cap) & np.isfinite(order["s"])
    out = np.zeros(len(day), dtype="int8")
    out[order.index[chosen.to_numpy()]] = 1
    return out


def expected_value(p, amt, false_block: float = FALSE_BLOCK):
    """Сколько денег в среднем спасает проверка операции: p·(amt+5) − 3 − (1−p)·25."""
    p = np.asarray(p, dtype="float64")
    amt = np.asarray(amt, dtype="float64")
    return p * (amt + MISS_EXTRA) - REVIEW - (1 - p) * false_block


def decide(policy: str, day: pd.Series, p, amt, capacity: float = CAPACITY, params: dict | None = None,
           false_block: float = FALSE_BLOCK) -> np.ndarray:
    params = params or {}
    if policy == "none":
        return np.zeros(len(day), dtype="int8")
    if policy == "top_p":
        return top_k_per_day(day, p, capacity=capacity)
    if policy == "rule_amt":
        return top_k_per_day(day, amt, capacity=capacity)
    if policy == "ev_cap":
        ev = expected_value(p, amt, false_block)
        return top_k_per_day(day, ev, eligible=ev > 0, capacity=capacity)
    if policy == "ev_thr":
        # Потоковый вариант: фиксированный порог по EV (подобран на valid) + жёсткий лимит как предохранитель.
        ev = expected_value(p, amt, false_block)
        return top_k_per_day(day, ev, eligible=ev > params["ev_threshold"], capacity=capacity)
    raise ValueError(policy)


def fit_ev_threshold(day: pd.Series, p, amt, target_rate: float = 0.0025, false_block: float = FALSE_BLOCK) -> float:
    """Порог по EV, при котором в среднем отправляется target_rate операций (подбирается на valid)."""
    ev = expected_value(p, amt, false_block)
    thr = float(np.quantile(ev, 1 - target_rate))
    return max(thr, 0.0)


def costs(y, amt, decision, day: pd.Series, fraud_weight: float = 1.0, false_block: float = FALSE_BLOCK) -> dict:
    """Деньги и метрики. fraud_weight > 1 — стресс-тест «фрода больше» (вес строк фрода)."""
    y = np.asarray(y).astype(bool)
    d = np.asarray(decision).astype(bool)
    amt = np.asarray(amt, dtype="float64")
    w = np.where(y, fraud_weight, 1.0)
    miss_cost = amt + MISS_EXTRA
    row_loss = np.where(d, np.where(y, REVIEW, REVIEW + false_block), np.where(y, miss_cost, 0.0)) * w
    row_none = np.where(y, miss_cost, 0.0) * w
    per_day = pd.DataFrame({"day": day.values, "loss": row_loss, "none": row_none}).groupby("day").sum()
    per_day["savings"] = per_day["none"] - per_day["loss"]
    n_days = len(per_day)
    caps = daily_cap(day)
    flagged_per_day = pd.Series(d, index=day.index).groupby(day).sum()
    return {
        "loss_none": float(row_none.sum()),
        "loss": float(row_loss.sum()),
        "savings": float(row_none.sum() - row_loss.sum()),
        "recall_cnt": float((w * (d & y)).sum() / max((w * y).sum(), 1e-9)),
        "recall_amt": float((w * amt * (d & y)).sum() / max((w * amt * y).sum(), 1e-9)),
        "precision": float((d & y).sum() / max(d.sum(), 1)),
        "flagged_per_day": float(d.sum() / max(n_days, 1)),
        "cap_violated": bool((flagged_per_day > caps.groupby(day).first()).any()),
        "per_day_savings": per_day["savings"],
    }


def paired_bootstrap(delta_per_day: pd.Series, n: int = 2000, seed: int = 42) -> tuple[float, float]:
    """90% интервал для суммарной разницы в деньгах: дни valid пересэмплируются с возвращением."""
    rng = np.random.default_rng(seed)
    v = delta_per_day.to_numpy()
    idx = rng.integers(0, len(v), size=(n, len(v)))
    sums = v[idx].sum(axis=1)
    return float(np.quantile(sums, 0.05)), float(np.quantile(sums, 0.95))
