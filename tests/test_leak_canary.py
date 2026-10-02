"""Проверка самого теста: заведомо «подглядывающие» признаки он обязан поймать.

python -m tests.test_leak_canary
"""
import numpy as np
import pandas as pd

from src.data import load_train
from tests.test_no_future_leak import compare


def leaky(df):
    out = pd.DataFrame(index=df.index)
    # Сколько всего операций у карты за весь период — знает будущее.
    out["card_total_cnt"] = df.groupby("cc_num")["amt"].transform("size").astype("float64")
    # Пауза до СЛЕДУЮЩЕЙ операции карты — знает будущее.
    out["gap_to_next_h"] = (df.groupby("cc_num")["ts"].shift(-1) - df["ts"]).dt.total_seconds() / 3600
    # Честный признак для контроля: пауза с ПРЕДЫДУЩЕЙ операции.
    out["gap_from_prev_h"] = (df["ts"] - df.groupby("cc_num")["ts"].shift(1)).dt.total_seconds() / 3600
    return out


def main():
    df = load_train()
    cards = np.random.default_rng(7).choice(df.cc_num.unique(), size=100, replace=False)
    sub = df[df.cc_num.isin(cards)].reset_index(drop=True)
    T = sub.ts.quantile(0.5)
    full, cut = leaky(sub), leaky(sub[sub.ts <= T])
    for f in full.columns:
        ok, _ = compare(cut[f], full.loc[sub.ts <= T, f])
        print(f"{f}: {'прошёл' if ok else 'ПОЙМАН как утечка'}")
    assert not compare(cut["card_total_cnt"], full.loc[sub.ts <= T, "card_total_cnt"])[0]
    assert not compare(cut["gap_to_next_h"], full.loc[sub.ts <= T, "gap_to_next_h"])[0]
    assert compare(cut["gap_from_prev_h"], full.loc[sub.ts <= T, "gap_from_prev_h"])[0]
    print("Тест на утечку работает: подглядывающие признаки пойманы, честный — пропущен.")


if __name__ == "__main__":
    main()
