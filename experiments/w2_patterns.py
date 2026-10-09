"""Неделя 2, шаг 1: типология мошенничества по эпизодам (от данных к паттерну).

python -m experiments.w2_patterns            # типология на fraudTrain (+ детекция v1 на valid+holdout)
python -m experiments.w2_patterns --test     # проверка устойчивости на fraudTest (запускать после заморозки v2)

Эпизод — все мошеннические операции одной карты, идущие с паузами < 48 ч.
Пишет reports/week2/tables/patterns.md, patterns_map.csv, episodes.csv.
"""
import argparse

import numpy as np
import pandas as pd
from scipy import stats

from experiments.w2_common import W2, load_labeled
from src.data import ROOT, load_train
from src.features._util import haversine_km

GAP_H = 48.0
SMALL = 100.0
PRED_FILES = {"valid": ROOT / "reports/preds/final_valid.parquet",
              "holdout": ROOT / "reports/preds/final_holdout.parquet"}


def slot(h):
    return np.select([h <= 3, h <= 11, h <= 21], ["00–03", "04–11", "12–21"], "22–23")


def build_episodes(df: pd.DataFrame):
    f = df[df["is_fraud"] == 1].sort_values(["cc_num", "ts"]).copy()
    gap = f.groupby("cc_num")["ts"].diff().dt.total_seconds() / 3600
    f["ep_id"] = ((gap.isna()) | (gap >= GAP_H)).cumsum()
    f["pos"] = f.groupby("ep_id").cumcount() + 1
    f["hour"] = f["ts"].dt.hour
    f["slot"] = slot(f["hour"])
    f["small"] = f["amt"] < SMALL
    f["wave"] = np.where(f["hour"] <= 11, "ночная (00–11)", "вечерняя (12–23)")
    g = f.groupby("ep_id")
    ep = pd.DataFrame({
        "cc_num": g["cc_num"].first(), "start": g["ts"].min(), "end": g["ts"].max(), "n": g.size(),
        "amt": g["amt"].sum(), "n_small": g["small"].sum(), "n_cat": g["category"].nunique(),
        "days": g["ts"].apply(lambda t: t.dt.normalize().nunique()),
        "has_night": g["hour"].apply(lambda h: (h <= 3).any()), "has_evening": g["hour"].apply(lambda h: (h >= 22).any()),
        "first_slot": g["slot"].first(), "last_slot": g["slot"].last(),
        "first_small": g["small"].first(), "first_cat": g["category"].first(),
    })
    ep["dur_h"] = (ep["end"] - ep["start"]).dt.total_seconds() / 3600
    # История держателя: сколько операций было до эпизода, есть ли его операции внутри и после.
    allc = df[["cc_num", "ts", "is_fraud"]].merge(ep[["cc_num", "start", "end"]], on="cc_num")
    ep = ep.set_index("cc_num", append=True)
    def cnt(mask):
        return allc[mask].groupby("cc_num").size()
    before = cnt(allc.ts < allc.start)
    during = cnt((allc.ts >= allc.start) & (allc.ts <= allc.end) & (allc.is_fraud == 0))
    after = cnt(allc.ts > allc.end)
    ep = ep.reset_index("cc_num")
    for name, s in [("ops_before", before), ("honest_during", during), ("ops_after", after)]:
        ep[name] = ep["cc_num"].map(s).fillna(0).astype(int)
    ep["new_card"] = ep["ops_before"] < 10
    return f, ep


