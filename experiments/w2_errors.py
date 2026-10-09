"""Неделя 2, шаг 2: ошибки модели относительно паттернов (valid + holdout, 21.02–21.06.2020).

python -m experiments.w2_errors

Нужны предсказания reports/preds/final_{valid,holdout}.parquet (v1) и, для контроля регрессий,
reports/preds/final_v2_{valid,holdout}.parquet (v2). fraudTest не используется — он для приёмки.
Пишет reports/week2/tables/: errors_tables.md, missed_review.md, fp_review.md, segments.csv, regression.md.
"""
import numpy as np
import pandas as pd

from experiments.w2_common import W2
from experiments.w2_patterns import build_episodes, md_table, pct
from src.data import ROOT, load_train
from src.economics import daily_cap, expected_value

PREDS = ROOT / "reports" / "preds"
CAT_RU = {"shopping_net": "покупки онлайн", "shopping_pos": "покупки в магазине", "misc_net": "разное онлайн",
          "misc_pos": "разное в магазине", "grocery_net": "продукты онлайн", "grocery_pos": "продукты в магазине",
          "gas_transport": "АЗС/транспорт", "travel": "путешествия", "entertainment": "развлечения",
          "food_dining": "кафе/рестораны", "personal_care": "уход за собой", "health_fitness": "здоровье/спорт",
          "kids_pets": "дети/животные", "home": "товары для дома"}


def load_preds(name: str) -> pd.DataFrame | None:
    files = [PREDS / f"{name}_valid.parquet", PREDS / f"{name}_holdout.parquet"]
    if not all(f.exists() for f in files):
        return None
    return pd.concat([pd.read_parquet(f).assign(part=f.stem.split("_")[-1]) for f in files])


def prepare(df, ep_ops, ep, preds):
    d = df.merge(preds, on="trans_num")
    d["day"] = d.ts.dt.normalize()
    d["hour"] = d.ts.dt.hour
    d["ev"] = expected_value(d.p, d.amt)
    d["rk"] = d.groupby("day").ev.rank(ascending=False, method="first")
    d["cap"] = daily_cap(d.day).values
    d = d.merge(ep_ops[["trans_num", "ep_id", "pos"]], on="trans_num", how="left")
    # Фаза эпизода (для фрода).
    small = d.amt < 100
    d["phase"] = np.where(d.is_fraud == 0, "честная",
                          np.where(small, "P1·м мелкие", np.where(d.hour <= 11, "P1·н ночная волна (00–11)",
                                                                  "P1·в вечерняя волна (12–23)")))
    # Длина истории клиента в потоке (дней с первой операции карты в логе).
    first = df.groupby("cc_num").ts.min()
    d["hist_days"] = (d.ts - d.cc_num.map(first)).dt.total_seconds() / 86400
    d["hist_seg"] = pd.cut(d.hist_days, [-1, 14, 90, 365, 10_000], labels=["< 2 нед", "2 нед–3 мес", "3–12 мес", "> 1 года"])
    d["amt_seg"] = pd.cut(d.amt, [0, 20, 100, 300, 600, 1000, 1e9],
                          labels=["< 20", "20–100", "100–300", "300–600", "600–1000", "> 1000"])
    d["hour_seg"] = pd.cut(d.hour, [-1, 3, 11, 21, 23], labels=["00–03", "04–11", "12–21", "22–23"])
    fr_day = d.groupby("day").is_fraud.transform("sum")
    d["load_seg"] = np.where(fr_day > 2 * d.cap, "фрода > 2× лимита", np.where(fr_day > d.cap, "фрода > лимита",
                                                                            "фрода ≤ лимита"))
    d["why"] = np.select([d.decision == 1, d.p < 0.5, d.ev <= 0, d.rk > d.cap],
                         ["отправлено", "модель не узнала (p < 0,5)", "EV ≤ 0 (дешевле не проверять)",
                          "узнала, но не влезло в лимит"], "прочее")
    return d


