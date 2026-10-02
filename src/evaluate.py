"""Единый «судья» (CLAUDE.md, раздел 9).

python -m src.evaluate --config configs/b.yaml                       # весь конфиг
python -m src.evaluate --config configs/b.yaml --add b_int_1h b_int_24h   # добавлять признаки по одному
python -m src.evaluate --config configs/final.yaml --holdout         # только финал, один раз

Каждый прогон дописывает строку в reports/experiments.csv.
"""
import argparse
import datetime as dt
import json
import os
import time

import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import average_precision_score

from src.calibration import Calibrator
from src.data import ROOT
from src.economics import costs, decide, fit_ev_threshold, paired_bootstrap, top_k_per_day
from src.features import get_block
from src.models import make_model
from src.pipeline import load_dataset

REPORTS = ROOT / "reports"
EXPERIMENTS = REPORTS / "experiments.csv"
PREDS = REPORTS / "preds"

DEFAULTS = {"features": None, "exclude": [], "model": "lgbm", "model_params": {}, "monotone": False,
            "sample_weight": "none", "calibration": "none", "policy": "top_p", "author": "team"}


def load_config(path) -> dict:
    cfg = yaml.safe_load(open(path, encoding="utf-8"))
    return {**DEFAULTS, **cfg}


def feature_list(cfg: dict) -> list[str]:
    if cfg["features"]:
        feats = list(cfg["features"])
    else:
        feats = [f for b in cfg["blocks"] for f in get_block(b).FEATURES]
    return [f for f in feats if f not in set(cfg["exclude"] or [])]


def monotone_map(cfg: dict) -> dict:
    if not cfg["monotone"]:
        return {}
    m = {}
    for b in cfg["blocks"]:
        m.update(getattr(get_block(b), "MONOTONE", {}))
    return m


def weights(cfg, y, amt):
    if cfg["sample_weight"] == "cost":
        # Фрод весит столько, сколько стоит его пропустить; честная операция — сколько стоит её зря остановить.
        return np.where(y == 1, amt + 5.0, 28.0)
    return None


def fit_predict(cfg, feats, df, part, X, eval_part="valid"):
    """Обучение на train (ранняя остановка по valid), калибровка и порог — по valid, оценка на eval_part."""
    tr, va, ev = (part == "train").to_numpy(), (part == "valid").to_numpy(), (part == eval_part).to_numpy()
    y = df["is_fraud"].to_numpy()
    amt = df["amt"].to_numpy(dtype="float64")
    model = make_model(cfg["model"], cfg["model_params"])
    t0 = time.time()
    model.fit(X.loc[tr, feats], y[tr], X.loc[va, feats], y[va], sample_weight=weights(cfg, y[tr], amt[tr]),
              monotone=monotone_map(cfg))
    fit_sec = time.time() - t0
    p_va_raw = model.predict_proba(X.loc[va, feats])
    cal = Calibrator(cfg["calibration"]).fit(p_va_raw, y[va])
    day_va = df.loc[va, "ts"].dt.normalize()
    if cfg["calibration"] != "none":
        # Честная оценка на valid: калибратор для первой половины valid учится на второй и наоборот.
        first = (day_va < day_va.min() + pd.Timedelta(days=30)).to_numpy()
        p_va = np.empty(len(p_va_raw))
        for h in (first, ~first):
            p_va[h] = Calibrator(cfg["calibration"]).fit(p_va_raw[~h], y[va][~h]).transform(p_va_raw[h])
    else:
        p_va = cal.transform(p_va_raw)
    params = {}
    if cfg["policy"] == "ev_thr":
        params["ev_threshold"] = fit_ev_threshold(day_va, p_va, amt[va])
    p_ev = p_va if eval_part == "valid" else cal.transform(model.predict_proba(X.loc[ev, feats]))
    return model, cal, params, p_ev, ev, fit_sec


def score_split(cfg, p, df, ev, params):
    y = df.loc[ev, "is_fraud"].to_numpy()
    amt = df.loc[ev, "amt"].to_numpy(dtype="float64")
    day = df.loc[ev, "ts"].dt.normalize()
    d = decide(cfg["policy"], day, p, amt, params=params)
    res = costs(y, amt, d, day)
    res["pr_auc"] = float(average_precision_score(y, p))
    rule = costs(y, amt, decide("rule_amt", day, p, amt), day)
    res["rule_amt_savings"] = rule["savings"]
    # Потолок: «оракул» знает правду и берёт самые дорогие фроды дня в пределах лимита.
    oracle = top_k_per_day(day, np.where(y == 1, amt, -np.inf), eligible=y == 1)
    res["ceiling"] = costs(y, amt, oracle, day)["savings"]
    # Запас на будущее: сколько дала бы та же модель, если бы аналитиков было втрое больше (1%).
    res["savings_cap1"] = costs(y, amt, decide(cfg["policy"], day, p, amt, capacity=0.01, params=params), day)["savings"]
    res["rule_amt_per_day"] = rule["per_day_savings"]
    return res, d


def baseline_savings(split: str):
    # Линейка — базовая модель под денежной политикой (см. decision_log.md, решение 5).
    f = REPORTS / f"baseline_ev_{split}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return None


