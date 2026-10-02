"""Тест на заглядывание в будущее (CLAUDE.md, раздел 11).

Для случайных дат T признаки, посчитанные на данных до T, должны совпасть с признаками,
посчитанными на всём файле, — для всех строк до T. Если значение изменилось, когда мы
«дописали будущее», значит признак это будущее видел.

python -m tests.test_no_future_leak --block a [--cards 150]
Результат дописывается в reports/leak_tests.csv.
"""
import argparse
import datetime as dt

import numpy as np
import pandas as pd

from src.data import ROOT, load_train
from src.features import get_block
from src.split import assign, boundaries


def compare(a: pd.Series, b: pd.Series):
    if isinstance(a.dtype, pd.CategoricalDtype) or a.dtype == object:
        a, b = a.astype("object"), b.astype("object")
        same = (a == b) | (a.isna() & b.isna())
        return bool(same.all()), float((~same).sum())
    a = a.to_numpy(dtype="float64")
    b = b.to_numpy(dtype="float64")
    same = np.isclose(a, b, rtol=1e-5, atol=1e-6, equal_nan=True)
    diff = np.nanmax(np.abs(a - b)) if (~same).any() else 0.0
    return bool(same.all()), float(diff)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", required=True)
    ap.add_argument("--cards", type=int, default=150)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    df = load_train()
    part = assign(df.ts, boundaries(df.ts))
    blk = get_block(a.block)
    state = blk.fit(df[part == "train"])

    # Подвыборка по картам целиком: история каждой карты не рвётся.
    rng = np.random.default_rng(a.seed)
    cards = rng.choice(df.cc_num.unique(), size=a.cards, replace=False)
    sub = df[df.cc_num.isin(cards)].reset_index(drop=True)
    full = blk.transform(sub, state)

    lo, hi = sub.ts.quantile(0.2), sub.ts.quantile(0.95)
    dates = sorted(pd.to_datetime(rng.uniform(lo.value, hi.value, size=3).astype("int64")))
    rows = []
    for T in dates:
        mask = sub.ts <= T
        cut = blk.transform(sub[mask].copy(), state)
        for f in blk.FEATURES:
            ok, diff = compare(cut[f], full.loc[mask, f])
            rows.append({"datetime": dt.datetime.now().isoformat(timespec="seconds"), "block": a.block,
                         "feature": f, "T": str(T), "rows_checked": int(mask.sum()), "pass": ok,
                         "max_diff": diff})
    res = pd.DataFrame(rows)
    out = ROOT / "reports" / "leak_tests.csv"
    res.to_csv(out, mode="a", header=not out.exists(), index=False, encoding="utf-8")
    summary = res.groupby("feature")["pass"].all()
    for f, ok in summary.items():
        print(f"{'OK   ' if ok else 'УТЕЧКА'} {f}")
    if not summary.all():
        raise SystemExit(f"Не прошли тест: {list(summary[~summary].index)}")


if __name__ == "__main__":
    main()
