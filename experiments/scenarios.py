"""Кто какой сценарий ловит: первая операция серии мошенничества против продолжения серии.

Серия — фрод-операции одной карты. «Первая» — фрод, перед которым у карты не было фрода 7 дней.
Метки здесь используются только для разбора результатов на valid, не в признаках.

python -m experiments.scenarios  ->  reports/scenarios.md
"""
import numpy as np
import pandas as pd

from src.data import ROOT
from src.evaluate import DEFAULTS, feature_list, run
from src.pipeline import load_dataset
from experiments.tournament import C_TREE_REJECTED, REJECTED


def cfg_of(name, blocks, **kw):
    return {**DEFAULTS, "name": name, "author": "team", "blocks": blocks, "calibration": "isotonic",
            "policy": "ev_cap", **kw}


def fs(blocks, drop=()):
    return [c for c in feature_list(cfg_of("x", blocks)) if c not in REJECTED and c not in set(drop)]


df, part, X, states, b = load_dataset(["base", "a", "b", "c"])
va = (part == "valid").to_numpy()
d = df.loc[va, ["cc_num", "ts", "amt", "is_fraud"]].copy()
# Первая операция серии: у карты не было фрода за предыдущие 7 дней (по всему файлу, включая train).
f = df.loc[df.is_fraud == 1, ["cc_num", "ts"]].sort_values(["cc_num", "ts"])
f["prev"] = f.groupby("cc_num")["ts"].shift(1)
first_idx = f.index[(f["prev"].isna()) | ((f["ts"] - f["prev"]) > pd.Timedelta(days=7))]
d["сценарий"] = np.where(d.is_fraud == 0, "честная", "продолжение серии")
d.loc[d.index.isin(first_idx) & (d.is_fraud == 1), "сценарий"] = "первая операция серии"

variants = {
    "база": (["base"], fs(["base"]), {}),
    "A: профиль (LightGBM)": (["base", "a"], fs(["base", "a"]), {}),
    "B: ритм (LightGBM монотонный)": (["base", "b"], fs(["base", "b"]), {"monotone": True}),
    "финал: A+B+C5, учит деньгам": (["base", "a", "b", "c"], fs(["base", "a", "b", "c"], C_TREE_REJECTED),
                                    {"sample_weight": "cost"}),
    "финал + монотонность": (["base", "a", "b", "c"], fs(["base", "a", "b", "c"], C_TREE_REJECTED),
                             {"sample_weight": "cost", "monotone": True}),
}
rows = []
for name, (blocks, feats, kw) in variants.items():
    res = run(cfg_of(f"S|{name}", blocks, **kw), feats, df, part, X, "valid", note="сценарии")
    d["dec"] = res["decision"]
    for sc in ["первая операция серии", "продолжение серии"]:
        m = d["сценарий"] == sc
        rows.append({"вариант": name, "сценарий": sc, "фродов": int(m.sum()),
                     "сумма фрода, у.е.": round(float(d.loc[m, "amt"].sum()), 2),
                     "поймано, шт": int(d.loc[m, "dec"].sum()),
                     "поймано, у.е.": round(float(d.loc[m & (d.dec == 1), "amt"].sum()), 2),
                     "доля денег": round(float(d.loc[m & (d.dec == 1), "amt"].sum() / d.loc[m, "amt"].sum()), 4)})
    rows.append({"вариант": name, "сценарий": "ложные отправки (честные)", "фродов": "",
                 "поймано, шт": int(((d["сценарий"] == "честная") & (d.dec == 1)).sum())})
t = pd.DataFrame(rows)
(ROOT / "reports" / "scenarios.md").write_text("# Кто какой сценарий ловит (valid)\n\n" + t.to_markdown(index=False),
                                               encoding="utf-8")
print(t.to_string())
