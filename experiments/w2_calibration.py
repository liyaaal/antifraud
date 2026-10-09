"""Неделя 2, замечание 8: даёт ли что-то более гладкая калибровка вместо изотонической «ступеньками».

python -m experiments.w2_raw_scores --config configs/final.yaml       # сырые скоры (до калибровки)
python -m experiments.w2_raw_scores --config configs/final_v2.yaml
python -m experiments.w2_calibration

Оценка на valid — как в неделе 1 (калибратор для одной половины valid учится на другой), на holdout —
калибратор на всём valid. Пишет reports/week2/tables/calibration.md.
"""
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from experiments.w2_common import W2
from experiments.w2_patterns import md_table
from src.data import ROOT, load_train
from src.economics import costs, decide


def _logit(z):
    z = np.clip(z, 1e-12, 1 - 1e-12)
    return np.log(z / (1 - z)).reshape(-1, 1)


def fit(method, r, y):
    if method == "isotonic (как в v1)":
        return IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(r, y).predict
    if method == "isotonic, интерполяция по центрам ступенек":
        v = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(r, y).predict(r)
        o = np.argsort(r)
        t = pd.DataFrame({"r": r[o], "v": v[o]})
        g = t.groupby((t.v.diff() != 0).cumsum()).agg(r=("r", "mean"), v=("v", "first"))
        return lambda z: np.interp(z, g.r.to_numpy(), g.v.to_numpy())
    lr = LogisticRegression(C=1e6).fit(_logit(r), y)
    return lambda z: lr.predict_proba(_logit(z))[:, 1]


def main():
    df = load_train()
    rows = []
    for name in ["final", "final_v2"]:
        R = pd.read_parquet(ROOT / "reports" / "preds" / f"{name}_raw.parquet").merge(
            df[["trans_num", "ts", "amt", "is_fraud"]], on="trans_num")
        va, ho = R[R.part == "valid"].reset_index(drop=True), R[R.part == "holdout"].reset_index(drop=True)
        dv, dh = va.ts.dt.normalize(), ho.ts.dt.normalize()
        first = (dv < dv.min() + pd.Timedelta(days=30)).to_numpy()
        for m in ["isotonic (как в v1)", "isotonic, интерполяция по центрам ступенек", "Платт (логистическая)"]:
            pv = np.empty(len(va))
            for h in (first, ~first):
                pv[h] = fit(m, va.raw.to_numpy()[~h], va.is_fraud.to_numpy()[~h])(va.raw.to_numpy()[h])
            sv = costs(va.is_fraud, va.amt, decide("ev_cap", dv, pv, va.amt.to_numpy()), dv)["savings"]
            ph = fit(m, va.raw.to_numpy(), va.is_fraud.to_numpy())(ho.raw.to_numpy())
            d = decide("ev_cap", dh, ph, ho.amt.to_numpy())
            sh = costs(ho.is_fraud, ho.amt, d, dh)["savings"]
            rows.append({"модель": name, "калибровка": m, "экономия valid": sv, "экономия holdout": sh,
                         "ложных holdout": int(((d == 1) & (ho.is_fraud == 0)).sum()),
                         "разных значений p": len(np.unique(ph))})
    t = pd.DataFrame(rows)
    (W2 / "calibration.md").write_text("# Калибровка: ступеньки против гладкой\n\n" + md_table(t), encoding="utf-8")
    print(md_table(t))


if __name__ == "__main__":
    main()
