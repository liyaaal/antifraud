"""Разведка данных «глазами аналитика». Только на части train — valid и holdout не смотрим.

python -m src.eda  ->  reports/eda.md, reports/fig_*.png
"""
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.data import ROOT, load_train
from src.split import assign, boundaries

REPORTS = ROOT / "reports"


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def main():
    REPORTS.mkdir(exist_ok=True)
    df = load_train()
    b = boundaries(df.ts)
    df = df[assign(df.ts, b) == "train"].copy()
    lines = ["# Разведка данных (только train, до 21.02.2020)", ""]

    def add(title, obj):
        lines.append(f"## {title}")
        lines.append("")
        lines.append("```")
        lines.append(obj.to_string() if hasattr(obj, "to_string") else str(obj))
        lines.append("```")
        lines.append("")

    days = df.ts.dt.normalize().nunique()
    add("Объём", pd.Series({
        "операций": len(df), "дней": days, "операций в день": round(len(df) / days, 1),
        "фрод, шт": int(df.is_fraud.sum()), "доля фрода": round(df.is_fraud.mean(), 5),
        "фрода в день": round(df.is_fraud.sum() / days, 2),
        "лимит аналитиков в день (0,3%)": round(0.003 * len(df) / days, 2),
        "карт": df.cc_num.nunique(), "карт с фродом": df.loc[df.is_fraud == 1, "cc_num"].nunique(),
        "сумма фрода, у.е.": round(float(df.loc[df.is_fraud == 1, "amt"].sum()), 2),
    }))

    df["hour"] = df.ts.dt.hour
    add("Доля фрода по часу", df.groupby("hour").is_fraud.agg(["mean", "sum"]).round(4))
    add("Доля фрода по категории", df.groupby("category").agg(
        rate=("is_fraud", "mean"), fraud=("is_fraud", "sum"),
        amt_legit_median=("amt", lambda s: s[df.loc[s.index, "is_fraud"] == 0].median()),
        amt_fraud_median=("amt", lambda s: s[df.loc[s.index, "is_fraud"] == 1].median()),
    ).sort_values("rate", ascending=False).round(4))

    # Серии фрода на карте
    f = df[df.is_fraud == 1].sort_values(["cc_num", "ts"])
    series = f.groupby("cc_num").agg(n=("amt", "size"), first=("ts", "min"), last=("ts", "max"),
                                     total=("amt", "sum"))
    series["span_days"] = (series["last"] - series["first"]).dt.total_seconds() / 86400
    add("Серии фрода на одной карте (описательно)", series[["n", "span_days", "total"]].describe().round(2))
    gaps = f.groupby("cc_num").ts.diff().dt.total_seconds().div(3600).dropna()
    add("Пауза между соседними фрод-операциями карты, часы", gaps.describe(percentiles=[.1, .25, .5, .75, .9]).round(2))

    # Проверка мелкой суммой: первая фрод-операция серии
    first_fraud = f.groupby("cc_num").head(1)
    add("Сумма ПЕРВОЙ фрод-операции серии", first_fraud.amt.describe(percentiles=[.1, .25, .5, .75, .9]).round(2))

    # Гео
    df["dist_km"] = haversine_km(df.lat, df.long, df.merch_lat, df.merch_long)
    add("Расстояние клиент–мерчант, км", df.groupby("is_fraud").dist_km.describe().round(1))

    # Возраст
    df["age_band"] = pd.cut(df.age, [0, 25, 40, 60, 75, 120], right=False)
    add("Доля фрода по возрасту", df.groupby("age_band", observed=True).is_fraud.agg(["mean", "sum"]).round(4))

    # Фрод не помещается в лимит: сколько денег максимум можно спасти
    df["day"] = df.ts.dt.normalize()
    cap = df.groupby("day").size().mul(0.003).astype(int)
    fr = df[df.is_fraud == 1].sort_values(["day", "amt"], ascending=[True, False])
    fr["rank"] = fr.groupby("day").cumcount()
    fr["fits"] = fr["rank"] < fr["day"].map(cap)
    total = fr.amt.sum() + 5 * len(fr)
    caught = (fr.amt + 5)[fr.fits].sum() - 3 * fr.fits.sum()
    add("Идеальная модель при лимите 0,3% (знает правду, берёт самые дорогие фроды дня)", pd.Series({
        "фрода всего, шт": len(fr), "помещается в лимит, шт": int(fr.fits.sum()),
        "доля фрода по штукам": round(fr.fits.mean(), 4),
        "потери без системы, у.е.": round(float(total), 2),
        "максимально возможная экономия, у.е.": round(float(caught), 2),
        "доля денег, которую можно спасти": round(float(caught / total), 4),
    }))

    (REPORTS / "eda.md").write_text("\n".join(lines), encoding="utf-8")

    fig, ax = plt.subplots(1, 2, figsize=(10, 3.2))
    hr = df.groupby("hour").is_fraud.mean() * 100
    ax[0].bar(hr.index, hr.values, color="#3b5b92")
    ax[0].set_title("Доля мошенничества по часу, %")
    ax[0].set_xlabel("час")
    for y, c, lab in [(0, "#9aa7bd", "обычные"), (1, "#c2453d", "мошенничество")]:
        ax[1].hist(df.loc[df.is_fraud == y, "dist_km"], bins=60, density=True, alpha=0.6, color=c, label=lab)
    ax[1].set_title("Расстояние до мерчанта, км")
    ax[1].legend()
    fig.tight_layout()
    fig.savefig(REPORTS / "fig_eda.png", dpi=150)
    print((REPORTS / "eda.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