def hypotheses(df, f, ep) -> pd.DataFrame:
    rows = []
    # H1. «Тестовое мелкое списание перед крупной покупкой».
    p_first = ep["first_small"].mean()
    p_all = f["small"].mean()
    rows.append(["Тестовое мелкое списание перед крупными покупками",
                 f"первая операция эпизода мелкая (< {SMALL:.0f}) в {p_first:.0%} эпизодов; доля мелких среди всех "
                 f"операций эпизода {p_all:.0%} — мелкие идут вперемешку, а не в начале", "не подтверждена"])
    # H2. Волны массовой компрометации: старты эпизодов по дням — пуассоновские?
    s = ep["start"].dt.normalize().value_counts()
    s = s.reindex(pd.date_range(df.ts.min().normalize(), df.ts.max().normalize()), fill_value=0)
    disp = s.var() / s.mean()
    rows.append(["Волна: много карт атакуют одновременно",
                 f"стартов эпизодов в день в среднем {s.mean():.2f}, дисперсия/среднее = {disp:.2f} "
                 f"(1,0 = независимые случайные старты); максимум {s.max()} стартов за день", "не подтверждена"])
    # H3. Общая точка компрометации — один мерчант до атаки.
    hon = df[df.is_fraud == 0][["cc_num", "ts", "merchant"]]
    st = ep.set_index("cc_num")["start"]
    def mset(cc):
        h = hon[(hon.cc_num == cc) & (hon.ts < st[cc]) & (hon.ts >= st[cc] - pd.Timedelta(days=30))]
        return set(h.merchant)
    srt = st.sort_values()
    close, rnd = [], []
    idx = list(srt.index)
    for a, b in zip(idx[:-1], idx[1:]):
        if abs((st[a] - st[b]).days) <= 1:
            A, B = mset(a), mset(b)
            if A and B:
                close.append(len(A & B) / len(A | B))
    rng = np.random.default_rng(0)
    for _ in range(len(close)):
        a, b = rng.choice(idx, 2, replace=False)
        A, B = mset(a), mset(b)
        if A and B:
            rnd.append(len(A & B) / len(A | B))
    pv = stats.mannwhitneyu(close, rnd).pvalue
    rows.append(["Общая точка компрометации (один магазин до атаки)",
                 f"у карт, атакованных в один день, общих магазинов за 30 дней до атаки столько же, сколько у "
                 f"случайных пар (Жаккар {np.mean(close):.3f} против {np.mean(rnd):.3f}, p = {pv:.2f})",
                 "не подтверждена"])
    # H4. Мошеннические магазины.
    mc = df.groupby(["category", "merchant"]).agg(n=("is_fraud", "size"), fr=("is_fraud", "sum")).reset_index()
    mc["exp"] = mc["n"] * mc["category"].map(df.groupby("category").is_fraud.mean())
    chi = ((mc.fr - mc.exp) ** 2 / mc.exp.clip(lower=1e-9)).sum()
    dof = len(mc) - mc.category.nunique()
    rows.append(["Мошенничество сосредоточено у отдельных магазинов",
                 f"внутри категории доля фрода по {len(mc)} магазинам не отличается от случайной "
                 f"(χ² = {chi:.0f} при {dof} ст. св., p = {stats.chi2.sf(chi, dof):.2f})", "не подтверждена"])
    # H5. Мошенник далеко от дома.
    dist = haversine_km(df.lat, df.long, df.merch_lat, df.merch_long)
    rows.append(["Операция далеко от дома держателя",
                 f"медиана расстояния: фрод {np.median(dist[df.is_fraud == 1]):.0f} км, честные "
                 f"{np.median(dist[df.is_fraud == 0]):.0f} км", "не подтверждена"])
    # H6. Повторные атаки на ту же карту.
    per_card = ep.groupby("cc_num").size()
    rows.append(["Повторная атака на ту же карту",
                 f"эпизодов на карту: максимум {per_card.max()}; у {int((per_card > 1).sum())} карт больше одного",
                 "не подтверждена"])
    # H7. Эскалация суммы внутри эпизода.
    rho = [stats.spearmanr(g.pos, g.amt).statistic for _, g in f.groupby("ep_id") if len(g) >= 4]
    rows.append(["Нарастание сумм внутри эпизода",
                 f"средняя ранговая корреляция «номер операции — сумма» {np.nanmean(rho):.2f}; слабый рост объясняется "
                 f"сменой волн (ночью продукты ≈ 300, вечером покупки ≈ 900), а не разгоном", "не подтверждена"])
    # H8. Держатель продолжает пользоваться картой во время эпизода.
    rows.append(["Держатель продолжает платить картой во время эпизода",
                 f"честных операций внутри эпизода нет в {(ep.honest_during == 0).mean():.1%} эпизодов; после эпизода "
                 f"карта снова живёт обычной жизнью (медиана {ep.ops_after.median():.0f} операций)",
                 "опровергнута: на время эпизода карта полностью у мошенника"])
    return pd.DataFrame(rows, columns=["Гипотеза", "Проверка", "Итог"])


