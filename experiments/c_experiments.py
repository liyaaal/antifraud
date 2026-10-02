"""Эксперименты блока C (TASK_C): задержка меток, обучение без меток, «учить деньгам или считать деньгами»,
признаки среды для линейной модели.

python -m experiments.c_experiments
"""
import numpy as np
import pandas as pd

from src.evaluate import DEFAULTS, feature_list, run
from src.features import context
from src.pipeline import load_dataset
from tests.test_no_future_leak import compare
from src.data import load_train
from src.split import assign, boundaries


def cfg_of(**kw):
    return {**DEFAULTS, "author": "C", **kw}


df, part, X, states, b = load_dataset(["base", "c"])
base_feats = feature_list(cfg_of(blocks=["base"]))
c_feats = feature_list(cfg_of(blocks=["base", "c"]))

# 1. Признаки среды на линейной модели: деревья видят категорию×час сами, а LogReg — нет.
run(cfg_of(name="c_logreg_base", blocks=["base"], model="logreg", calibration="isotonic", policy="ev_cap"),
    base_feats, df, part, X, note="LogReg без признаков среды")
run(cfg_of(name="c_logreg", blocks=["base", "c"], model="logreg", calibration="isotonic", policy="ev_cap"),
    c_feats, df, part, X, note="LogReg + признаки среды C")

# 2. Задержка меток: 30 дней (реализм) против 1 дня (метки «уже завтра»).
for delay in [1, 30]:
    context.DELAY_DAYS = delay
    st = context.fit(df[part == "train"])
    fc = context.transform(df, st)
    X2 = X.copy()
    X2[context.FEATURES] = fc[context.FEATURES]
    run(cfg_of(name=f"c_delay{delay}", blocks=["base", "c"], model="lgbm", sample_weight="cost",
               calibration="isotonic", policy="ev_cap"), c_feats, df, part, X2, added=f"D={delay}",
        note="задержка меток")
context.DELAY_DAYS = 30

# 2б. Задержка 0 (метки того же дня) — это уже утечка: тест обязан её поймать.
raw = load_train()
rawpart = assign(raw.ts, boundaries(raw.ts))
context.DELAY_DAYS = 0
st0 = context.fit(raw[rawpart == "train"])
cards = np.random.default_rng(7).choice(raw.cc_num.unique(), size=150, replace=False)
sub = raw[raw.cc_num.isin(cards)].reset_index(drop=True)
T = sub.ts.quantile(0.5)
full, cut = context.transform(sub, st0), context.transform(sub[sub.ts <= T], st0)
ok, diff = compare(cut["c_risk_cat_hour"], full.loc[sub.ts <= T, "c_risk_cat_hour"])
print(f"D=0: тест на утечку {'прошёл (ПЛОХО)' if ok else 'поймал утечку (как и должен)'}; max_diff={diff:.4f}")
context.DELAY_DAYS = 30

# 3. Без учителя: Isolation Forest на сырых полях и перцентиле суммы.
run(cfg_of(name="c_iforest", blocks=["base", "c"], model="iforest", policy="ev_cap", calibration="isotonic"),
    base_feats + ["c_amt_pct_cat"], df, part, X, note="без меток: необычное ≠ мошенническое")
run(cfg_of(name="c_iforest_topp", blocks=["base", "c"], model="iforest", policy="top_p"),
    base_feats + ["c_amt_pct_cat"], df, part, X, note="без меток, ранжирование по аномальности")

# 4. «Учить деньгам или считать деньгами» — на базовых полях, чтобы видеть эффект решения, а не признаков.
for name, w, cal, pol in [("c_money_1_topp", "none", "none", "top_p"),
                          ("c_money_2_ev", "none", "isotonic", "ev_cap"),
                          ("c_money_3_costw_ev", "cost", "isotonic", "ev_cap"),
                          ("c_money_4_costw_topp", "cost", "none", "top_p"),
                          ("c_money_5_ev_thr", "none", "isotonic", "ev_thr")]:
    run(cfg_of(name=name, blocks=["base"], model="lgbm", sample_weight=w, calibration=cal, policy=pol),
        base_feats, df, part, X, note="учить деньгам или считать деньгами")
