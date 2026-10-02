"""Обучение и сохранение артефактов (CLAUDE.md, раздел 12).

python train.py --config configs/final.yaml

Модель учится на train (до 21.02.2020), ранняя остановка и калибровка — на valid.
Сохраняется ровно та модель, которая оценивалась на холдауте: что проверили, то и сдаём.
"""
import argparse
import json
import pickle
import platform
import time
from importlib.metadata import version

import numpy as np

from src.data import ROOT
from src.evaluate import feature_list, fit_predict, load_config, score_split
from src.features import get_block
from src.models import SEED
from src.pipeline import load_dataset


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/final.yaml")
    a = ap.parse_args()
    t0 = time.time()
    np.random.seed(SEED)
    cfg = load_config(a.config)
    out = ROOT / "artifacts" / cfg["name"]
    out.mkdir(parents=True, exist_ok=True)

    df, part, X, states, b = load_dataset(cfg["blocks"])
    feats = feature_list(cfg)
    model, cal, params, p_va, va, fit_sec = fit_predict(cfg, feats, df, part, X, eval_part="valid")
    res, _ = score_split(cfg, p_va, df, va, params)
    print(f"valid: экономия {res['savings']:,.2f} у.е., доля потолка {res['savings'] / res['ceiling']:.1%}")

    (out / "model.pkl").write_bytes(pickle.dumps(model))
    (out / "calibrator.pkl").write_bytes(pickle.dumps(cal))
    (out / "states.pkl").write_bytes(pickle.dumps(states))
    # История операций без меток: у знакомых карт в score.py признаки продолжаются «с того же места».
    df.drop(columns=["is_fraud"]).to_parquet(out / "history.parquet", index=False)
    meta = {
        "config": cfg, "features": feats, "policy_params": params,
        "split": {k: str(v) for k, v in b.items()},
        "block_constants": {"a": {"ALPHA": get_block("a").ALPHA, "K_AMT": get_block("a").K_AMT},
                            "b": {"SESSION_GAP_H": get_block("b").SESSION_GAP_H, "M_RATE": get_block("b").M_RATE},
                            "c": {"DELAY_DAYS": get_block("c").DELAY_DAYS, "M_SMOOTH": get_block("c").M_SMOOTH}},
        "best_iteration": getattr(model, "best_iteration", None), "seed": SEED,
        "valid_savings": res["savings"], "python": platform.python_version(),
        "libs": {p: version(p) for p in ["numpy", "pandas", "scikit-learn", "lightgbm", "pyarrow"]},
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"Артефакты: {out}  ({time.time() - t0:.0f} c)")


if __name__ == "__main__":
    main()
