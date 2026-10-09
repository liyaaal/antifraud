"""Неделя 2: что, если банк блокирует карту после подтверждённого мошенничества (сценарий «что если»).

python -m experiments.w2_block                       # v1 и v2 на holdout
python -m experiments.w2_block --scored-v1 ... --scored-v2 ... --tag test

Метрика недели 1 считает каждую операцию отдельно: пропущенная операция эпизода — убыток, даже если
карту уже заблокировали бы после первой подтверждённой. Разбор эпизодов показал: во время эпизода
честных операций на карте нет, эпизод длится ≈ 45 ч. Значит, в реальном банке одна подтверждённая
проверка останавливает весь остаток эпизода. Здесь это посчитано отдельно и НЕ подменяет метрику
недели 1 (она остаётся основной в сравнении v1/v2).

Правила симуляции:
  * аналитик не ошибается: проверенный фрод подтверждается, карта блокируется на BLOCK_H часов;
  * фрод-операции заблокированной карты не проходят — спасены без проверки; честные операции держателя
    идут уже по перевыпущенной карте (стоимость перевыпуска одинакова для всех политик и не считается);
  * каждый день лимит k_d = floor(0,3% · n_d) проверок, как в неделе 1.
Политики:
  ev_cap      — как в v1/v2: топ-k по деньгам за одну операцию;
  ev_episode  — проверка ценится как «эта операция + ожидаемый остаток эпизода»; одна проверка на карту в день.
"""
import argparse

import numpy as np
import pandas as pd

from experiments.w2_common import W2, load_labeled
from experiments.w2_patterns import build_episodes, md_table
from src.data import ROOT, load_train
from src.economics import FALSE_BLOCK, MISS_EXTRA, REVIEW, costs, decide, expected_value

BLOCK_H = 72.0


def remaining_by_spent(train_df: pd.DataFrame):
    """Средний остаток эпизода после операции как функция уже потраченного по карте за 48 ч (по train)."""
    f, ep = build_episodes(train_df)
    f = f.sort_values(["ep_id", "ts"])
    f["rest"] = f.groupby("ep_id").amt.transform(lambda a: a[::-1].cumsum()[::-1]) - f.amt
    f["spent"] = f.groupby("ep_id").amt.cumsum() - f.amt
    bins = [-1, 0, 500, 1000, 2000, 3000, 4000, 5000, 1e9]
    tab = f.groupby(pd.cut(f.spent, bins), observed=True).rest.mean()
    return bins, tab.to_numpy()


def spent_48h(df):
    """Сумма операций карты за 48 ч строго раньше (без меток)."""
    order = np.lexsort((df.trans_num.to_numpy(), df.ts.to_numpy(), df.cc_num.to_numpy()))
    card = pd.factorize(df.cc_num.to_numpy()[order])[0].astype("float64")
    t = df.ts.to_numpy()[order].astype("datetime64[s]").astype("int64") / 3600.0
    key = card * 1e7 + (t - t.min())
    vis = np.searchsorted(key, key, side="left")
    lo = np.searchsorted(key, key - 48.0, side="left")
    cs = np.concatenate([[0.0], np.cumsum(df.amt.to_numpy(dtype="float64")[order])])
    out = np.empty(len(df))
    out[order] = cs[vis] - cs[lo]
    return out


