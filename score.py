"""Скоринг новых операций (CLAUDE.md, раздел 12). Ничего не обучает и не ходит в сеть.

python score.py --input <входной_csv> --output <выходной_csv> [--artifacts artifacts/final]

Выход: trans_num, fraud_probability, decision (0/1), reason_1..3 (причины только при decision = 1).
"""
import argparse
import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src.data import ROOT, clean, READ_DTYPES
from src.economics import decide
from src.pipeline import compute
from src.reasons import top_reasons


def load_artifacts(path: Path):
    return {
        "model": pickle.loads((path / "model.pkl").read_bytes()),
        "cal": pickle.loads((path / "calibrator.pkl").read_bytes()),
        "states": pickle.loads((path / "states.pkl").read_bytes()),
        "meta": json.loads((path / "meta.json").read_text(encoding="utf-8")),
        "history": path / "history.parquet",
    }


def score_frame(raw: pd.DataFrame, art: dict, with_reasons: bool = True) -> pd.DataFrame:
    meta = art["meta"]
    cfg = meta["config"]
    raw = raw.drop(columns=[c for c in ["is_fraud"] if c in raw.columns])   # метки на входе не используем никогда
    new = clean(raw)
    if new["ts"].isna().any():   # непарсящаяся дата не должна ронять скоринг
        new["ts"] = new["ts"].fillna(new["ts"].dropna().max() if new["ts"].notna().any() else pd.Timestamp("2020-06-22"))
    new["_input"] = True

    hist = pd.read_parquet(art["history"])
    hist = hist[~hist["trans_num"].isin(set(new["trans_num"]))]
    hist = hist[hist["ts"] <= new["ts"].max()]          # будущее относительно входа не нужно
    hist["_input"] = False
    df = pd.concat([hist, new], ignore_index=True)
    df = df.sort_values(["ts", "trans_num"], kind="mergesort").reset_index(drop=True)

    X = compute(df, cfg["blocks"], art["states"])
    inp = df["_input"].to_numpy()
    Xi = X.loc[inp, meta["features"]]
    p = art["cal"].transform(art["model"].predict_proba(Xi))
    di = df.loc[inp]
    day = di["ts"].dt.normalize()
    decision = decide(cfg["policy"], day, p, di["amt"].to_numpy(dtype="float64"), params=meta["policy_params"])

    out = pd.DataFrame({"trans_num": di["trans_num"].to_numpy(), "fraud_probability": np.round(p, 6),
                        "decision": decision.astype(int)}, index=di.index)
    for k in range(1, 4):
        out[f"reason_{k}"] = ""
    flagged = out.index[out["decision"] == 1]
    if with_reasons and len(flagged):
        contrib = art["model"].contributions(X.loc[flagged, meta["features"]])
        rows = pd.concat([di.loc[flagged, ["amt"]], X.loc[flagged].drop(columns=["amt", "category"], errors="ignore")],
                         axis=1)
        rows["category"] = di.loc[flagged, "category"].astype("str")
        rows["hour"] = di.loc[flagged, "ts"].dt.hour
        rows["minute"] = di.loc[flagged, "ts"].dt.minute
        out.loc[flagged, ["reason_1", "reason_2", "reason_3"]] = top_reasons(contrib, rows).to_numpy()
    # Порядок строк — как во входном файле.
    order = pd.Series(np.arange(len(raw)), index=raw["trans_num"].astype("str").to_numpy())
    return out.assign(_o=out["trans_num"].map(order)).sort_values("_o").drop(columns="_o").reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--artifacts", default=str(ROOT / "artifacts" / "final"))
    a = ap.parse_args()
    t0 = time.time()
    art = load_artifacts(Path(a.artifacts))
    raw = pd.read_csv(a.input, dtype={k: v for k, v in READ_DTYPES.items()}, low_memory=False)
    out = score_frame(raw, art)
    out.to_csv(a.output, index=False, encoding="utf-8")
    try:
        import psutil

        mem = psutil.Process().memory_info().peak_wset / 2**30 if hasattr(psutil.Process().memory_info(), "peak_wset") \
            else psutil.Process().memory_info().rss / 2**30
        mem_s = f", пик памяти {mem:.2f} ГБ"
    except Exception:
        mem_s = ""
    print(f"Готово: {len(out)} операций, отправлено аналитикам {int(out['decision'].sum())}, "
          f"{time.time() - t0:.1f} c{mem_s} -> {a.output}")


if __name__ == "__main__":
    main()
