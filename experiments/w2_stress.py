"""Неделя 2, раздел 5: поведение решения при изменении условий (измерения, а не предположения).

python -m experiments.w2_stress --artifacts artifacts/final_v2 --tag v2

Запускается на fraudTest ПОСЛЕ сравнения v1/v2 (ничего не подбирается). Каждый сценарий — прогон
score_frame() с изменённым входом или артефактами; деньги считаются той же функцией, что в неделе 1.
Пишет reports/week2/tables/stress_<tag>.md/.csv.
"""
import argparse
import time

import numpy as np
import pandas as pd

from experiments.w2_common import W2, TEST_CSV, summarize
from experiments.w2_patterns import md_table, pct
from score import load_artifacts, score_frame
from src.data import READ_DTYPES, ROOT, clean
from src.economics import costs, decide


def run(raw, art, label, fraud_weight=1.0):
    t0 = time.time()
    out = score_frame(raw, art, with_reasons=False)
    sec = time.time() - t0
    lab = clean(raw)[["trans_num", "ts", "amt", "is_fraud", "category", "cc_num"]]
    m = lab.merge(out, on="trans_num")
    r = summarize(m, m.fraud_probability.to_numpy(), m.decision.to_numpy())
    if fraud_weight != 1.0:
        day = m.ts.dt.normalize()
        for cap in (0.003, 0.005, 0.01):
            d = decide("ev_cap", day, m.fraud_probability.to_numpy(), m.amt.to_numpy(dtype="float64"), capacity=cap)
            c = costs(m.is_fraud, m.amt, d, day, fraud_weight=fraud_weight)
            r[f"savings_cap{cap}"] = c["savings"]
            r[f"loss_left_cap{cap}"] = c["loss"]
    r.update({"сценарий": label, "сек": sec})
    return r, m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifacts", default="artifacts/final_v2")
    ap.add_argument("--tag", default="v2")
    a = ap.parse_args()
    art = load_artifacts(ROOT / a.artifacts)
    raw = pd.read_csv(TEST_CSV, dtype=READ_DTYPES, low_memory=False)
    rows = []

    base, m0 = run(raw, art, "как есть (fraudTest)")
    rows.append(base)

    # 1. Хранилище истории недоступно: все карты выглядят новыми.
    empty = ROOT / "data" / "cache" / "empty_history.parquet"
    pd.read_parquet(art["history"]).head(0).to_parquet(empty, index=False)
    r, _ = run(raw, {**art, "history": empty}, "нет истории карт (хранилище недоступно)")
    rows.append(r)

    # 2. Новые честные клиенты: 50 честных карт клонируются под новыми номерами без истории.
    rng = np.random.default_rng(42)
    honest_cards = raw.groupby("cc_num").is_fraud.max()
    pick = rng.choice(honest_cards[honest_cards == 0].index.to_numpy(), 50, replace=False)
    clone = raw[raw.cc_num.isin(pick)].copy()
    clone["cc_num"] = clone["cc_num"].map({c: 900_000_000_000 + i for i, c in enumerate(pick)})
    clone["trans_num"] = "clone_" + clone["trans_num"].astype(str)
    r, m = run(pd.concat([raw, clone], ignore_index=True), art, "+50 новых честных карт без истории")
    cl = m[m.trans_num.str.startswith("clone_")]
    orig = m0[m0.cc_num.isin(pick)]
    first = cl.sort_values("ts").groupby("cc_num").head(5)
    r["новые карты: операций"] = len(cl)
    r["новые карты: отправлено аналитику"] = int(cl.decision.sum())
    r["новые карты: доля p ≥ 0,5 в первых 5 операциях"] = float((first.fraud_probability >= 0.5).mean())
    r["те же карты с историей: отправлено"] = int(orig.decision.sum())
    rows.append(r)

    # 3. Смена рынка: все суммы ×1,5 (другая валюта/инфляция), поведение то же.
    x = raw.copy()
    x["amt"] = x["amt"] * 1.5
    r, _ = run(x, art, "все суммы ×1,5")
    rows.append(r)

    # 4. Источник времени сдвинут на +3 ч (другой часовой пояс в выгрузке).
    x = raw.copy()
    x["trans_date_trans_time"] = (pd.to_datetime(x["trans_date_trans_time"]) + pd.Timedelta(hours=3)).astype(str)
    r, _ = run(x, art, "время в выгрузке сдвинуто на +3 ч")
    rows.append(r)

    # 5. Поле category недоступно (пустое).
    x = raw.copy()
    x["category"] = "unknown"
    r, _ = run(x, art, "категория недоступна")
    rows.append(r)

    # 6. Мошенничества втрое больше (вес строк фрода ×3) при разном лимите.
    r, _ = run(raw, art, "фрода ×3", fraud_weight=3.0)
    rows.append(r)

    res = pd.DataFrame(rows)
    render(res, a)


def render(res, a):
    res.to_csv(W2 / f"stress_{a.tag}.csv", index=False, encoding="utf-8")
    show = res[["сценарий", "savings", "ceiling", "pct_of_ceiling", "precision", "recall_amt", "fp", "flagged", "сек"]]
    txt = [f"# Поведение при изменении условий — {a.artifacts} на fraudTest", "",
           md_table(show.rename(columns={"savings": "экономия", "ceiling": "потолок", "pct_of_ceiling": "доля потолка",
                                         "precision": "точность", "recall_amt": "чувствительность (деньги)",
                                         "fp": "ложных", "flagged": "проверок"}),
                    {"доля потолка": lambda v: f"{v:.1%}", "точность": pct, "чувствительность (деньги)": pct,
                     "сек": lambda v: f"{v:.0f}"}), "",
           "Новые честные карты: " + ", ".join(f"{k} = {res.iloc[2][k]:.0f}" if not k.startswith("новые карты: доля")
                                               else f"{k} = {res.iloc[2][k]:.0%}"
                                               for k in res.columns if k.startswith(("новые", "те же"))), "",
           "Строка «фрода ×3» в таблице совпадает с базовой: утроение учитывается только в деньгах ниже.", "",
           "Фрода ×3: " + ", ".join(f"лимит {c:.1%}: экономия {res.iloc[-1][f'savings_cap{c}']:,.0f}, осталось убытка "
                                    f"{res.iloc[-1][f'loss_left_cap{c}']:,.0f}".replace(",", " ") for c in (0.003, 0.005, 0.01))]
    (W2 / f"stress_{a.tag}.md").write_text("\n".join(txt), encoding="utf-8")
    print("\n".join(txt))


if __name__ == "__main__":
    main()
