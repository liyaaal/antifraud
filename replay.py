"""Подача серии операций holdout в сервис из терминала (альтернатива кнопке «Серия» в интерфейсе).

python replay.py --n 150 --start 0 --pause 0.1

Каждая операция идёт через POST /predict (без is_fraud), затем её метка — через POST /label.
"""
import argparse
import json
import time

import pandas as pd
import requests

from service.prepare import HOLDOUT_CSV


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--pause", type=float, default=0.1)
    a = ap.parse_args()
    rows = pd.read_csv(HOLDOUT_CSV, low_memory=False).iloc[a.start:a.start + a.n]
    tp = fp = fn = err = 0
    for i, row in rows.iterrows():
        y = int(row["is_fraud"])
        payload = {k: v for k, v in json.loads(row.drop(labels=["is_fraud"]).to_json()).items() if v is not None}
        r = requests.post(f"{a.api}/predict", json=payload, timeout=30)
        if r.status_code != 200:
            err += 1
            print(f"{i}: HTTP {r.status_code}")
            continue
        res = r.json()
        requests.post(f"{a.api}/label", json={"transaction_id": res["transaction_id"], "is_fraud": y}, timeout=30)
        pred = res["is_fraud_pred"]
        tp += pred and y
        fp += pred and not y
        fn += (not pred) and y
        if pred or y:
            print(f"{i}: {row['trans_date_trans_time']} {row['category']:<14} {row['amt']:>8.2f}  "
                  f"оценка {res['fraud_score']:.3f}  решение {'ФРОД' if pred else 'не фрод'}  факт {'фрод' if y else 'честная'}")
        time.sleep(a.pause)
    print(f"Готово: {len(rows)} операций, поймано {tp}, ложных тревог {fp}, пропущено {fn}, ошибок {err}")


if __name__ == "__main__":
    main()