def seg_table(d, col):
    g = d.groupby(col, observed=True)
    fr = d[d.is_fraud == 1].groupby(col, observed=True)
    t = pd.DataFrame({
        "операций": g.size(), "фрод-операций": fr.size(), "деньги фрода": fr.amt.sum(),
        "чувствительность (шт)": fr.decision.mean(),
        "чувствительность (деньги)": fr.apply(lambda x: (x.amt * x.decision).sum() / x.amt.sum()),
        "ложных тревог": d[(d.is_fraud == 0) & (d.decision == 1)].groupby(col, observed=True).size(),
        "упущено денег": fr.apply(lambda x: (x.amt * (1 - x.decision)).sum()),
    }).fillna(0)
    return t


def history_lines(df, cc, t, k=5):
    h = df[(df.cc_num == cc) & (df.ts < t)].tail(k)
    if h.empty:
        return "истории нет — карта впервые появилась в логе с этого эпизода"
    return "; ".join(f"{r.ts:%d.%m %H:%M} {CAT_RU.get(r.category, r.category)} {r.amt:.0f}"
                     + (" [фрод]" if r.is_fraud else "") for r in h.itertuples())


def similar_rate(df_train, r):
    """Доля фрода среди похожих операций train: та же категория, сумма ±15%, то же время суток (день/ночь)."""
    night = lambda h: (h >= 22) | (h <= 3)
    h = df_train.ts.dt.hour
    m = ((df_train.category == r.category) & (df_train.amt.between(r.amt * 0.85, r.amt * 1.15))
         & (night(h) == night(r.hour)))
    return float(df_train.is_fraud[m].mean()), int(m.sum())


def comment(r, d_ep, df_train=None):
    if r.why == "узнала, но не влезло в лимит":
        day = r.day
        return (f"модель уверена (p = {r.p:.2f}), но в этот день {int(r.fr_day)} фрод-операций при лимите {int(r.cap)}; "
                f"место {int(r.rk)} по EV. В эпизоде отправлено {int(d_ep.decision.sum())} из {len(d_ep)} операций")
    if r.why.startswith("модель не узнала"):
        rate, n = similar_rate(df_train, r)
        return (f"p = {r.p:.2f}: среди похожих операций до valid ({CAT_RU.get(r.category)}, сумма ±15%, "
                f"{'ночь' if (r.hour >= 22 or r.hour <= 3) else 'день'}) фрода {rate:.0%} из {n}"
                + ("; это первая операция эпизода — по карте ещё ничего необычного" if r.pos == 1 else ""))
    if r.why.startswith("EV"):
        return f"мелкая сумма {r.amt:.0f}: проверка (3) и риск задержать честного дороже ожидаемой выгоды"
    return ""