def log_row(row: dict):
    REPORTS.mkdir(exist_ok=True)
    cols = ["datetime", "author", "config", "split", "model", "policy", "calibration", "sample_weight",
            "monotone", "n_features", "added_feature", "pr_auc", "savings", "delta_savings", "delta_ci_low",
            "delta_ci_high", "delta_pr_auc", "savings_vs_baseline", "savings_vs_rule_amt", "recall_cnt",
            "recall_amt", "precision", "flagged_per_day", "cap_violated", "best_iter", "fit_sec", "note",
            "ceiling", "pct_of_ceiling", "savings_cap1pct"]
    r = {c: row.get(c, "") for c in cols}
    if EXPERIMENTS.exists():
        old = pd.read_csv(EXPERIMENTS, encoding="utf-8")
        if list(old.columns) != cols:
            old.reindex(columns=cols).to_csv(EXPERIMENTS, index=False, encoding="utf-8")
    header = not EXPERIMENTS.exists()
    pd.DataFrame([r])[cols].to_csv(EXPERIMENTS, mode="a", header=header, index=False, encoding="utf-8")


def run(cfg, feats, df, part, X, split="valid", added="", prev=None, note=""):
    model, cal, params, p, ev, fit_sec = fit_predict(cfg, feats, df, part, X, eval_part=split)
    res, d = score_split(cfg, p, df, ev, params)
    base = baseline_savings(split)
    row = {
        "datetime": dt.datetime.now().isoformat(timespec="seconds"), "author": cfg["author"],
        "config": cfg["name"], "split": split, "model": cfg["model"], "policy": cfg["policy"],
        "calibration": cfg["calibration"], "sample_weight": cfg["sample_weight"], "monotone": cfg["monotone"],
        "n_features": len(feats), "added_feature": added, "pr_auc": round(res["pr_auc"], 5),
        "savings": round(res["savings"], 2),
        "savings_vs_baseline": round(res["savings"] - base["savings"], 2) if base else "",
        "savings_vs_rule_amt": round(res["savings"] - res["rule_amt_savings"], 2),
        "recall_cnt": round(res["recall_cnt"], 4), "recall_amt": round(res["recall_amt"], 4),
        "precision": round(res["precision"], 4), "flagged_per_day": round(res["flagged_per_day"], 2),
        "cap_violated": res["cap_violated"], "best_iter": getattr(model, "best_iteration", ""),
        "fit_sec": round(fit_sec, 1), "note": note, "ceiling": round(res["ceiling"], 2),
        "pct_of_ceiling": round(res["savings"] / res["ceiling"], 4), "savings_cap1pct": round(res["savings_cap1"], 2),
    }
    if prev is not None:
        delta = res["per_day_savings"] - prev["per_day_savings"]
        lo, hi = paired_bootstrap(delta)
        row.update({"delta_savings": round(res["savings"] - prev["savings"], 2), "delta_ci_low": round(lo, 2),
                    "delta_ci_high": round(hi, 2), "delta_pr_auc": round(res["pr_auc"] - prev["pr_auc"], 5)})
    log_row(row)
    print(f"[{cfg['name']} | {split}] {added or 'все признаки'}: savings={res['savings']:.2f} "
          f"pr_auc={res['pr_auc']:.4f} recall_amt={res['recall_amt']:.3f} flagged/day={res['flagged_per_day']:.2f} "
          f"потолок={res['savings'] / res['ceiling']:.1%} при_лимите_1%={res['savings_cap1']:.0f}"
          + (f"  Δ={row['delta_savings']} [{row['delta_ci_low']}; {row['delta_ci_high']}]" if prev else ""))
    res.update({"model": model, "cal": cal, "params": params, "p": p, "decision": d, "ev_mask": ev})
    return res


def save_preds(name, split, df, res):
    PREDS.mkdir(parents=True, exist_ok=True)
    ev = res["ev_mask"]
    out = pd.DataFrame({"trans_num": df.loc[ev, "trans_num"].to_numpy(), "p": res["p"], "decision": res["decision"]})
    out.to_parquet(PREDS / f"{name}_{split}.parquet", index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--add", nargs="*", default=None, help="добавлять признаки по одному в этом порядке")
    ap.add_argument("--holdout", action="store_true")
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    cfg = load_config(a.config)
    split = "holdout" if a.holdout else "valid"
    df, part, X, states, b = load_dataset(cfg["blocks"])
    feats = feature_list(cfg)

    if a.add:
        start = [f for f in feats if f not in a.add]
        prev = run(cfg, start, df, part, X, split, added="(старт)", note=a.note)
        cur = list(start)
        for f in a.add:
            cur.append(f)
            prev = run(cfg, cur, df, part, X, split, added=f, prev=prev, note=a.note)
        save_preds(cfg["name"], split, df, prev)
        return

    res = run(cfg, feats, df, part, X, split, note=a.note)
    save_preds(cfg["name"], split, df, res)
    if cfg["name"].startswith("baseline"):
        (REPORTS / f"{cfg['name']}_{split}.json").write_text(json.dumps({"savings": res["savings"]}), encoding="utf-8")
        (REPORTS / f"rule_amt_{split}.json").write_text(json.dumps({"savings": res["rule_amt_savings"],
                                                                   "loss_none": res["loss_none"]}), encoding="utf-8")
    imp = res["model"].importance().sort_values(key=np.abs, ascending=False)
    print("Важность (для справки, не для защиты):")
    print(imp.head(15).round(3).to_string())


if __name__ == "__main__":
    main()
