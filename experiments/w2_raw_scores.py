"""Неделя 2: сырые (до калибровки) скоры моделей v1/v2 на valid и holdout — для разбора калибровки.

python -m experiments.w2_raw_scores --config configs/final.yaml
Пишет reports/preds/<name>_raw.parquet (trans_num, part, raw).
"""
import argparse

import pandas as pd

from src.evaluate import feature_list, load_config, weights
from src.models import make_model
from src.pipeline import load_dataset
from src.data import ROOT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    a = ap.parse_args()
    cfg = load_config(a.config)
    df, part, X, states, b = load_dataset(cfg["blocks"])
    feats = feature_list(cfg)
    tr, va = (part == "train").to_numpy(), (part == "valid").to_numpy()
    y, amt = df["is_fraud"].to_numpy(), df["amt"].to_numpy(dtype="float64")
    m = make_model(cfg["model"], cfg["model_params"])
    m.fit(X.loc[tr, feats], y[tr], X.loc[va, feats], y[va], sample_weight=weights(cfg, y[tr], amt[tr]), monotone={})
    ev = (part != "train").to_numpy()
    out = pd.DataFrame({"trans_num": df.loc[ev, "trans_num"].to_numpy(), "part": part[ev].to_numpy(),
                        "raw": m.predict_proba(X.loc[ev, feats])})
    out.to_parquet(ROOT / "reports" / "preds" / f"{cfg['name']}_raw.parquet", index=False)
    print(cfg["name"], m.best_iteration, len(out))


if __name__ == "__main__":
    main()
