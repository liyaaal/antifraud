"""Примеры карточек для аналитика: реальные операции холдаута, прогнанные через score.py.

python -m experiments.examples  ->  reports/examples.md, reports/examples_flagged.csv
"""
import pandas as pd

from score import load_artifacts, score_frame
from src.data import ROOT, load_train
from src.split import assign, boundaries

R = ROOT / "reports"
df = load_train()
part = assign(df.ts, boundaries(df.ts))
ho = df[part == "holdout"]
raw = pd.read_csv(ROOT / "data" / "fraudTrain.csv", dtype={"cc_num": "int64", "trans_num": "str"}, low_memory=False)
raw = raw[raw["trans_num"].isin(set(ho["trans_num"]))].drop(columns=["is_fraud"])
out = score_frame(raw, load_artifacts(ROOT / "artifacts" / "final"))
m = out.merge(ho[["trans_num", "ts", "cc_num", "category", "amt", "is_fraud"]], on="trans_num")
fl = m[m["decision"] == 1].copy()
fl["n_reasons"] = (fl[["reason_1", "reason_2", "reason_3"]] != "").sum(axis=1)
fl.to_csv(R / "examples_flagged.csv", index=False, encoding="utf-8-sig")
reasons = pd.concat([fl[c] for c in ["reason_1", "reason_2", "reason_3"]])
reasons = reasons[reasons != ""].str.replace(r"\d[\d  .,]*", "N", regex=True).value_counts().head(12)
lines = ["# Примеры карточек для аналитика (холдаут, реальный выход score.py)", "",
         f"Отправлено аналитикам: {len(fl)}; из них мошенничество: {int(fl.is_fraud.sum())}; честные: {int((fl.is_fraud == 0).sum())}.",
         f"Три причины: {int((fl.n_reasons == 3).sum())}; две: {int((fl.n_reasons == 2).sum())}; одна: {int((fl.n_reasons == 1).sum())}.",
         "", "## Самые частые причины (числа заменены на N)", "", reasons.to_markdown(), ""]
for title, sub in [("Пойманное мошенничество", fl[fl.is_fraud == 1].sort_values("amt", ascending=False).head(6)),
                   ("Честные операции, которые остановили (ложная тревога)", fl[fl.is_fraud == 0].head(6))]:
    lines += [f"## {title}", ""]
    for _, r in sub.iterrows():
        lines += [f"- **{r.ts:%d.%m.%Y %H:%M}**, {r.category}, {r.amt:.2f} у.е., вероятность {r.fraud_probability:.3f}",
                  f"  1. {r.reason_1}", f"  2. {r.reason_2}", f"  3. {r.reason_3}"]
    lines.append("")
(R / "examples.md").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
