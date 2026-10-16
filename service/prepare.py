"""Подготовка данных для сервиса (неделя 3). Запускается один раз перед первым стартом.

python -m service.prepare                         # holdout = 02.12 22:00 – 11.12 22:00 (2020) из fraudTest
python -m service.prepare --holdout-file path.csv # holdout, выданный преподавателем

Что делает:
1. data/holdout.csv — операции, которые будем подавать в сервис (сырые поля датасета + is_fraud).
2. data/cache/service_history.parquet — стартовая история карт ДО начала holdout, без меток:
   история обучения (artifacts/final/history.parquet, fraudTrain) + операции fraudTest раньше holdout.
   Нужна, чтобы признаки по истории карты (блоки a, b, e) считались так же, как в score.py.

Почему начало декабря 2020. Отложенного периода, не использованного ни в обучении, ни в сравнении версий,
у нас не осталось: fraudTrain ушёл на train/valid/holdout, fraudTest — на сравнение v1/v2 недели 2.
По ТЗ такой период выдаёт преподаватель. До этого демонстрируем на 9 сутках декабря 2020 из fraudTest (02.12 22:00 – 11.12 22:00): на нём модель
не обучалась и ничего не настраивалось (он был только в итоговом подсчёте сравнения v1/v2).
Начало 02.12 22:00 выбрано, чтобы в первой серии из 200 операций попала вечерняя волна мошенничества
(13 операций): при доле фрода 0,4% в случайных 200 операциях в среднем меньше одной.
"""
import argparse
from pathlib import Path

import pandas as pd

from src.data import READ_DTYPES, ROOT, clean
from service.scoring import SERVICE_HISTORY

HOLDOUT_CSV = ROOT / "data" / "holdout.csv"
TRAIN_HISTORY = ROOT / "artifacts" / "final" / "history.parquet"


def find_test_csv() -> Path:
    for p in [ROOT / "data" / "fraudTest.csv", ROOT.parent / "data" / "fraudTest.csv"]:
        if p.exists():
            return p
    raise SystemExit("Не найден fraudTest.csv: положите его в data/ или укажите --test-csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-csv", default=None)
    ap.add_argument("--start", default="2020-12-02 22:00", help="начало holdout (если файл holdout не выдан)")
    ap.add_argument("--end", default="2020-12-11 22:00", help="конец holdout, не включая (файл до 25 МБ — грузится на GitHub)")
    ap.add_argument("--holdout-file", default=None, help="готовый holdout от преподавателя")
    a = ap.parse_args()

    test_path = Path(a.test_csv) if a.test_csv else find_test_csv()
    test = pd.read_csv(test_path, dtype=READ_DTYPES, low_memory=False)
    test = test.drop(columns=[c for c in test.columns if c.startswith("Unnamed")])
    ts = pd.to_datetime(test["trans_date_trans_time"])

    if a.holdout_file:
        hold = pd.read_csv(a.holdout_file, dtype=READ_DTYPES, low_memory=False)
        hold = hold.drop(columns=[c for c in hold.columns if c.startswith("Unnamed")])
        start = pd.to_datetime(hold["trans_date_trans_time"]).min()
    else:
        start = pd.Timestamp(a.start)
        hold = test[(ts >= start) & (ts < pd.Timestamp(a.end))]
    hold = hold.assign(_t=pd.to_datetime(hold["trans_date_trans_time"])) \
        .sort_values(["_t", "trans_num"], kind="mergesort").drop(columns="_t").reset_index(drop=True)

    before = test[(ts < start) & ~test["trans_num"].isin(set(hold["trans_num"]))]
    hist = pd.concat([pd.read_parquet(TRAIN_HISTORY), clean(before).drop(columns="is_fraud")], ignore_index=True)
    hist = hist[hist["ts"] < start].sort_values(["ts", "trans_num"], kind="mergesort").reset_index(drop=True)

    HOLDOUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    SERVICE_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    hold.to_csv(HOLDOUT_CSV, index=False)
    hist.to_parquet(SERVICE_HISTORY, index=False)
    nf = int(hold["is_fraud"].sum()) if "is_fraud" in hold.columns else 0
    print(f"holdout: {len(hold)} операций с {start}, мошеннических {nf} -> {HOLDOUT_CSV}")
    print(f"история карт: {len(hist)} операций до {hist['ts'].max()} -> {SERVICE_HISTORY}")


if __name__ == "__main__":
    main()