def main():
    W2.mkdir(parents=True, exist_ok=True)
    df = load_train()
    ep_ops, ep = build_episodes(df)
    v1 = prepare(df, ep_ops, ep, load_preds("final"))
    v1["fr_day"] = v1.groupby("day").is_fraud.transform("sum")
    out = ["# Ошибки v1 относительно паттернов — таблицы", "",
           "Скрипт: `python -m experiments.w2_errors`. Период: valid + holdout (21.02–21.06.2020, 122 дня). "
           "Модель v1 (`artifacts/final`).", ""]

    # 1. Почему фрод не отправлен — по фазам.
    fr = v1[v1.is_fraud == 1]
    why = fr.pivot_table(index="phase", columns="why", values="amt", aggfunc="sum", fill_value=0)
    why_n = fr.pivot_table(index="phase", columns="why", values="amt", aggfunc="size", fill_value=0)
    out += ["## 1. Куда уходят деньги фрода: по фазам эпизода (у.е.)", "", md_table(why.reset_index()), "",
            "То же в операциях:", "", md_table(why_n.reset_index(), {c: str for c in why_n.columns}), ""]

    # 2. Эпизоды: когда эпизод впервые попадает к аналитику.
    e = fr.groupby("ep_id").agg(n=("amt", "size"), amt=("amt", "sum"), sent=("decision", "sum"),
                                first_sent=("pos", lambda s: s[fr.loc[s.index, "decision"] == 1].min()))
    full = e.n == ep.loc[e.index, "n"]
    e = e[full]
    lost_before = fr[fr.ep_id.isin(e.index)].merge(e[["first_sent"]], left_on="ep_id", right_index=True)
    lost_before = lost_before[(lost_before.pos < lost_before.first_sent) | lost_before.first_sent.isna()].amt.sum()
    out += ["## 2. Эпизоды целиком", "",
            f"Эпизодов, целиком попавших в период: {len(e)}. Хотя бы одна операция отправлена аналитику в "
            f"{(e.sent > 0).mean():.1%} эпизодов. Номер первой отправленной операции: медиана "
            f"{e.first_sent.median():.0f}, распределение: "
            + ", ".join(f"{int(k)}: {v}" for k, v in e.first_sent.value_counts().sort_index().items()) + ".", "",
            f"Деньги этих эпизодов: {e.amt.sum():,.0f}; не отправлено по операциям: "
            f"{fr[fr.ep_id.isin(e.index)].pipe(lambda x: (x.amt * (1 - x.decision)).sum()):,.0f}; "
            f"из них ушло ДО первой отправленной операции эпизода: {lost_before:,.0f}.".replace(",", " "), ""]

    # 3. Сегменты.
    segs = []
    for col, name in [("category", "категория"), ("amt_seg", "сумма"), ("hour_seg", "время"),
                      ("hist_seg", "история клиента"), ("load_seg", "нагрузка дня"), ("part", "период")]:
        t = seg_table(v1, col).reset_index(names="значение")
        t.insert(0, "разрез", name)
        segs.append(t)
        out += [f"## 3. Разрез: {name}", "", md_table(t.drop(columns="разрез"),
                                                       {"чувствительность (шт)": pct, "чувствительность (деньги)": pct}), ""]
    pd.concat(segs).to_csv(W2 / "segments_v1.csv", index=False, encoding="utf-8")

    # 4. Самые дорогие ошибки.
    top = fr[fr.decision == 0].sort_values("amt", ascending=False).head(10)
    out += ["## 4. Десять самых дорогих пропусков", "",
            md_table(top.assign(когда=top.ts.dt.strftime("%d.%m %H:%M"), категория=top.category.map(CAT_RU))
                     [["когда", "категория", "amt", "p", "rk", "cap", "fr_day", "why"]]
                     .rename(columns={"amt": "сумма", "rk": "место по EV", "cap": "лимит дня", "fr_day": "фрода в день",
                                      "why": "причина"}),
                     {"p": lambda v: f"{v:.2f}", "сумма": lambda v: f"{v:.0f}"}), ""]
    (W2 / "errors_tables.md").write_text("\n".join(out), encoding="utf-8")

    # 5. Построчный просмотр пропусков: 24 операции из всех групп причин и фаз.
    miss = fr[fr.decision == 0].copy()
    pick = pd.concat([
        miss[miss.why == "узнала, но не влезло в лимит"].sort_values("amt", ascending=False).head(8),
        miss[miss.why == "узнала, но не влезло в лимит"].query("phase == 'P1·н ночная волна (00–11)'").sample(4, random_state=1),
        miss[miss.why == "модель не узнала (p < 0,5)"].query("amt >= 100").sort_values("amt", ascending=False).head(8),
        miss[miss.why.str.startswith("EV")].sample(4, random_state=1),
    ]).drop_duplicates("trans_num")
    rows = []
    for r in pick.itertuples():
        d_ep = fr[fr.ep_id == r.ep_id]
        rows.append({"когда": f"{r.ts:%d.%m.%Y %H:%M}", "операция": f"{CAT_RU.get(r.category)} {r.amt:.2f}",
                     "фаза / № в эпизоде": f"{r.phase} / {int(r.pos)} из {len(d_ep)}", "p": f"{r.p:.3f}",
                     "причина": r.why, "что видно в строке": comment(r, d_ep, df[df.ts < "2020-02-21"]),
                     "история держателя до эпизода (5 последних)": history_lines(df, r.cc_num, ep.loc[r.ep_id, "start"])})
    mr = pd.DataFrame(rows)
    mr.to_csv(W2 / "missed_review.csv", index=False, encoding="utf-8")
    (W2 / "missed_review.md").write_text("# Построчный просмотр пропущенного фрода (v1, valid + holdout)\n\n"
                                         + md_table(mr), encoding="utf-8")

    # 6. Построчный просмотр ложных срабатываний — все.
    fp = v1[(v1.is_fraud == 0) & (v1.decision == 1)].copy()
    ep_t = ep.set_index("cc_num")[["start", "end"]]
    fp = fp.join(ep_t, on="cc_num")
    fp["near_h"] = np.where(fp.ts < fp.start, (fp.start - fp.ts).dt.total_seconds() / 3600,
                                               (fp.ts - fp.end).dt.total_seconds() / 3600)
    typ = df[df.is_fraud == 0].groupby(["cc_num", "category"]).amt.median()
    rows = []
    for r in fp.itertuples():
        t_amt = typ.get((r.cc_num, r.category), np.nan)
        near = r.near_h
        hist = df[(df.cc_num == r.cc_num) & (df.ts < r.ts)]
        last24 = hist[hist.ts >= r.ts - pd.Timedelta(hours=48)]
        kind = ("рядом с эпизодом своей карты" if near == near and abs(near) < 48 else
                "одиночная крупная покупка на фоне обычной жизни" if len(last24[last24.amt >= 200]) == 0 else
                "несколько крупных покупок подряд у честного клиента")
        rows.append({"когда": f"{r.ts:%d.%m %H:%M}", "операция": f"{CAT_RU.get(r.category)} {r.amt:.0f}", "p": f"{r.p:.2f}",
                     "обычная сумма клиента в категории": f"{t_amt:.0f}" if t_amt == t_amt else "нет покупок",
                     "операций за 48 ч до": len(last24), "крупных за 48 ч до": int((last24.amt >= 200).sum()),
                     "ч до/после эпизода своей карты": f"{near:.0f}" if near == near else "нет эпизода",
                     "тип": kind})
    fr_ = pd.DataFrame(rows)
    fr_.to_csv(W2 / "fp_review.csv", index=False, encoding="utf-8")
    kinds = fr_["тип"].value_counts()
    (W2 / "fp_review.md").write_text("# Построчный просмотр ложных срабатываний (v1, valid + holdout)\n\n"
                                     + "Типы: " + "; ".join(f"{k} — {v}" for k, v in kinds.items()) + "\n\n"
                                     + md_table(fr_), encoding="utf-8")

    # 7. Контроль регрессий v1 → v2 по сегментам.
    p2 = load_preds("final_v2")
    if p2 is not None:
        v2 = prepare(df, ep_ops, ep, p2)
        lines = ["# Контроль регрессий v1 → v2 (valid + holdout)", "",
                 "Сегмент деградировал, если упущенные деньги выросли или ложных тревог стало больше.", ""]
        allt = []
        for col, name in [("phase", "фаза"), ("category", "категория"), ("amt_seg", "сумма"), ("hour_seg", "время"),
                          ("hist_seg", "история клиента"), ("load_seg", "нагрузка дня"), ("part", "период")]:
            a, b = seg_table(v1, col), seg_table(v2, col)
            t = pd.DataFrame({"разрез": name, "значение": a.index.astype(str),
                              "упущено v1": a["упущено денег"].values, "упущено v2": b["упущено денег"].reindex(a.index).values,
                              "ложных v1": a["ложных тревог"].values, "ложных v2": b["ложных тревог"].reindex(a.index).values})
            t["Δ упущено"] = t["упущено v2"] - t["упущено v1"]
            t["Δ ложных"] = t["ложных v2"] - t["ложных v1"]
            t["итог"] = np.where((t["Δ упущено"] > 50) | (t["Δ ложных"] > 0), "хуже",
                                 np.where((t["Δ упущено"] < -50) | (t["Δ ложных"] < 0), "лучше", "без изменений"))
            allt.append(t)
            lines += [f"## {name}", "", md_table(t.drop(columns="разрез"),
                                                  {"ложных v1": lambda v: f"{v:.0f}", "ложных v2": lambda v: f"{v:.0f}",
                                                   "Δ ложных": lambda v: f"{v:+.0f}", "Δ упущено": lambda v: f"{v:+,.0f}".replace(",", " ")}), ""]
        pd.concat(allt).to_csv(W2 / "regression.csv", index=False, encoding="utf-8")
        (W2 / "regression.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(out[:40]))


if __name__ == "__main__":
    main()
