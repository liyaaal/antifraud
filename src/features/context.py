"""Блок C — «Решение в деньгах»: риск среды с задержкой меток (tasks/TASK_C.md, часть 1).

Метка «это был фрод» в банке приходит не сразу (жалоба клиента, чарджбэк). Поэтому для
операции дня d используются только метки операций дней ≤ d − DELAY_DAYS.

Строки периода train: доли считаются накопительно с задержкой по самим данным.
Строки после train (valid, holdout, score.py): таблицы заморожены на момент конца train
с той же задержкой — ровно то, что будет у модели в эксплуатации.
"""
import numpy as np
import pandas as pd

PREFIX = "c_"
DELAY_DAYS = 30   # метки доступны только за дни ≤ d − 30
M_SMOOTH = 200.0  # m-оценка: доля прижимается к средней, пока наблюдений мало
PRIOR = 0.005     # априорная доля фрода «меньше 1%» из ТЗ — пока своих меток ещё нет

FEATURES = ["c_risk_cat_hour", "c_risk_cat_amtbin", "c_risk_age_cat", "c_risk_merchant", "c_amt_pct_cat"]
INFO = ["c_info_x_cat_hour", "c_info_x_cat_amtbin", "c_info_x_age_cat", "c_info_x_merchant"]
MONOTONE: dict = {}
REASONS = {
    "c_risk_cat_hour": "Покупки «{category}» в это время суток — в {x_cat_hour:.0f} раз чаще мошенничество, чем в среднем",
    "c_risk_cat_amtbin": "Такие суммы в категории «{category}» — в {x_cat_amtbin:.0f} раз чаще мошенничество, чем в среднем",
    "c_risk_age_cat": "Для клиентов этого возраста категория «{category}» — в {x_age_cat:.1f} раза рискованнее средней",
    "c_risk_merchant": "У этого продавца мошенничество в {x_merchant:.1f} раза чаще среднего",
    "c_amt_pct_cat": "Сумма больше, чем у {amt_pct:.0%} покупок в категории «{category}»",
}
AGE_BINS = [0, 25, 40, 60, 75, 200]
KEYS = {"cat_hour": None, "cat_amtbin": None, "age_cat": None, "merchant": None}


def _keys(df: pd.DataFrame, state: dict) -> dict:
    cat = df["category"].astype("str")
    tb = (df["ts"].dt.hour // 4).astype("str")
    amt = df["amt"].to_numpy(dtype="float64")
    amtbin = np.zeros(len(df), dtype="int64")
    for c, edges in state["amt_edges"].items():
        m = (cat == c).to_numpy()
        amtbin[m] = np.searchsorted(edges, amt[m], side="right")
    age = pd.cut(df["age"], AGE_BINS, right=False, labels=False).fillna(-1).astype("int64").astype("str")
    return {
        "cat_hour": cat + "|" + tb,
        "cat_amtbin": cat + "|" + pd.Series(amtbin, index=df.index).astype("str"),
        "age_cat": age + "|" + cat,
        "merchant": df["merchant"].astype("str"),
    }


def _frozen_table(key: pd.Series, y: pd.Series) -> dict:
    g = pd.DataFrame({"k": key, "y": y}).groupby("k")["y"].agg(["sum", "size"])
    return {k: (float(r["sum"]), float(r["size"])) for k, r in g.iterrows()}


def fit(train_df: pd.DataFrame) -> dict:
    cat = train_df["category"].astype("str")
    amt_edges, amt_sorted = {}, {}
    for c, s in train_df["amt"].astype("float64").groupby(cat):
        amt_edges[c] = np.unique(np.quantile(s, np.linspace(0.1, 0.9, 9)))
        amt_sorted[c] = np.sort(s.to_numpy())
    state = {"amt_edges": amt_edges, "amt_sorted": amt_sorted, "delay": DELAY_DAYS,
             "train_end": train_df["ts"].max()}
    day = train_df["ts"].dt.normalize()
    known = day <= day.max() - pd.Timedelta(days=DELAY_DAYS)
    keys = _keys(train_df, state)
    y = train_df["is_fraud"].astype("float64")
    state["p_global"] = float(y[known].mean())
    state["tables"] = {name: _frozen_table(k[known], y[known]) for name, k in keys.items()}
    return state


def _delayed_counts(key: pd.Series, day: pd.Series, y: pd.Series, delay: int):
    """Для каждой строки: число фродов и операций с тем же ключом за дни ≤ day − delay."""
    daily = pd.DataFrame({"k": key.to_numpy(), "d": day.to_numpy(), "y": y.to_numpy()}).groupby(["k", "d"])["y"].agg(
        ["sum", "size"]).reset_index()
    daily[["cf", "cn"]] = daily.groupby("k")[["sum", "size"]].cumsum()
    daily = daily.sort_values("d")
    left = pd.DataFrame({"k": key.to_numpy(), "d": (day - pd.Timedelta(days=delay)).to_numpy(),
                         "row": np.arange(len(key))}).sort_values("d")
    m = pd.merge_asof(left, daily[["k", "d", "cf", "cn"]], on="d", by="k", direction="backward",
                      allow_exact_matches=True)
    m = m.sort_values("row")
    return m["cf"].fillna(0).to_numpy(), m["cn"].fillna(0).to_numpy()


def transform(df: pd.DataFrame, state: dict) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    keys = _keys(df, state)
    delay = state["delay"]
    day = df["ts"].dt.normalize()
    has_labels = "is_fraud" in df.columns
    live = (df["ts"] <= state["train_end"]).to_numpy() & has_labels   # период train: накопление с задержкой

    pg_frozen = state["p_global"]
    if live.any():
        const = pd.Series("all", index=df.index)
        y = df["is_fraud"].astype("float64") if has_labels else pd.Series(0.0, index=df.index)
        gf, gn = _delayed_counts(const[live], day[live], y[live], delay)
        # Для строк train средняя доля тоже только по прошлым меткам (с задержкой), без знания будущего.
        pg_live = (gf + M_SMOOTH * PRIOR) / (gn + M_SMOOTH)
    pg = np.full(len(df), pg_frozen)
    if live.any():
        pg[live] = pg_live

    for name, key in keys.items():
        f = np.zeros(len(df))
        n = np.zeros(len(df))
        tbl = state["tables"][name]
        fr = key.map(lambda k: tbl.get(k, (0.0, 0.0)))
        f[:] = [v[0] for v in fr]
        n[:] = [v[1] for v in fr]
        if live.any():
            lf, ln = _delayed_counts(key[live], day[live], y[live], delay)
            f[live], n[live] = lf, ln
        rate = (f + M_SMOOTH * pg) / (n + M_SMOOTH)
        ratio = rate / pg
        out[f"c_risk_{name}"] = np.log(ratio)
        out[f"c_info_x_{name}"] = ratio

    # C5. Перцентиль суммы среди всех покупок категории (без меток).
    cat = df["category"].astype("str")
    pct = np.full(len(df), 0.5)
    amt = df["amt"].to_numpy(dtype="float64")
    for c, arr in state["amt_sorted"].items():
        m = (cat == c).to_numpy()
        pct[m] = np.searchsorted(arr, amt[m], side="right") / len(arr)
    out["c_amt_pct_cat"] = pct
    return out.astype("float64")
