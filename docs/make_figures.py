"""Графики для документа «Разбор решений». Числа читаются из reports/ (реальные запуски).

python docs/make_figures.py  ->  docs/fig/*.png
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "reports"
F = ROOT / "docs" / "fig"
F.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({"font.family": "Calibri", "font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#8F97A3", "axes.labelcolor": "#161A22", "xtick.color": "#5B6472",
                     "ytick.color": "#5B6472"})
TEAL, RED, AMBER, GREY, INK, GOLD = "#1F8A7A", "#D6452F", "#E9A83B", "#B8BFCA", "#161A22", "#D9A43A"


def thousands(v):
    return f"{v:,.0f}".replace(",", " ")


# 1. Турнир: тепловая карта (наборы признаков × модели)
t = pd.read_csv(R / "tournament.csv")
t = t[t["решение"].isna()]
order = ["сырые поля", "+ A (профиль)", "+ B (ритм)", "+ C (среда)", "+ A + B", "+ A + B + C", "+ A + B + C5"]
models = ["LogReg", "LightGBM", "LightGBM монотонный", "LightGBM, учит деньгам"]
piv = t.pivot_table(index="признаки", columns="модель", values="экономия", aggfunc="last").reindex(order)[models] / 1000
fig, ax = plt.subplots(figsize=(8, 4.2))
im = ax.imshow(piv.values, cmap="BuGn", vmin=165, vmax=256, aspect="auto")
ax.set_xticks(range(len(models)), ["LogReg", "LightGBM", "LightGBM\nс запретом", "LightGBM\n«учит деньгам»"])
ax.set_yticks(range(len(order)), ["Сырые поля", "+ A профиль", "+ B ритм", "+ C среда", "+ A + B", "+ A + B + C",
                                  "+ A + B + сумма из C"])
for i in range(piv.shape[0]):
    for j in range(piv.shape[1]):
        v = piv.values[i, j]
        ax.text(j, i, f"{v:.1f}".replace(".", ","), ha="center", va="center", fontsize=11,
                color="white" if v > 225 else INK, fontweight="bold" if (i == 6 and j == 3) else "normal")
ax.add_patch(plt.Rectangle((2.5, 5.5), 1, 1, fill=False, ec=AMBER, lw=3))
ax.set_title("Экономия на 2 месяцах проверки, тыс. у.е. (потолок — 255,5)", loc="left", fontsize=12, color=INK)
for s in ax.spines.values():
    s.set_visible(False)
ax.tick_params(length=0)
fig.tight_layout()
fig.savefig(F / "tournament_heat.png", dpi=200)
plt.close(fig)

# 2. Кто какой сценарий ловит
lines = [l for l in (R / "scenarios.md").read_text(encoding="utf-8").splitlines() if l.startswith("|")][2:]
rows = [[c.strip() for c in l.strip("|").split("|")] for l in lines]
sc = pd.DataFrame(rows, columns=["вариант", "сценарий", "фродов", "сумма", "шт", "уе", "доля"])
names = {"A: профиль (LightGBM)": "A: профиль", "B: ритм (LightGBM монотонный)": "B: ритм",
         "финал: A+B+C5, учит деньгам": "Финал"}
fig, axes = plt.subplots(1, 3, figsize=(10, 3.4))
for ax, (scen, title, key) in zip(axes, [("первая операция серии", "Первая операция кражи\nпоймано, у.е.", "уе"),
                                         ("продолжение серии", "Продолжение серии\nпоймано, тыс. у.е.", "уе"),
                                         ("ложные отправки (честные)", "Честных клиентов\nостановлено зря", "шт")]):
    sub = sc[(sc["сценарий"] == scen) & sc["вариант"].isin(names)]
    vals = sub[key].astype(float).to_numpy()
    if scen == "продолжение серии":
        vals = vals / 1000
    labs = [names[v] for v in sub["вариант"]]
    cols = [RED, AMBER, TEAL]
    bars = ax.bar(labs, vals, color=cols, width=0.6)
    lo = vals.min() * (0.85 if scen != "ложные отправки (честные)" else 0)
    ax.set_ylim(lo, vals.max() * 1.12)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, (f"{v:,.1f}" if scen == "продолжение серии" else f"{v:,.0f}")
                .replace(",", " ").replace(".", ","), ha="center", va="bottom", fontsize=11, fontweight="bold")
    ax.set_title(title, fontsize=11.5, loc="left", color=INK)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
fig.suptitle("Разбор по сценариям, 2 месяца проверки. Шкалы первых двух графиков начинаются не с нуля", fontsize=9.5,
             color="#5B6472", y=0.035)
fig.tight_layout(rect=(0, 0.09, 1, 1))
fig.savefig(F / "scenarios.png", dpi=200)
plt.close(fig)

# 3. Холдаут: все варианты
eco = json.loads((R / "economics.json").read_text(encoding="utf-8"))
tab = pd.DataFrame(eco["table"]).set_index("index")
show = [("Правило «проверять самые дорогие»", "Правило «самые дорогие»", GREY),
        ("Базовая модель, по вероятности", "База, по вероятности", GREY),
        ("Базовая модель, по деньгам", "База, по деньгам", GREY),
        ("Решение A (профиль, LogReg)", "Решение A", RED),
        ("Решение C (среда, учит деньгам)", "Решение C", TEAL),
        ("Решение B (ритм, монотонный LightGBM)", "Решение B", AMBER),
        ("Финал", "Финал", GOLD),
        ("Потолок (идеальная модель)", "Потолок", "#E6D9B8")]
fig, ax = plt.subplots(figsize=(8.5, 4))
vals = [tab.loc[k, "экономия"] for k, _, _ in show]
bars = ax.barh([l for _, l, _ in show], vals, color=[c for _, _, c in show], height=0.62)
ax.invert_yaxis()
for b, v, (k, _, _) in zip(bars, vals, show):
    fp = int(tab.loc[k, "честных клиентов остановлено"])
    ax.text(v + 4000, b.get_y() + b.get_height() / 2, f"{thousands(v)}   (зря остановлено: {fp})", va="center", fontsize=10.5)
ax.set_xlim(0, 470000)
ax.set_xticks([])
ax.spines["bottom"].set_visible(False)
ax.set_title("Отложенные 2 месяца: экономия, у.е. Потери без системы — 513 229", loc="left", fontsize=12, color=INK)
fig.tight_layout()
fig.savefig(F / "holdout.png", dpi=200)
plt.close(fig)

# 4. Сколько проверок нужно
cur = pd.DataFrame(eco["curve"])
fig, ax = plt.subplots(figsize=(8, 3.6))
ax.plot(cur["проверок в день"], cur["экономия"] / 1000, "-o", color=TEAL, lw=2.2, label="как сейчас")
ax.plot(cur["проверок в день"], cur["экономия ×3"] / 1000, "-o", color=RED, lw=2.2, label="если фрода втрое больше")
ax.axvline(6.7, color=GREY, ls="--")
ax.text(6.9, 50, "сейчас:\n≈7 проверок\nв день", fontsize=10, color="#5B6472")
ax.set_xlabel("проверок в день")
ax.set_ylabel("экономия за 2 месяца, тыс. у.е.")
ax.legend(frameon=False, loc="lower right")
ax.set_title("Больше проверок — больше спасённых денег, но после ~15 в день рост почти останавливается",
             loc="left", fontsize=11.5, color=INK)
ax.grid(axis="y", color="#E6E9EE")
fig.tight_layout()
fig.savefig(F / "capacity.png", dpi=200)
plt.close(fig)

# 5. Вклад признаков A и B (по одному)
e = pd.read_csv(R / "experiments.csv")
seq = e[e["added_feature"].notna() & (e["added_feature"] != "(старт)")]
for cfg, fname, col, ttl in [("a", "features_a.png", RED, "Решение A (LogReg): вклад каждого признака, у.е."),
                             ("b", "features_b.png", AMBER, "Решение B (LightGBM с запретом): вклад каждого признака, у.е.")]:
    d = seq[(seq["config"] == cfg) & ((seq["policy"] == "ev_cap"))].drop_duplicates("added_feature", keep="last")
    fig, ax = plt.subplots(figsize=(8, 0.36 * len(d) + 0.9))
    y = np.arange(len(d))
    ax.barh(y, d["delta_savings"], color=[col if lo > 0 else GREY for lo in d["delta_ci_low"]], height=0.6)
    ax.errorbar(d["delta_savings"], y, xerr=[d["delta_savings"] - d["delta_ci_low"], d["delta_ci_high"] - d["delta_savings"]],
                fmt="none", ecolor=INK, elinewidth=1, capsize=3)
    ax.set_yticks(y, d["added_feature"])
    ax.invert_yaxis()
    ax.axvline(0, color=INK, lw=0.8)
    ax.set_title(ttl + "\nцветом — интервал целиком выше нуля; серым — в пределах шума", loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(F / fname, dpi=200)
    plt.close(fig)
print(sorted(p.name for p in F.glob("*.png")))
