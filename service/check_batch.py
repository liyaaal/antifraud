"""Сверка сервиса с пакетным score.py (дополнительный пункт ТЗ недели 3).

python -m service.check_batch --n 300

Первые N операций holdout считаются двумя способами:
1) по одной, как в сервисе (OnlineScorer — та же история карт, операции дописываются по очереди);
2) пакетом, функцией score_frame из score.py с той же стартовой историей.
Печатает максимальное расхождение вероятностей и совпадение групп риска.
"""
import argparse
import contextlib
import io

import numpy as np
import pandas as pd

from score import score_frame
from service.prepare import HOLDOUT_CSV
from service.scoring import SERVICE_HISTORY, OnlineScorer
from src.data import READ_DTYPES
from src.risk import risk_level


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    a = ap.parse_args()
    hold = pd.read_csv(HOLDOUT_CSV, dtype=READ_DTYPES, low_memory=False).head(a.n)

    online = OnlineScorer()
    p_on = []
    for r in hold.drop(columns=["is_fraud"], errors="ignore").to_dict("records"):
        p_on.append(online.score(r)["p"])

    art = dict(online.art)
    art["history"] = SERVICE_HISTORY
    with contextlib.redirect_stdout(io.StringIO()):
        batch = score_frame(hold, art, with_reasons=False)
    p_b = batch["fraud_probability"].to_numpy()
    p_on = np.asarray(p_on)
    diff = np.abs(p_on - p_b)
    same = (risk_level(p_on) == risk_level(p_b)).mean()
    print(f"Операций: {len(hold)}")
    print(f"Макс. расхождение вероятности: {diff.max():.2e}, среднее: {diff.mean():.2e}")
    print(f"Совпадение группы риска: {same:.1%}")
    print("ОК: сервис считает так же, как score.py" if diff.max() < 1e-6 else "ВНИМАНИЕ: есть расхождения")


if __name__ == "__main__":
    main()
