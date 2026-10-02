"""Экономика для заказчика на холдауте (22.04–21.06.2020). Финал уже выбран и зафиксирован на valid;
здесь ничего не подбирается — только отчёт.

python -m experiments.economics_report  ->  reports/economics.md, reports/economics.json, reports/fig_*.png
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.calibration import reliability
from src.data import ROOT
from src.economics import costs, decide, top_k_per_day
from src.evaluate import DEFAULTS, feature_list, load_config, run
from src.pipeline import load_dataset

R = ROOT / "reports"


def cfg_of(name, blocks, **kw):
    return {**DEFAULTS, "name": name, "author": "team", "blocks": blocks, **kw}


def main():
    final = load_config(ROOT / "configs" / "final.yaml")
    df, part, X, states, b = load_dataset(["base", "a", "b", "c"])
    ho = (part == "holdout").to_numpy()
    y = df.loc[ho, "is_fraud"].to_numpy()
    amt = df.loc[ho, "amt"].to_numpy(dtype="float64")
    day = df.loc[ho, "ts"].dt.normalize()
    ndays = day.nunique()

    rej = set(final["exclude"])
    runs = {
        "Базовая модель, по вероятности": (cfg_of("H|base_topp", ["base"], policy="top_p"), ["base"]),
        "Базовая модель, по деньгам": (cfg_of("H|base_ev", ["base"], calibration="isotonic", policy="ev_cap"), ["base"]),
        "Решение A (профиль, LogReg)": (cfg_of("H|A", ["base", "a"], model="logreg", calibration="isotonic",
                                               policy="ev_cap"), ["base", "a"]),
        "Решение B (ритм, монотонный LightGBM)": (cfg_of("H|B", ["base", "b"], monotone=True, calibration="isotonic",
                                                         policy="ev_cap"), ["base", "b"]),
        "Решение C (среда, учит деньгам)": (cfg_of("H|C", ["base", "c"], sample_weight="cost", calibration="isotonic",
                                                   policy="ev_cap"), ["base", "c"]),
        "Финал": (final, final["blocks"]),
    }
    res = {}
    for name, (cfg, blocks) in runs.items():
        feats = [f for f in feature_list({**cfg, "blocks": blocks, "exclude": []}) if f not in rej or name != "Финал"]
        if name == "Финал":
            feats = feature_list(final)
        elif blocks != ["base"]:
            feats = [f for f in feats if f not in {"a_new_merchant", "a_geo_km", "a_amt_down", "b_cnt_24h_window",
                                                   "b_sess_cat_n"}]
        note = "холдаут: отчёт после выбора финала" if name != "Финал" else "холдаут: финал (повтор для отчёта)"
        res[name] = run(cfg, feats, df, part, X, "holdout", note=note)

    fin = res["Финал"]
    p = fin["p"]
    oracle = top_k_per_day(day, np.where(y == 1, amt, -np.inf), eligible=y == 1)
    ceiling = costs(y, amt, oracle, day)
    rule = costs(y, amt, decide("rule_amt", day, p, amt), day)
    none = costs(y, amt, decide("none", day, p, amt), day)

    def summary(c, d):
        d = np.asarray(d).astype(bool)
        return {"экономия": round(c["savings"], 2), "потери": round(c["loss"], 2),
                "поймано фродов": int((d & (y == 1)).sum()), "поймано денег": round(float(amt[d & (y == 1)].sum()), 2),
                "честных клиентов остановлено": int((d & (y == 0)).sum()),
                "проверок в день": round(float(d.sum() / ndays), 2)}

    table = {"Без системы": summary(none, np.zeros(len(y))),
             "Правило «проверять самые дорогие»": summary(rule, decide("rule_amt", day, p, amt))}
    for name, r in res.items():
        table[name] = summary(costs(y, amt, r["decision"], day), r["decision"])
    table["Потолок (идеальная модель)"] = summary(ceiling, oracle)
    T = pd.DataFrame(table).T

    # Стресс-тест: фрода втрое больше.
    stress = []
    for k in [1, 2, 3]:
        pk = k * p / (k * p + 1 - p)
        for cap in [0.003, 0.005, 0.01]:
            d = decide("ev_cap", day, pk, amt, capacity=cap)
            c = costs(y, amt, d, day, fraud_weight=k)
            oc = costs(y, amt, top_k_per_day(day, np.where(y == 1, amt, -np.inf), eligible=y == 1, capacity=cap), day,
                       fraud_weight=k)
            stress.append({"фрод ×": k, "лимит": f"{cap:.1%}", "потери без системы": round(c["loss_none"], 0),
                           "экономия": round(c["savings"], 0), "доля спасённых денег": round(c["savings"] / c["loss_none"], 3),
                           "доля от потолка": round(c["savings"] / oc["savings"], 3),
                           "пропущено фрода, у.е.": round(float((amt * (y == 1) * k)[~d.astype(bool)].sum()), 0)})
    S = pd.DataFrame(stress)

    # Кривая «сколько аналитиков нанимать».
    caps = [0.001, 0.002, 0.003, 0.004, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03]
    curve = []
    for cap in caps:
        d = decide("ev_cap", day, p, amt, capacity=cap)
        c = costs(y, amt, d, day)
        curve.append({"лимит": cap, "проверок в день": round(float(d.sum() / ndays), 1), "экономия": round(c["savings"], 0),
                      "экономия ×3": round(costs(y, amt, decide("ev_cap", day, 3 * p / (3 * p + 1 - p), amt, capacity=cap),
                                                 day, fraud_weight=3)["savings"], 0)})
    C = pd.DataFrame(curve)

    # Чувствительность к цене ложной блокировки.
    sens = []
    for fb in [10, 25, 50]:
        row = {"ложная блокировка, у.е.": fb}
        for pol in ["top_p", "ev_cap"]:
            d = decide(pol, day, p, amt, false_block=fb)
            row[pol] = round(costs(y, amt, d, day, false_block=fb)["savings"], 0)
        sens.append(row)
    F = pd.DataFrame(sens)

    rel = reliability(p, y)
    lines = ["# Экономика на холдауте (22.04–21.06.2020, 61 день, не использовался при выборе)", "",
             f"Операций: {len(y)}; мошеннических: {int(y.sum())}; сумма мошенничества: {amt[y == 1].sum():,.2f} у.е.".replace(",", " "),
             "", "## Итог по вариантам", "", T.to_markdown(), "",
             "## Стресс-тест: фрода больше", "", S.to_markdown(index=False), "",
             "## Сколько проверок нужно (финальная модель)", "", C.to_markdown(index=False), "",
             "## Чувствительность к цене ложной блокировки (экономия, у.е.)", "", F.to_markdown(index=False), "",
             "## Калибровка вероятностей финальной модели (верхние 10% по скору)", "", rel.to_markdown(), ""]
    (R / "economics.md").write_text("\n".join(lines), encoding="utf-8")
    (R / "economics.json").write_text(json.dumps({"table": T.reset_index().to_dict("records"),
                                                  "stress": S.to_dict("records"), "curve": C.to_dict("records"),
                                                  "false_block": F.to_dict("records"), "n": int(len(y)),
                                                  "n_fraud": int(y.sum()), "fraud_amt": float(amt[y == 1].sum()),
                                                  "days": int(ndays)}, ensure_ascii=False, indent=1),
                                      encoding="utf-8")

    # Предсказания финала на холдауте — для примеров причин.
    out = df.loc[ho, ["trans_num"]].copy()
    out["p"] = p
    out["decision"] = fin["decision"]
    out.to_parquet(R / "preds" / "final_holdout.parquet", index=False)
    print(T.to_string())
    print(S.to_string())
    print(C.to_string())
    print(F.to_string())
    print(rel.to_string())


if __name__ == "__main__":
    main()
