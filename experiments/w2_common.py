"""Неделя 2: общие функции оценки (деньги + метрики) для выхода score.py на размеченном периоде."""
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from src.data import ROOT, read_csv
from src.economics import costs, top_k_per_day

W2 = ROOT / "reports" / "week2" / "tables"
TEST_CSV = ROOT / "data" / "fraudTest.csv"


def load_labeled(path=TEST_CSV) -> pd.DataFrame:
    cache = ROOT / "data" / "cache" / (path.stem + "_clean.parquet")
    if cache.exists():
        return pd.read_parquet(cache)
    df = read_csv(path)
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    return df


def summarize(df: pd.DataFrame, p: np.ndarray, decision: np.ndarray) -> dict:
    """df — очищенные операции с is_fraud; p, decision выровнены по df."""
    y = df["is_fraud"].to_numpy()
    amt = df["amt"].to_numpy(dtype="float64")
    day = df["ts"].dt.normalize()
    r = costs(y, amt, decision, day)
    oracle = top_k_per_day(day, np.where(y == 1, amt, -np.inf), eligible=y == 1)
    ceil = costs(y, amt, oracle, day)["savings"]
    d = decision.astype(bool)
    yb = y.astype(bool)
    n_days = day.nunique()
    return {
        "days": int(n_days), "ops": int(len(y)), "fraud_ops": int(yb.sum()), "fraud_rate": float(yb.mean()),
        "loss_none": r["loss_none"], "savings": r["savings"], "ceiling": ceil, "pct_of_ceiling": r["savings"] / ceil,
        "savings_per_day": r["savings"] / n_days, "ceiling_per_day": ceil / n_days,
        "pr_auc": float(average_precision_score(y, p)), "roc_auc": float(roc_auc_score(y, p)),
        "precision": r["precision"], "recall_cnt": r["recall_cnt"], "recall_amt": r["recall_amt"],
        "sensitivity": r["recall_cnt"], "specificity": float((~d & ~yb).sum() / (~yb).sum()),
        "flagged": int(d.sum()), "tp": int((d & yb).sum()), "fp": int((d & ~yb).sum()),
        "flagged_per_day": r["flagged_per_day"], "fp_per_day": float((d & ~yb).sum() / n_days),
        "cap_violated": r["cap_violated"],
    }
