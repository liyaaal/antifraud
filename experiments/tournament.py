"""Турнир: три решения участниц и обмен моделями между наборами признаков.

Все прогоны — на valid, одной и той же денежной политикой (ev_cap + честная калибровка),
кроме строки «как было» (top_p). Для каждого прогона считаем:
  - экономию и долю от потолка (идеальная модель при лимите 0,3%);
  - 90% интервал разницы с базовой моделью (бутстрэп по дням valid);
  - экономию, если бы аналитиков было втрое больше (лимит 1%);
  - стресс-тест: фрода втрое больше.

python -m experiments.tournament  ->  reports/tournament.csv, reports/tournament.md
"""
import numpy as np
import pandas as pd

from src.data import ROOT
from src.economics import costs, decide, paired_bootstrap, top_k_per_day
from src.evaluate import DEFAULTS, feature_list, run
from src.pipeline import load_dataset

REJECTED = {
    # Гипотеза отвергнута или признак — контроль (см. reports/feature_map.csv).
    "a_new_merchant", "a_geo_km", "a_amt_down", "b_cnt_24h_window", "b_sess_cat_n",
}
C_TREE_REJECTED = {"c_risk_cat_hour", "c_risk_cat_amtbin", "c_risk_age_cat", "c_risk_merchant"}

MODELS = {
    "LogReg": {"model": "logreg"},
    "LightGBM": {"model": "lgbm"},
    "LightGBM монотонный": {"model": "lgbm", "monotone": True},
    "LightGBM, учит деньгам": {"model": "lgbm", "sample_weight": "cost"},
}


def cfg_of(name, blocks, **kw):
    return {**DEFAULTS, "name": name, "author": "team", "blocks": blocks, "calibration": "isotonic",
            "policy": "ev_cap", **kw}


def main():
    df, part, X, states, b = load_dataset(["base", "a", "b", "c"])
    va = (part == "valid").to_numpy()
    y = df.loc[va, "is_fraud"].to_numpy()
    amt = df.loc[va, "amt"].to_numpy(dtype="float64")
    day = df.loc[va, "ts"].dt.normalize()
    ceil3 = costs(y, amt, top_k_per_day(day, np.where(y == 1, amt, -np.inf), eligible=y == 1), day,
                  fraud_weight=3)["savings"]

    def fs(blocks, drop=()):
        f = feature_list(cfg_of("x", blocks))
        return [c for c in f if c not in REJECTED and c not in set(drop)]

    SETS = {
        "сырые поля": (["base"], fs(["base"])),
        "+ A (профиль)": (["base", "a"], fs(["base", "a"])),
        "+ B (ритм)": (["base", "b"], fs(["base", "b"])),
        "+ C (среда)": (["base", "c"], fs(["base", "c"])),
        "+ A + B": (["base", "a", "b"], fs(["base", "a", "b"])),
        "+ A + B + C": (["base", "a", "b", "c"], fs(["base", "a", "b", "c"])),
        "+ A + B + C5": (["base", "a", "b", "c"], fs(["base", "a", "b", "c"], drop=C_TREE_REJECTED)),
    }

    rows, ref = [], None
    runs = [("как было: база, ранжирование по вероятности", "сырые поля", "LightGBM", {"policy": "top_p", "calibration": "none"})]
    runs += [("", s, m, {}) for s in SETS for m in MODELS]
    runs += [("решение A", "+ A (профиль)", "LogReg", {}), ("решение B", "+ B (ритм)", "LightGBM монотонный", {}),
             ("решение C", "+ C (среда)", "LightGBM, учит деньгам", {})]
    for label, sname, mname, extra in runs:
        blocks, feats = SETS[sname]
        cfg = cfg_of(f"T|{sname}|{mname}", blocks, **MODELS[mname], **extra)
        res = run(cfg, feats, df, part, X, "valid", note="турнир")
        p = res["p"]
        # Стресс-тест: фрода втрое больше. Вероятности сдвигаются по априорной доле, строки фрода весят ×3.
        p3 = 3 * p / (3 * p + 1 - p)
        d3 = decide(cfg["policy"], day, p3, amt)
        s3 = costs(y, amt, d3, day, fraud_weight=3)
        if sname == "сырые поля" and mname == "LightGBM" and not extra:
            ref = res
        rows.append({"решение": label, "признаки": sname, "модель": mname, "политика": cfg["policy"],
                     "n_признаков": len(feats), "экономия": round(res["savings"], 2),
                     "доля_потолка": round(res["savings"] / res["ceiling"], 4),
                     "pr_auc": round(res["pr_auc"], 4), "recall_по_деньгам": round(res["recall_amt"], 4),
                     "точность_отправленных": round(res["precision"], 4),
                     "в_день_аналитику": round(res["flagged_per_day"], 2),
                     "экономия_при_лимите_1%": round(res["savings_cap1"], 2),
                     "экономия_при_фроде_x3": round(s3["savings"], 2),
                     "доля_потолка_x3": round(s3["savings"] / ceil3, 4),
                     "_per_day": res["per_day_savings"]})
    for r in rows:
        lo, hi = paired_bootstrap(r["_per_day"] - ref["per_day_savings"])
        r["разница_с_базой"] = round(r["экономия"] - ref["savings"], 2)
        r["интервал_90%"] = f"[{lo:,.0f}; {hi:,.0f}]".replace(",", " ")
    out = pd.DataFrame(rows).drop(columns="_per_day")
    out.to_csv(ROOT / "reports" / "tournament.csv", index=False, encoding="utf-8")

    piv = out[out["решение"] == ""].pivot(index="признаки", columns="модель", values="экономия").reindex(SETS)[list(MODELS)]
    lines = ["# Турнир (valid, 21.02–21.04.2020)", "",
             f"Потери без системы: {ref['loss_none']:,.2f} у.е. Потолок (идеальная модель при лимите 0,3%): "
             f"{ref['ceiling']:,.2f} у.е.".replace(",", " "), "",
             "## Экономия, у.е.: наборы признаков × модели (политика ev_cap)", "", piv.round(0).to_markdown(), "",
             "## Все прогоны", "", out.to_markdown(index=False)]
    (ROOT / "reports" / "tournament.md").write_text("\n".join(lines), encoding="utf-8")
    print(piv.round(0).to_string())


if __name__ == "__main__":
    main()