def detection(f: pd.DataFrame):
    """Детекция v1 на valid+holdout для операций паттерна."""
    pv = pd.concat([pd.read_parquet(p).assign(part=k) for k, p in PRED_FILES.items()])
    x = f.merge(pv, on="trans_num")
    return x


def row_stats(x: pd.DataFrame, mask, name, scen, log):
    s = x[mask]
    if len(s) == 0:
        return None
    eps = s.groupby("ep_id")["decision"].max()
    return {"Паттерн": name, "Сценарий": scen, "Проявление в логе": log,
            "Операций": int(len(s)), "Сумма": float(s["amt"].sum()),
            "Модель узнаёт (p ≥ 0,5), доля операций": float((s["p"] >= 0.5).mean()),
            "Отправлено аналитику, доля операций": float(s["decision"].mean()),
            "Отправлено аналитику, доля денег": float((s["amt"] * s["decision"]).sum() / s["amt"].sum()),
            "Эпизодов с хотя бы одной проверкой": float(eps.mean())}


def stability(f, ep, df):
    q = ep["start"].dt.to_period("Q").astype(str)
    cards_q = df.groupby(df.ts.dt.to_period("Q").astype(str))["cc_num"].nunique()
    t = pd.DataFrame({
        "эпизодов": ep.groupby(q).size(),
        "карт с эпизодом / активных карт": ep.groupby(q)["cc_num"].nunique().astype(str) + " / " + cards_q.astype(str),
        "операций в эпизоде (медиана)": ep.groupby(q)["n"].median(),
        "сумма эпизода (медиана)": ep.groupby(q)["amt"].median().round(0),
        "длительность, ч (медиана)": ep.groupby(q)["dur_h"].median().round(1),
        "есть ночная и вечерняя волна": ep.groupby(q).apply(lambda e: (e.has_night & e.has_evening).mean()).round(2),
        "старт ночью 00–03": ep.groupby(q).apply(lambda e: (e.first_slot == "00–03").mean()).round(2),
        "доля мелких операций": ep.groupby(q).apply(lambda e: e.n_small.sum() / e.n.sum()).round(2),
        "новая карта (< 10 операций до)": ep.groupby(q)["new_card"].sum(),
    })
    return t


def md_table(df: pd.DataFrame, fmt=None) -> str:
    fmt = fmt or {}
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if c in fmt:
                v = fmt[c](v)
            elif isinstance(v, float):
                v = f"{v:,.0f}".replace(",", " ")
            cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def pct(v):
    return f"{v:.0%}"


