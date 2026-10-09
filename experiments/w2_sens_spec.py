"""Неделя 2, раздел 6: чувствительность и специфичность как функция порога.

python -m experiments.w2_sens_spec --version final            # v1 на holdout (своя оценка)
python -m experiments.w2_sens_spec --version final_v2         # v2 на holdout
python -m experiments.w2_sens_spec --version final --scored data/cache/scored_v1_test.csv --tag test

Две «ручки», которыми может управлять банк:
  A) порог по вероятности без лимита — сколько операций в день придётся смотреть;
  B) лимит аналитиков (доля операций в сутки) при денежной политике ev_cap — как работает система.
Пишет reports/week2/tables/sens_spec_<version>_<tag>.md/.csv и график .png.
"""
import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from experiments.w2_common import W2, load_labeled
from experiments.w2_patterns import md_table, pct
from src.data import ROOT, load_train
from src.economics import costs, decide

THRESHOLDS = [0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 0.99, 0.999]
CAPS = [0.001, 0.002, 0.003, 0.005, 0.0075, 0.01, 0.015, 0.02]


def point(y, amt, day, d, label):
    y = y.astype(bool)
    d = d.astype(bool)
    n_days = day.nunique()
    c = costs(y, amt, d, day)
    return {"точка": label, "проверок в сутки": d.sum() / n_days, "задержано честных в сутки": (d & ~y).sum() / n_days,
            "задержано честных всего": int((d & ~y).sum()), "поймано фрод-операций": int((d & y).sum()),
            "чувствительность (шт)": (d & y).sum() / y.sum(), "чувствительность (деньги)": c["recall_amt"],
            "специфичность": (~d & ~y).sum() / (~y).sum(), "точность (precision)": (d & y).sum() / max(d.sum(), 1),
            "экономия, у.е.": c["savings"], "упущено фрода, у.е.": float((amt * (y & ~d)).sum())}


def table(df, p):
    y = df.is_fraud.to_numpy()
    amt = df.amt.to_numpy(dtype="float64")
    day = df.ts.dt.normalize()
    a = [point(y, amt, day, p >= t, f"p ≥ {t:g}") for t in THRESHOLDS]
    b = [point(y, amt, day, decide("ev_cap", day, p, amt, capacity=c), f"лимит {c:.2%}".replace(".", ",")) for c in CAPS]
    return pd.DataFrame(a), pd.DataFrame(b)


FMT = {"проверок в сутки": lambda v: f"{v:.1f}", "задержано честных в сутки": lambda v: f"{v:.2f}",
       "чувствительность (шт)": pct, "чувствительность (деньги)": pct,
       "специфичность": lambda v: f"{v:.3%}", "точность (precision)": pct}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="final")
    ap.add_argument("--scored", default=None, help="выход score.py на размеченном наборе (иначе holdout из preds)")
    ap.add_argument("--tag", default="holdout")
    a = ap.parse_args()
    if a.scored:
        df = load_labeled()
        s = pd.read_csv(ROOT / a.scored).set_index("trans_num").loc[df.trans_num]
        p = s.fraud_probability.to_numpy()
    else:
        df = load_train()
        pr = pd.read_parquet(ROOT / "reports" / "preds" / f"{a.version}_holdout.parquet")
        df = df.merge(pr, on="trans_num")
        p = df.p.to_numpy()
    ta, tb = table(df, p)
    name = f"sens_spec_{a.version}_{a.tag}"
    pd.concat([ta.assign(ручка="порог p"), tb.assign(ручка="лимит")]).to_csv(W2 / f"{name}.csv", index=False,
                                                                              encoding="utf-8")
    fr = df.is_fraud.mean()
    lines = [f"# Чувствительность и специфичность — {a.version}, {a.tag}", "",
             f"Операций {len(df):,}, дней {df.ts.dt.normalize().nunique()}, доля фрода {fr:.2%}.".replace(",", " "), "",
             "## A. Порог по вероятности (без лимита аналитиков)", "", md_table(ta, FMT), "",
             "## B. Лимит аналитиков (денежная политика ev_cap) — так работает система", "", md_table(tb, FMT)]
    # Чувствительность к допущению о цене задержки честного клиента (25 у.е. в неделе 1).
    day = df.ts.dt.normalize()
    amt = df.amt.to_numpy(dtype="float64")
    cs = []
    for fb in (10, 25, 50, 100):
        d = decide("ev_cap", day, p, amt, false_block=fb)
        c = costs(df.is_fraud, df.amt, d, day, false_block=fb)
        cs.append({"цена задержки честного": fb, "экономия, у.е.": c["savings"],
                   "ложных": int(((d == 1) & (df.is_fraud.to_numpy() == 0)).sum()),
                   "проверок в сутки": c["flagged_per_day"]})
    lines += ["", "## C. Чувствительность к цене задержки честного клиента", "",
              md_table(pd.DataFrame(cs), {"проверок в сутки": lambda v: f"{v:.2f}", "ложных": lambda v: f"{v:.0f}",
                                          "цена задержки честного": lambda v: f"{v:.0f}"})]
    (W2 / f"{name}.md").write_text("\n".join(lines), encoding="utf-8")

    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    for t, lab, m in [(ta, "порог p", "o-"), (tb, "лимит (ev_cap)", "s-")]:
        ax[0].plot(t["проверок в сутки"], t["чувствительность (деньги)"], m, label=f"{lab}: деньги")
        ax[0].plot(t["проверок в сутки"], t["чувствительность (шт)"], m, alpha=.45, label=f"{lab}: штуки")
        ax[1].plot(t["проверок в сутки"], t["задержано честных в сутки"], m, label=lab)
    from matplotlib.ticker import FixedLocator, NullLocator, ScalarFormatter
    for x in ax:
        x.set_xscale("log")
        x.xaxis.set_major_locator(FixedLocator([2, 3, 5, 7, 10, 15, 20, 30]))
        x.xaxis.set_minor_locator(NullLocator())
        x.xaxis.set_major_formatter(ScalarFormatter())
        x.set_xlabel("проверок в сутки (нагрузка на мониторинг)")
        x.grid(alpha=.3)
    wp = tb[tb["точка"].str.contains("0,30")].iloc[0]
    ax[0].axvline(wp["проверок в сутки"], color="k", ls=":", lw=1)
    ax[1].axvline(wp["проверок в сутки"], color="k", ls=":", lw=1)
    ax[0].set_ylabel("чувствительность")
    ax[1].set_ylabel("задержано честных клиентов в сутки")
    ax[0].legend(fontsize=7)
    ax[1].legend(fontsize=7)
    ax[0].set_title("Сколько фрода ловим")
    ax[1].set_title("Цена: честные клиенты")
    fig.suptitle(f"{a.version}, {a.tag}: пунктир — рабочая точка 0,3%")
    fig.tight_layout()
    fig.savefig(W2 / f"{name}.png", dpi=130)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
