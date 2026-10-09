"""Неделя 2, раздел 7: v1 и v2 на одном наборе — fraudTest (период, не использованный в первой приёмке).

Сначала обе версии прогоняются обычным score.py (см. README), затем:
python -m experiments.w2_compare --v1 data/cache/scored_v1_test.csv --v2 data/cache/scored_v2_test.csv

Пишет reports/week2/tables/comparison_tables.md, comparison*.csv: метрики недели 1 + деньги, интервал разницы по дням,
по месяцам, по эпизодам и расхождение «своя оценка на holdout ↔ приёмочный прогон».
"""
import argparse

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from experiments.w2_common import W2, load_labeled, summarize
from experiments.w2_patterns import build_episodes, md_table
from src.data import ROOT, load_train
from src.economics import costs, paired_bootstrap

ROWS = [("savings", "Экономия, у.е."), ("pct_of_ceiling", "Доля потолка (лучшее при лимите 0,3%)"),
        ("savings_per_day", "Экономия в сутки, у.е."), ("pr_auc", "PR-AUC"), ("precision", "Точность (precision)"),
        ("recall_cnt", "Чувствительность, шт"), ("recall_amt", "Чувствительность, деньги"),
        ("specificity", "Специфичность"), ("fp", "Задержано честных, всего"), ("fp_per_day", "Задержано честных в сутки"),
        ("flagged_per_day", "Проверок в сутки"), ("cap_violated", "Лимит нарушен")]


def episode_view(df, p_dec):
    f, ep = build_episodes(df)
    x = f.merge(p_dec, on="trans_num")
    g = x.groupby("ep_id")
    first = g.apply(lambda s: s.pos[s.decision == 1].min() if s.decision.any() else np.nan)
    lost = x.merge(first.rename("fs"), left_on="ep_id", right_index=True)
    lost = lost[(lost.pos < lost.fs) | lost.fs.isna()].amt.sum()
    return {"episodes": len(ep), "ep_detected": float(g.decision.max().mean()), "first_pos_median": float(first.median()),
            "lost_before_first": float(lost), "ep_money": float(x.amt.sum())}


def holdout_estimate(name):
    df = load_train().merge(pd.read_parquet(ROOT / "reports" / "preds" / f"{name}_holdout.parquet"), on="trans_num")
    return summarize(df, df.p.to_numpy(), df.decision.to_numpy())


def fmt(k, v):
    if k in ("pct_of_ceiling", "precision", "recall_cnt", "recall_amt"):
        return f"{v:.1%}"
    if k == "specificity":
        return f"{v:.3%}"
    if k in ("pr_auc",):
        return f"{v:.4f}"
    if k in ("fp_per_day", "flagged_per_day"):
        return f"{v:.2f}"
    if k == "cap_violated":
        return "нет" if not v else "да"
    return f"{v:,.0f}".replace(",", " ")


def delta(k, v):
    if k == "cap_violated":
        return ""
    if k in ("pct_of_ceiling", "precision", "recall_cnt", "recall_amt"):
        return f"{v * 100:+.1f} п.п."
    if k == "specificity":
        return f"{v * 100:+.3f} п.п."
    if k == "pr_auc":
        return f"{v:+.4f}"
    if k in ("fp_per_day", "flagged_per_day"):
        return f"{v:+.2f}"
    return f"{v:+,.0f}".replace(",", " ")


