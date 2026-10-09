"""Неделя 2: расчёты к замечаниям преподавателя (reports/week2/1_remarks.md).

python -m experiments.w2_remarks
Нужны предсказания reports/preds/final*_{valid,holdout}.parquet и выходы score.py на fraudTest
(data/cache/scored_v1_test.csv, data/cache/scored_v2_test.csv). Пишет reports/week2/tables/remarks_*.md/.csv/.png.

  1. Группы риска (высокий / средний / низкий): сколько операций и сколько фрода в каждой, сколько отправлено.
  2. Из скольких рисковых операций помечаем (в день).
  3. Кривая precision–recall и PR-AUC.
  4. Баланс классов.
  5. «7 аналитиков»: сколько проверок в день даёт лимит 0,3%.
  6. Откуда 327 812 («потолок») и 323 389 — формула по слагаемым.
  7. Логистическая регрессия против LightGBM (из турнира недели 1).
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_curve

from experiments.w2_common import W2, load_labeled
from experiments.w2_patterns import md_table
from src.data import ROOT, load_train
from src.economics import MISS_EXTRA, REVIEW, FALSE_BLOCK, daily_cap, top_k_per_day
from src.risk import HIGH, LOW, risk_level

PRED = ROOT / "reports" / "preds"


def sets():
    tr = load_train()
    out = {}
    for v, name in [("v1", "final"), ("v2", "final_v2")]:
        for part in ("valid", "holdout"):
            d = tr.merge(pd.read_parquet(PRED / f"{name}_{part}.parquet"), on="trans_num")
            out[(v, part)] = d[["ts", "amt", "is_fraud", "p", "decision"]]
    te = load_labeled()
    for v in ("v1", "v2"):
        s = pd.read_csv(ROOT / "data" / "cache" / f"scored_{v}_test.csv").set_index("trans_num").loc[te.trans_num]
        out[(v, "fraudTest")] = pd.DataFrame({"ts": te.ts.to_numpy(), "amt": te.amt.to_numpy(),
                                              "is_fraud": te.is_fraud.to_numpy(),
                                              "p": s.fraud_probability.to_numpy(), "decision": s.decision.to_numpy()})
    return tr, te, out


def pct(v):
    return f"{v:.1%}"


def main():
    W2.mkdir(parents=True, exist_ok=True)
    tr, te, S = sets()
    md = ["# Расчёты к замечаниям преподавателя", "", "Скрипт: `python -m experiments.w2_remarks`.", ""]

    # 1–2. Группы риска.
    rows, daily = [], []
    for (v, part), d in S.items():
        lvl = risk_level(d.p)
        y = d.is_fraud.to_numpy() == 1
        dec = d.decision.to_numpy() == 1
        ndays = d.ts.dt.normalize().nunique()
        for k in ("высокий", "средний", "низкий"):
            m = lvl == k
            rows.append({"версия": v, "период": part, "группа": k, "операций": int(m.sum()),
                         "из них фрод": int((m & y).sum()), "доля фрода в группе": (m & y).sum() / max(m.sum(), 1),
                         "доля от всего фрода": (m & y).sum() / y.sum(), "отправлено аналитику": int((m & dec).sum()),
                         "фрод среди отправленных": int((m & dec & y).sum())})
        risky = lvl != "низкий"
        daily.append({"версия": v, "период": part, "дней": ndays, "операций в день": len(d) / ndays,
                      "фрод-операций в день": y.sum() / ndays, "рисковых в день": risky.sum() / ndays,
                      "лимит (проверок) в день": daily_cap(d.ts.dt.normalize()).groupby(d.ts.dt.normalize()).first().mean(),
                      "отправлено в день": dec.sum() / ndays,
                      "фрод помечен рисковым": (risky & y).sum() / y.sum(),
                      "фрод отправлен аналитику": (dec & y).sum() / y.sum()})
    t1, t2 = pd.DataFrame(rows), pd.DataFrame(daily)
    t1.to_csv(W2 / "remarks_risk_groups.csv", index=False, encoding="utf-8")
    t2.to_csv(W2 / "remarks_risky_per_day.csv", index=False, encoding="utf-8")
    md += [f"## 1. Группы риска (пороги {LOW:.2f} и {HIGH:.2f} выбраны на valid)", "",
           md_table(t1, {"доля фрода в группе": lambda x: f"{x:.2%}", "доля от всего фрода": pct}), "",
           "## 2. Из скольких рисковых операций помечаем", "",
           md_table(t2, {"операций в день": lambda x: f"{x:,.0f}".replace(",", " "),
                         "фрод-операций в день": lambda x: f"{x:.1f}", "рисковых в день": lambda x: f"{x:.1f}",
                         "лимит (проверок) в день": lambda x: f"{x:.1f}", "отправлено в день": lambda x: f"{x:.1f}",
                         "фрод помечен рисковым": pct, "фрод отправлен аналитику": pct, "дней": str}), ""]

    # 3. PR-кривая.
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.4))
    prow = []
    for j, part in enumerate(("holdout", "fraudTest")):
        for v, col in (("v1", "#8F97A3"), ("v2", "#1F8A7A")):
            d = S[(v, part)]
            y, p = d.is_fraud.to_numpy(), d.p.to_numpy()
            pr, rc, _ = precision_recall_curve(y, p)
            ap = average_precision_score(y, p)
            ax[j].plot(rc, pr, color=col, lw=2, label=f"{v}: PR-AUC = {ap:.3f}")
            for thr, mk in ((HIGH, "o"), (LOW, "s")):
                m = p >= thr
                ax[j].plot((m & (y == 1)).sum() / y.sum(), (m & (y == 1)).sum() / max(m.sum(), 1), mk, color=col, ms=7)
            dec = d.decision.to_numpy() == 1
            ax[j].plot((dec & (y == 1)).sum() / y.sum(), (dec & (y == 1)).sum() / dec.sum(), "*", color=col, ms=13)
            prow.append({"период": part, "версия": v, "PR-AUC": ap, "доля фрода (случайная модель = PR-AUC)": y.mean()})
        ax[j].axhline(S[("v1", part)].is_fraud.mean(), color="#D6452F", ls=":", lw=1)
        ax[j].set_title(f"{part}: точность против полноты")
        ax[j].set_xlabel("полнота (recall) — какую долю фрода нашли")
        ax[j].set_ylabel("точность (precision) — доля фрода среди отмеченных")
        ax[j].set_ylim(0, 1.02)
        ax[j].grid(alpha=.3)
        ax[j].legend(fontsize=8, loc="lower left")
    fig.suptitle("Кривая precision–recall. ● порог 0,90 (высокий риск), ■ порог 0,10 (средний), ★ отправлено аналитикам "
                 "при лимите 0,3%; пунктир — случайная модель", fontsize=9)
    fig.tight_layout()
    fig.savefig(W2 / "remarks_pr_curve.png", dpi=130)
    t3 = pd.DataFrame(prow)
    md += ["## 3. Precision–recall", "", "![](remarks_pr_curve.png)", "",
           md_table(t3, {"PR-AUC": lambda x: f"{x:.4f}", "доля фрода (случайная модель = PR-AUC)": lambda x: f"{x:.4f}"}), ""]

    # 4. Баланс классов.
    bal = []
    parts = {"train (01.2019–20.02.2020)": tr[tr.ts < "2020-02-21"], "valid": tr[(tr.ts >= "2020-02-21") & (tr.ts < "2020-04-22")],
             "holdout": tr[tr.ts >= "2020-04-22"], "fraudTest (приёмка)": te}
    for k, d in parts.items():
        f = int(d.is_fraud.sum())
        bal.append({"набор": k, "операций": len(d), "мошеннических": f, "честных": len(d) - f,
                    "доля фрода": f / len(d), "1 фрод на N операций": round(len(d) / f),
                    "доля денег фрода": d.amt[d.is_fraud == 1].sum() / d.amt.sum()})
    t4 = pd.DataFrame(bal)
    md += ["## 4. Баланс классов", "", md_table(t4, {"доля фрода": lambda x: f"{x:.2%}", "доля денег фрода": pct,
                                                     "1 фрод на N операций": lambda x: f"{x:.0f}"}), ""]

    # 5–6. Лимит и потолок на holdout.
    d = S[("v1", "holdout")]
    day = d.ts.dt.normalize()
    y = d.is_fraud.to_numpy() == 1
    amt = d.amt.to_numpy(dtype="float64")
    k = daily_cap(day).groupby(day).first()
    n = d.groupby(day).size()
    o = top_k_per_day(day, np.where(y, amt, -np.inf), eligible=y) == 1
    dec = d.decision.to_numpy() == 1
    loss_none = (amt[y] + MISS_EXTRA).sum()
    ceil_ = (amt[o] + MISS_EXTRA).sum() - REVIEW * o.sum()
    ours = (amt[dec & y] + MISS_EXTRA).sum() - REVIEW * dec.sum() - FALSE_BLOCK * (dec & ~y).sum()
    t5 = pd.DataFrame([{"величина": "операций в день (среднее / мин / макс)", "значение": f"{n.mean():.0f} / {n.min()} / {n.max()}"},
                       {"величина": "лимит k = floor(0,3% · операций дня), проверок в день", "значение": f"{k.mean():.1f} / {k.min()} / {k.max()}"},
                       {"величина": "фрод-операций в день (среднее / макс)",
                        "значение": f"{y.sum() / len(n):.1f} / {int(pd.Series(y).groupby(day.to_numpy()).sum().max())}"}])
    t6 = pd.DataFrame([
        {"слагаемое": "убыток без системы: Σ(сумма + 5) по всему фроду", "оракул (потолок)": loss_none, "наша система v1": loss_none},
        {"слагаемое": "проверок за 61 день", "оракул (потолок)": o.sum(), "наша система v1": dec.sum()},
        {"слагаемое": "из них фрод", "оракул (потолок)": o.sum(), "наша система v1": int((dec & y).sum())},
        {"слагаемое": "спасено: Σ(сумма + 5) по пойманному фроду", "оракул (потолок)": (amt[o] + MISS_EXTRA).sum(),
         "наша система v1": (amt[dec & y] + MISS_EXTRA).sum()},
        {"слагаемое": "минус 3 у.е. за каждую проверку", "оракул (потолок)": -REVIEW * o.sum(), "наша система v1": -REVIEW * dec.sum()},
        {"слагаемое": "минус 25 у.е. за каждого задержанного честного", "оракул (потолок)": 0.0,
         "наша система v1": -FALSE_BLOCK * (dec & ~y).sum()},
        {"слагаемое": "ЭКОНОМИЯ", "оракул (потолок)": ceil_, "наша система v1": ours},
    ])
    md += ["## 5. Лимит 0,3% — это проверки, а не люди (holdout, 61 день)", "", md_table(t5), "",
           "## 6. Откуда 327 812 и 323 389 (holdout, 61 день)", "",
           md_table(t6, {"оракул (потолок)": lambda x: f"{x:,.0f}".replace(",", " "),
                         "наша система v1": lambda x: f"{x:,.0f}".replace(",", " ")}), "",
           f"Доля потолка: {ours:,.0f} / {ceil_:,.0f} = {ours / ceil_:.2%}.".replace(",", " "), ""]

    # 7. LogReg против LightGBM (турнир недели 1, valid).
    tour = pd.read_csv(ROOT / "reports" / "tournament.csv")
    cols = [c for c in tour.columns]
    fcol = "признаки" if "признаки" in cols else cols[1]
    sub = tour[tour["модель"].isin(["LogReg", "LightGBM, учит деньгам"]) & (tour["политика"] == "ev_cap")]
    sub = sub.drop_duplicates([fcol, "модель"])
    piv = sub.pivot_table(index=fcol, columns="модель", values=["экономия", "pr_auc"], aggfunc="first")
    piv.columns = [f"{a}: {b}" for a, b in piv.columns]
    piv = piv.reset_index()
    md += ["## 7. Логистическая регрессия против LightGBM (турнир недели 1, valid, политика ev_cap)", "",
           md_table(piv, {c: (lambda x: f"{x:.3f}") if c.startswith("pr_auc") else (lambda x: f"{x:,.0f}".replace(",", " "))
                          for c in piv.columns if c != fcol})]
    (W2 / "remarks_tables.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