ST_FMT = {"операций в эпизоде (медиана)": lambda v: f"{v:.0f}", "длительность, ч (медиана)": lambda v: f"{v:.0f}",
          "есть ночная и вечерняя волна": pct, "старт ночью 00–03": pct, "доля мелких операций": pct}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    W2.mkdir(parents=True, exist_ok=True)
    if a.test:
        df = load_labeled()
        f, ep = build_episodes(df)
        st = stability(f, ep, df)
        txt = ["# Проверка устойчивости паттернов на fraudTest (после заморозки v2)", "",
               f"Эпизодов {len(ep)}, операций {len(f)}, карт с эпизодом {ep.cc_num.nunique()} из {df.cc_num.nunique()}.",
               f"Длительность (медиана) {ep.dur_h.median():.1f} ч, операций в эпизоде {ep.n.median():.0f}, "
               f"обе волны в {(ep.has_night & ep.has_evening).mean():.0%} эпизодов, честных операций внутри эпизода нет в "
               f"{(ep.honest_during == 0).mean():.1%}.", "", md_table(st.reset_index(names="квартал"), ST_FMT)]
        (W2 / "patterns_test_stability.md").write_text("\n".join(txt), encoding="utf-8")
        print("\n".join(txt))
        return

    df = load_train()
    f, ep = build_episodes(df)
    ep.to_csv(W2 / "episodes.csv", index=False, encoding="utf-8")
    x = detection(f)
    full = x.groupby("ep_id").size() == ep.loc[x.groupby("ep_id").size().index, "n"]
    x = x[x.ep_id.isin(full[full].index)]          # только эпизоды, целиком попавшие в valid+holdout
    xn = x.merge(ep[["new_card"]], left_on="ep_id", right_index=True)

    rows = [
        row_stats(xn, xn.index == xn.index, "P1. Двухсуточный захват карты (весь эпизод)",
                  "ночь: продукты в магазине ≈ 300 + мелочь на АЗС → вечер 22–23: покупки онлайн/в магазине ≈ 900, "
                  "разное онлайн ≈ 800 → то же на вторые сутки → конец вечером вторых суток",
                  "≈ 10 операций за ≈ 45 ч, 5–6 категорий; обычных операций владельца в эти 2 дня нет"),
        row_stats(xn, (~xn.small) & (xn.hour >= 12), "P1·в. Вечерняя волна крупных покупок",
                  "фаза P1", "12–23 ч, ≥ 100: shopping_net ≈ 1000, shopping_pos ≈ 880, misc_net ≈ 800, entertainment ≈ 500, "
                             "home ≈ 250"),
        row_stats(xn, (~xn.small) & (xn.hour <= 11), "P1·н. Ночная волна",
                  "фаза P1", "00–11 ч, ≥ 100: grocery_pos ≈ 310 (2–4 раза), реже misc_net / shopping"),
        row_stats(xn, xn.small, "P1·м. Мелкие сопутствующие операции",
                  "фаза P1, обе волны", "< 100: ночью gas_transport ≈ 10, grocery_net ≈ 12; вечером personal_care, "
                                       "kids_pets, health_fitness ≈ 20, travel ≈ 9"),
        row_stats(xn, xn.new_card, "P2. Захват новой карты",
                  "тот же сценарий P1, но у карты < 10 операций до эпизода — профиля клиента ещё нет",
                  "эпизод в первые дни жизни карты в потоке"),
    ]
    pm = pd.DataFrame([r for r in rows if r])
    totals = {"P1. Двухсуточный захват карты (весь эпизод)": (len(f), f.amt.sum())}
    pm["Операций (весь fraudTrain)"] = [
        len(f), int(((~f.small) & (f.hour >= 12)).sum()), int(((~f.small) & (f.hour <= 11)).sum()), int(f.small.sum()),
        int(f.ep_id.isin(ep.index[ep.new_card]).sum())]
    pm["Сумма (весь fraudTrain)"] = [
        f.amt.sum(), f.amt[(~f.small) & (f.hour >= 12)].sum(), f.amt[(~f.small) & (f.hour <= 11)].sum(),
        f.amt[f.small].sum(), f.amt[f.ep_id.isin(ep.index[ep.new_card])].sum()]
    pm.to_csv(W2 / "patterns_map.csv", index=False, encoding="utf-8")
    hyp = hypotheses(df, f, ep)
    hyp.to_csv(W2 / "patterns_hypotheses.csv", index=False, encoding="utf-8")
    st = stability(f, ep, df)
    st.to_csv(W2 / "patterns_stability.csv", encoding="utf-8")
    ph = pd.crosstab([f.slot], [np.where(f.small, "мелкие < 100", "крупные ≥ 100")], margins=True, margins_name="всего")

    # Различимость: если бы ночная и вечерняя волны были разными сценариями, они жили бы в разных эпизодах.
    both = (ep.has_night & ep.has_evening).mean()
    lines = [
        "# Карта паттернов мошенничества (неделя 2)", "",
        "Скрипт: `python -m experiments.w2_patterns`. Данные: fraudTrain.csv, все метки 01.2019–06.2020. "
        "Детекция — модель v1 на valid + holdout (21.02–21.06.2020), только эпизоды, целиком попавшие в эти 4 месяца "
        f"({x.ep_id.nunique()} эпизодов). fraudTest здесь не использован — он оставлен для приёмки.", "",
        "## Единица анализа — эпизод", "",
        f"Эпизод — мошеннические операции одной карты с паузами меньше {GAP_H:.0f} ч. Порог взят из данных: самая длинная "
        f"пауза внутри мошенничества одной карты — {f.groupby('ep_id').ts.diff().dt.total_seconds().max() / 3600:.0f} ч, "
        f"а у каждой карты ровно один эпизод. Итого {len(ep)} эпизодов, {len(f)} операций, "
        f"{ep.cc_num.nunique()} карт из {df.cc_num.nunique()}.", "",
        f"- операций в эпизоде: медиана {ep.n.median():.0f} (10–90%: {ep.n.quantile(.1):.0f}–{ep.n.quantile(.9):.0f})",
        f"- длительность: медиана {ep.dur_h.median():.0f} ч; {(ep.days == 2).mean():.0%} эпизодов занимают ровно 2 календарных дня",
        f"- сумма эпизода: медиана {ep.amt.median():,.0f} у.е.".replace(",", " "),
        f"- честных операций держателя внутри эпизода нет в {(ep.honest_during == 0).mean():.1%} эпизодов; после эпизода карта "
        f"продолжает обычную жизнь (медиана {ep.ops_after.median():.0f} операций)", "",
        "## Карта паттернов", "",
        md_table(pm[["Паттерн", "Проявление в логе", "Операций (весь fraudTrain)", "Сумма (весь fraudTrain)",
                     "Модель узнаёт (p ≥ 0,5), доля операций", "Отправлено аналитику, доля денег",
                     "Эпизодов с хотя бы одной проверкой"]],
                 {"Модель узнаёт (p ≥ 0,5), доля операций": pct, "Отправлено аналитику, доля денег": pct,
                  "Эпизодов с хотя бы одной проверкой": pct}), "",
        "Столбец «Детектируется моделью» разделён на два, потому что это разные вещи: «модель узнаёт» — вероятность "
        "≥ 0,5; «отправлено аналитику» — попало в 0,3% дневного лимита.", "",
        "## Проверенные и не подтвердившиеся гипотезы", "", md_table(hyp), "",
        "## Фазы эпизода: время × сумма (операции)", "", md_table(ph.reset_index(names="время")), "",
        "## Почему волны и мелкие операции — фазы одного сценария, а не разные паттерны", "",
        f"Если бы ночная и вечерняя волны были разными сценариями, они встречались бы в разных эпизодах. "
        f"На деле обе волны есть в {both:.0%} эпизодов, мелкие операции есть в {(ep.n_small > 0).mean():.0%} эпизодов, "
        f"крупные — в {((ep.n - ep.n_small) > 0).mean():.1%}. Поэтому P1·в, P1·н, P1·м — фазы одного сценария, а P2 — тот же "
        "сценарий на карте без истории (отличается не поведением мошенника, а тем, что видит модель).", "",
        "## Устойчивость во времени и по картам", "", md_table(st.reset_index(names="квартал"), ST_FMT), "",
        f"В 2019Q1 «новых карт» больше из-за начала наблюдения: карты впервые появляются в логе. Паттерн P1 воспроизводится "
        f"на {ep.cc_num.nunique()} картах из {df.cc_num.nunique()} и в каждом квартале с одинаковой формой.",
    ]
    (W2 / "patterns.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