def simulate(df: pd.DataFrame, p: np.ndarray, policy: str, rest_bins=None, rest_tab=None) -> dict:
    df = df.reset_index(drop=True)
    y = df.is_fraud.to_numpy().astype(bool)
    amt = df.amt.to_numpy(dtype="float64")
    t = df.ts.to_numpy().astype("datetime64[s]").astype("int64") / 3600.0
    card = df.cc_num.to_numpy()
    day = df.ts.dt.normalize().to_numpy()
    if policy == "ev_cap":
        score = expected_value(p, amt)
    else:
        spent = spent_48h(df)
        idx = np.clip(np.searchsorted(rest_bins, spent, side="left") - 1, 0, len(rest_tab) - 1)
        rest = rest_tab[idx]
        score = p * (amt + MISS_EXTRA + rest) - REVIEW - (1 - p) * FALSE_BLOCK
    block = {}                              # карта -> время начала блокировки
    prevented = np.zeros(len(df), bool)
    reviewed = np.zeros(len(df), bool)
    wasted = 0
    days, starts = np.unique(day, return_index=True)
    ends = list(starts[1:]) + [len(df)]
    for s, e in zip(starts, ends):
        rows = np.arange(s, e)
        k = int(np.floor(0.003 * len(rows)))
        # Операции карт, заблокированных до этого дня, в поток не попадают.
        bs = np.array([block.get(c, np.nan) for c in card[rows]])
        pre = (~np.isnan(bs)) & (t[rows] > bs) & (t[rows] <= bs + BLOCK_H)
        prevented[rows[pre]] = True
        cand = rows[(~pre) & (score[rows] > 0)]
        cand = cand[np.argsort(-score[cand], kind="mergesort")]
        picks, seen = [], set()
        for i in cand:
            if len(picks) >= k:
                break
            if policy == "ev_episode":
                if card[i] in seen:
                    continue
                seen.add(card[i])
            picks.append(i)
        for i in sorted(picks, key=lambda j: t[j]):
            b = block.get(card[i])
            if b is not None and b < t[i] <= b + BLOCK_H:
                wasted += 1            # карта уже заблокирована раньше в этот же день — проверка не нужна
                continue
            reviewed[i] = True
            if y[i]:
                block[card[i]] = t[i]
        # Внутри дня: операции после блокировки тоже не проходят.
        bs = np.array([block.get(c, np.nan) for c in card[rows]])
        pre = (~np.isnan(bs)) & (t[rows] > bs) & (t[rows] <= bs + BLOCK_H) & ~reviewed[rows]
        prevented[rows[pre]] = True
    miss = y & ~reviewed & ~prevented
    loss = (REVIEW * reviewed.sum() + FALSE_BLOCK * (reviewed & ~y).sum()
            + (amt[miss] + MISS_EXTRA).sum())
    loss_none = (amt[y] + MISS_EXTRA).sum()
    return {"политика": policy, "экономия с блокировкой карты": loss_none - loss,
            "доля спасённых денег фрода": 1 - amt[miss].sum() / amt[y].sum(),
            "проверок": int(reviewed.sum()), "фрод-операций остановлено блокировкой": int((prevented & y).sum()),
            "ложных проверок": int((reviewed & ~y).sum()),
            "впустую потраченных мест": wasted, "убыток без системы": loss_none}


def run(df, p, tag, bins, tab):
    rows = []
    for pol in ["ev_cap", "ev_episode"]:
        r = simulate(df, p, pol, bins, tab)
        d = decide("ev_cap", df.ts.dt.normalize(), p, df.amt.to_numpy(dtype="float64")) if pol == "ev_cap" else None
        r["экономия по метрике недели 1"] = costs(df.is_fraud, df.amt, d, df.ts.dt.normalize())["savings"] if d is not None else np.nan
        r["набор"] = tag
        rows.append(r)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scored-v1", default=None)
    ap.add_argument("--scored-v2", default=None)
    ap.add_argument("--tag", default="holdout")
    a = ap.parse_args()
    tr = load_train()
    bins, tab = remaining_by_spent(tr[tr.ts < "2020-02-21"])
    rows = []
    if a.scored_v1:
        df = load_labeled()
        for name, path in [("v1", a.scored_v1), ("v2", a.scored_v2)]:
            s = pd.read_csv(ROOT / path).set_index("trans_num").loc[df.trans_num]
            rows += run(df, s.fraud_probability.to_numpy(), f"{name} {a.tag}", bins, tab)
    else:
        for name, pred in [("v1", "final"), ("v2", "final_v2")]:
            f = ROOT / "reports" / "preds" / f"{pred}_holdout.parquet"
            if not f.exists():
                continue
            df = tr.merge(pd.read_parquet(f), on="trans_num")
            rows += run(df, df.p.to_numpy(), f"{name} holdout", bins, tab)
    res = pd.DataFrame(rows)
    res.to_csv(W2 / f"block_whatif_{a.tag}.csv", index=False, encoding="utf-8")
    txt = [f"# Что если банк блокирует карту после подтверждения — {a.tag}", "",
           "Средний остаток эпизода по уже потраченному за 48 ч (train): "
           + ", ".join(f"{int(b)}+ → {v:,.0f}".replace(",", " ") for b, v in zip(bins[:-1], tab)), "",
           md_table(res[["набор", "политика", "экономия по метрике недели 1", "экономия с блокировкой карты",
                         "доля спасённых денег фрода", "проверок", "ложных проверок",
                         "фрод-операций остановлено блокировкой",
                         "впустую потраченных мест", "убыток без системы"]],
                    {"доля спасённых денег фрода": lambda v: f"{v:.1%}",
                     "экономия по метрике недели 1": lambda v: "—" if v != v else f"{v:,.0f}".replace(",", " ")})]
    (W2 / f"block_whatif_{a.tag}.md").write_text("\n".join(txt), encoding="utf-8")
    print("\n".join(txt))


if __name__ == "__main__":
    main()
