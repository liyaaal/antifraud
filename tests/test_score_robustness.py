"""Надёжность score.py (TASK_B):
  1. «тот же код»: вероятности score.py на холдауте совпадают с оценкой в evaluate (до 1e-6);
  2. перемешанный вход даёт тот же ответ, что и отсортированный;
  3. незнакомые карта / мерчант / категория / город, файл из одной строки, две операции карты в одну секунду,
     битая дата — не падает, вероятности в [0, 1];
  4. нагрузка: 0,55 млн строк через командную строку — время и пиковая память.

python -m tests.test_score_robustness [--skip-load]
"""
import argparse
import subprocess
import sys
import time

import numpy as np
import pandas as pd

from score import load_artifacts, score_frame
from src.data import DATA_DIR, ROOT, TRAIN_CSV
from src.split import boundaries

ART = ROOT / "artifacts" / "final"
TMP = DATA_DIR / "test_inputs"


def raw_train():
    raw = pd.read_csv(TRAIN_CSV, dtype={"cc_num": "int64", "trans_num": "str"}, low_memory=False)
    raw = raw.drop(columns=[c for c in raw.columns if c.startswith("Unnamed")])
    return raw


def check(name, ok, extra=""):
    print(f"{'OK    ' if ok else 'ОШИБКА'} {name} {extra}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-load", action="store_true")
    a = ap.parse_args()
    TMP.mkdir(parents=True, exist_ok=True)
    art = load_artifacts(ART)
    raw = raw_train()
    ts = pd.to_datetime(raw["trans_date_trans_time"])
    ho = raw[ts >= boundaries(ts)["holdout_start"]].copy()
    results = []

    # 1–2. Тот же код и порядок строк.
    t0 = time.time()
    shuffled = ho.sample(frac=1.0, random_state=1).drop(columns="is_fraud")
    out_s = score_frame(shuffled, art)
    ref = pd.read_parquet(ROOT / "reports" / "preds" / "final_holdout.parquet")
    m = out_s.merge(ref, on="trans_num")
    diff = float(np.abs(m["fraud_probability"] - m["p"]).max())
    results.append(check("вероятности score.py = evaluate на холдауте", len(m) == len(ho) and diff < 1e-6,
                         f"(строк {len(m)}, макс. расхождение {diff:.2e}, {time.time() - t0:.0f} c)"))
    results.append(check("решения score.py = evaluate", bool((m["decision_x"] == m["decision_y"]).all()),
                         f"(отправлено {int(m['decision_x'].sum())})"))
    out_o = score_frame(ho.drop(columns="is_fraud"), art)
    mm = out_o.merge(out_s, on="trans_num")
    results.append(check("перемешанный вход = отсортированный",
                         float(np.abs(mm["fraud_probability_x"] - mm["fraud_probability_y"]).max()) == 0.0))
    results.append(check("порядок строк выхода = порядок входа",
                         list(out_s["trans_num"]) == list(shuffled["trans_num"])))
    fl = out_s[out_s["decision"] == 1]
    results.append(check("у каждой отправленной операции есть хотя бы одна причина", bool((fl["reason_1"] != "").all()),
                         f"(без причин: {int((fl['reason_1'] == '').sum())})"))

    # 3. Незнакомое и странное.
    base = ho.head(200).drop(columns="is_fraud").copy()
    cases = {}
    x = base.copy(); x["cc_num"] = 9999000011112222; x["trans_num"] = "new_card_" + x.index.astype(str)
    cases["незнакомая карта (200 операций подряд)"] = x
    x = base.head(20).copy(); x["merchant"] = "fraud_Совсем Новый Магазин"; x["category"] = "crypto_net"
    x["city"] = "Nowhere"; x["trans_num"] = "new_cat_" + x.index.astype(str)
    cases["незнакомые мерчант, категория и город"] = x
    cases["файл из одной строки"] = base.head(1).assign(trans_num="one_row")
    x = base.head(2).copy(); x["cc_num"] = 5555000011112222; x["trans_date_trans_time"] = x["trans_date_trans_time"].iloc[0]
    x["trans_num"] = ["tie_1", "tie_2"]
    cases["две операции карты в одну секунду"] = x
    x = base.head(3).copy(); x.loc[x.index[0], "trans_date_trans_time"] = "не дата"; x["trans_num"] = ["bad_1", "bad_2", "bad_3"]
    cases["битая дата в одной строке"] = x
    for name, inp in cases.items():
        try:
            o = score_frame(inp, art)
            ok = len(o) == len(inp) and o["fraud_probability"].between(0, 1).all() and o["decision"].isin([0, 1]).all()
            results.append(check(name, bool(ok), f"(строк {len(o)}, p от {o['fraud_probability'].min():.4f} "
                                                 f"до {o['fraud_probability'].max():.4f})"))
        except Exception as e:  # noqa: BLE001
            results.append(check(name, False, f"упало: {e!r}"))

    # 4. Нагрузка: 0,55 млн строк через командную строку.
    if not a.skip_load:
        need = 550_000 - len(ho)
        extra = raw[ts < boundaries(ts)["holdout_start"]].sample(n=need, random_state=3).drop(columns="is_fraud").copy()
        shift = pd.Timedelta(days=366)
        extra["trans_date_trans_time"] = (pd.to_datetime(extra["trans_date_trans_time"]) + shift).dt.strftime("%Y-%m-%d %H:%M:%S")
        extra["trans_num"] = "load_" + extra["trans_num"]
        big = pd.concat([ho.drop(columns="is_fraud"), extra], ignore_index=True).sample(frac=1.0, random_state=5)
        big.insert(0, "", np.arange(len(big)))
        path = TMP / "load_550k.csv"
        big.to_csv(path, index=False)
        t0 = time.time()
        r = subprocess.run([sys.executable, str(ROOT / "score.py"), "--input", str(path), "--output",
                            str(TMP / "load_550k_out.csv")], capture_output=True, text=True, encoding="utf-8")
        sec = time.time() - t0
        print(r.stdout.strip(), r.stderr.strip()[-500:] if r.returncode else "")
        out = pd.read_csv(TMP / "load_550k_out.csv") if r.returncode == 0 else pd.DataFrame()
        results.append(check("нагрузка 550 000 строк: ≤ 10 минут, все строки на выходе",
                             r.returncode == 0 and sec <= 600 and len(out) == len(big), f"({sec:.0f} c)"))
    print(f"\nИтого: {sum(results)} из {len(results)} проверок пройдено")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