def segments(df, decs):
    """Контроль регрессий на приёмке: где v2 стал лучше/хуже."""
    f, ep = build_episodes(df)
    x = df.merge(f[["trans_num", "ep_id"]], on="trans_num", how="left")
    h = x.ts.dt.hour
    x["фаза"] = np.where(x.is_fraud == 0, "честная", np.where(x.amt < 100, "P1·м мелкие",
                         np.where(h <= 11, "P1·н ночная волна", "P1·в вечерняя волна")))
    x["сумма"] = pd.cut(x.amt, [0, 100, 300, 600, 1000, 1e9], labels=["< 100", "100–300", "300–600", "600–1000", "> 1000"]).astype(str)
    fr_day = x.groupby(x.ts.dt.normalize()).is_fraud.transform("sum")
    cap = np.floor(0.003 * x.groupby(x.ts.dt.normalize()).trans_num.transform("size"))
    x["нагрузка дня"] = np.where(fr_day > 2 * cap, "фрода > 2× лимита", np.where(fr_day > cap, "фрода > лимита", "фрода ≤ лимита"))
    x["месяц"] = x.ts.dt.to_period("M").astype(str)
    rows = []
    for col in ["фаза", "сумма", "нагрузка дня", "месяц"]:
        for val, g in x.groupby(col):
            r = {"разрез": col, "значение": val}
            for v in ("v1", "v2"):
                d = decs[v].set_index("trans_num").decision.reindex(g.trans_num).to_numpy()
                r[f"упущено {v}"] = float((g.amt * ((g.is_fraud == 1) & (d == 0))).sum())
                r[f"ложных {v}"] = int(((g.is_fraud == 0) & (d == 1)).sum())
            r["Δ упущено"] = r["упущено v2"] - r["упущено v1"]
            r["Δ ложных"] = r["ложных v2"] - r["ложных v1"]
            r["итог"] = "хуже" if (r["Δ упущено"] > 50 or r["Δ ложных"] > 0) else ("лучше" if (r["Δ упущено"] < -50 or r["Δ ложных"] < 0) else "без изменений")
            rows.append(r)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v1", default="data/cache/scored_v1_test.csv")
    ap.add_argument("--v2", default="data/cache/scored_v2_test.csv")
    a = ap.parse_args()
    df = load_labeled()
    day = df.ts.dt.normalize()
    res, per_day, decs = {}, {}, {}
    for k, path in [("v1", a.v1), ("v2", a.v2)]:
        s = pd.read_csv(ROOT / path).set_index("trans_num").loc[df.trans_num]
        p, d = s.fraud_probability.to_numpy(), s.decision.to_numpy()
        res[k] = summarize(df, p, d)
        per_day[k] = costs(df.is_fraud, df.amt, d, day)["per_day_savings"]
        decs[k] = pd.DataFrame({"trans_num": df.trans_num.to_numpy(), "p": p, "decision": d})
        res[k].update(episode_view(df, decs[k]))
    lo, hi = paired_bootstrap(per_day["v2"] - per_day["v1"])
    hold = {"v1": holdout_estimate("final"), "v2": holdout_estimate("final_v2")}

    t = pd.DataFrame([{"Показатель": name, "Было (v1)": fmt(k, res["v1"][k]), "Стало (v2)": fmt(k, res["v2"][k]),
                       "Δ": delta(k, res["v2"][k] - res["v1"][k])} for k, name in ROWS])
    ep_rows = [("ep_detected", "Эпизодов, где хотя бы одна операция ушла аналитику"),
               ("first_pos_median", "Номер первой проверенной операции эпизода (медиана)"),
               ("lost_before_first", "Деньги эпизодов, ушедшие до первой проверки, у.е.")]
    te = pd.DataFrame([{"Показатель": n, "Было (v1)": (f"{res['v1'][k]:.1%}" if k == "ep_detected" else fmt(k, res["v1"][k])),
                        "Стало (v2)": (f"{res['v2'][k]:.1%}" if k == "ep_detected" else fmt(k, res["v2"][k]))}
                       for k, n in ep_rows])
    gap = []
    for k, n in [("pct_of_ceiling", "Доля потолка"), ("precision", "Точность"), ("recall_amt", "Чувствительность, деньги"),
                 ("pr_auc", "PR-AUC"), ("fp_per_day", "Задержано честных в сутки")]:
        row = {"Показатель": n}
        for v in ("v1", "v2"):
            row[f"{v}: holdout"] = fmt(k, hold[v][k])
            row[f"{v}: приёмка"] = fmt(k, res[v][k])
            row[f"{v}: расхождение"] = fmt(k, res[v][k] - hold[v][k]) if k != "pr_auc" else f"{res[v][k] - hold[v][k]:+.4f}"
        gap.append(row)
    tg = pd.DataFrame(gap)
    m = df.ts.dt.to_period("M").astype(str)
    mon = []
    for mm in sorted(m.unique()):
        idx = (m == mm).to_numpy()
        r = {"месяц": mm}
        for v in ("v1", "v2"):
            sub = df[idx]
            s = summarize(sub, decs[v].p.to_numpy()[idx], decs[v].decision.to_numpy()[idx])
            r[f"{v} экономия"] = s["savings"]
            r[f"{v} доля потолка"] = f"{s['pct_of_ceiling']:.1%}"
            r[f"{v} ложных"] = s["fp"]
        r["фрода, операций"] = int(df.is_fraud[idx].sum())
        r["операций"] = int(idx.sum())
        mon.append(r)
    tm = pd.DataFrame(mon)
    out = pd.DataFrame({"metric": [k for k, _ in ROWS], "v1": [res["v1"][k] for k, _ in ROWS],
                        "v2": [res["v2"][k] for k, _ in ROWS]})
    out.to_csv(W2 / "comparison.csv", index=False, encoding="utf-8")
    tm.to_csv(W2 / "comparison_monthly.csv", index=False, encoding="utf-8")
    lines = ["# v1 против v2 на приёмочном периоде (fraudTest)", "",
             f"fraudTest: {fmt('fp', res['v1']['ops'])} операций, {res['v1']['days']} дней (21.06–31.12.2020), фрод "
             f"{fmt('fp', res['v1']['fraud_ops'])} операций ({res['v1']['fraud_rate']:.2%}). Обе версии — тем же score.py, "
             "на тех же строках, с одной и той же историей карт до 21.06.2020.", "",
             md_table(t), "",
             f"Разница v2 − v1 по экономии: {res['v2']['savings'] - res['v1']['savings']:+,.0f} у.е.; 90% интервал по дням "
             f"(парный бутстрэп): [{lo:+,.0f}; {hi:+,.0f}].".replace(",", " "), "",
             "## Эпизоды", "", md_table(te), "",
             "## Расхождение: своя оценка на holdout ↔ приёмочный прогон", "", md_table(tg), "",
             "## По месяцам", "", md_table(tm)]
    # Паттерны на приёмке.
    f, ep = build_episodes(df)
    first_ts = df.groupby("cc_num").ts.min()
    newc = set(ep.cc_num[ep.start <= ep.cc_num.map(first_ts)])
    prow = []
    masks = {"P1 весь эпизод": f.index == f.index, "P1·в вечерняя волна (≥100, 12–23)": (~f.small) & (f.hour >= 12),
             "P1·н ночная волна (≥100, 00–11)": (~f.small) & (f.hour <= 11), "P1·м мелкие (<100)": f.small,
             "P2 новая карта (эпизод с первой операции)": f.cc_num.isin(newc)}
    for name, mk in masks.items():
        x = f[mk]
        r = {"паттерн": name, "операций": len(x), "сумма": float(x.amt.sum())}
        for v in ("v1", "v2"):
            dd = decs[v].set_index("trans_num").reindex(x.trans_num)
            r[f"{v}: p ≥ 0,5"] = f"{(dd.p >= 0.5).mean():.0%}"
            r[f"{v}: деньги отправлено"] = f"{(x.amt.to_numpy() * dd.decision.to_numpy()).sum() / x.amt.sum():.0%}"
            r[f"{v}: эпизодов с проверкой"] = f"{pd.Series(dd.decision.to_numpy(), index=x.ep_id.values).groupby(level=0).max().mean():.0%}"
        prow.append(r)
    tp = pd.DataFrame(prow)
    tp.to_csv(W2 / "comparison_patterns.csv", index=False, encoding="utf-8")
    lines += ["", "## Паттерны на приёмке", "", md_table(tp)]
    sg = segments(df, decs)
    sg.to_csv(W2 / "comparison_segments.csv", index=False, encoding="utf-8")
    lines += ["", "## Контроль регрессий на приёмке (упущенные деньги и ложные тревоги)", "",
              md_table(sg, {"Δ упущено": lambda v: f"{v:+,.0f}".replace(",", " "), "Δ ложных": lambda v: f"{v:+d}",
                            "ложных v1": str, "ложных v2": str})]
    (W2 / "comparison_tables.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
