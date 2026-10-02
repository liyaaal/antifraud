"""Три короткие причины для аналитика (владелец A, TASK_A).

Берём признаки с наибольшим положительным вкладом в скор операции и переводим их в обычные слова.
Причина показывается, только если она правда верна для этой операции (например, «ночная» — только ночью),
иначе берём следующую. Никаких «z-score», «бит» и названий колонок.
"""
import math

import numpy as np
import pandas as pd

CATEGORY_RU = {
    "shopping_net": "покупки онлайн", "shopping_pos": "покупки в магазине", "misc_net": "разное онлайн",
    "misc_pos": "разное в магазине", "grocery_net": "продукты онлайн", "grocery_pos": "продукты в магазине",
    "gas_transport": "топливо и транспорт", "travel": "путешествия", "entertainment": "развлечения",
    "food_dining": "кафе и рестораны", "personal_care": "уход за собой", "health_fitness": "здоровье и спорт",
    "kids_pets": "дети и животные", "home": "товары для дома",
}
TIME_BANDS = ["с 0 до 4 часов", "с 4 до 8 часов", "с 8 до 12 часов", "с 12 до 16 часов", "с 16 до 20 часов",
              "с 20 до 24 часов"]


def _fmt(x, nd=0):
    return f"{x:,.{nd}f}".replace(",", " ")


def _reason(f: str, r: dict):
    """(ключ, текст) или None, если причина для этой операции неверна. Ключ убирает дубликаты."""
    amt, cat, hour = r["amt"], CATEGORY_RU.get(r["category"], r["category"]), int(r["hour"])
    if f in ("amt", "log_amt"):
        return ("amt", f"Крупная сумма: {_fmt(amt, 2)} у.е.") if amt >= 100 else None
    if f == "c_amt_pct_cat" and r.get(f, 0) >= 0.95:
        share = "99%" if r[f] >= 0.99 else f"{r[f]:.0%}"
        return ("amt", f"Сумма {_fmt(amt, 2)} у.е. — дороже {share} покупок в категории «{cat}»")
    if f == "category":
        return ("cat", f"Категория «{cat}» — частая цель мошенников")
    if f in ("hour", "is_night") and (hour >= 22 or hour <= 3):
        return ("night", f"Ночная операция ({hour:02d}:{int(r['minute']):02d})")
    if f == "is_online" and r["category"].endswith("_net"):
        return ("online", f"Покупка в интернете ({cat})")
    if f in ("a_cat_bits", "a_cat_x_amt") and r.get("a_info_cat_share", 1) < 0.1:
        return ("a_cat", f"Клиент редко покупает в категории «{cat}»: около {r['a_info_cat_share']:.0%} его операций")
    if f in ("a_time_bits", "a_time_x_amt") and r.get("a_info_time_share", 1) < 0.1:
        return ("a_time", f"Клиент почти не платит {TIME_BANDS[hour // 4]}: около {r['a_info_time_share']:.0%} его операций")
    if f in ("a_amt_z", "a_amt_up", "a_surprise_total"):
        typ = r.get("a_info_typical_amt", np.nan)
        if typ and typ > 0 and amt / typ >= 2:
            return ("a_amt", f"Сумма в {amt / typ:.0f} раз больше обычной для этого клиента в этой категории "
                             f"(обычно около {_fmt(typ)} у.е.)")
        return None
    if f == "a_drift" and r.get(f, 0) > 0.5:
        return ("a_drift", f"В последние дни клиент тратит примерно в {math.exp(r[f]):.0f} раз крупнее, чем обычно")
    if f == "a_profile_log_n" and r.get("a_info_n", 99) < 20:
        n = int(r["a_info_n"])
        return ("a_n", "Новая карта: это её первая операция" if n == 0 else f"Почти новая карта: {n} операций в истории")
    if f == "b_gap_log_h" and not np.isnan(r.get(f, np.nan)):
        gap_h = math.expm1(r[f])
        if gap_h < 1:
            return ("b_gap", f"Операция через {max(gap_h * 60, 1):.0f} мин после предыдущей")
        return None
    if f in ("b_int_1h", "b_int_24h", "b_act_ratio") and r.get("b_act_ratio", 0) >= 2:
        return ("b_act", f"Карта сейчас в {r['b_act_ratio']:.0f} раз активнее, чем обычно для этого клиента")
    if f == "b_amt_int_24h" and r.get(f, 0) >= 100:
        return ("b_amt24", f"За последние сутки по карте уже списано около {_fmt(r[f])} у.е.")
    if f in ("b_sess_pos", "b_sess_cum_amt", "b_sess_escalation") and r.get("b_sess_pos", 1) >= 3:
        return ("b_sess", f"Уже {int(r['b_sess_pos'])}-я операция подряд без перерыва, в серии потрачено "
                          f"{_fmt(r.get('b_sess_cum_amt', 0))} у.е.")
    if f == "b_sess_night_share" and r.get(f, 0) >= 0.5 and r.get("b_sess_pos", 1) >= 2:
        return ("b_night", f"Серия из {int(r['b_sess_pos'])} операций ночью")
    if f == "b_amt_rank10" and r.get(f, 0) >= 1 and r.get("a_info_n", 10) >= 5:
        return ("b_rank", "Сумма больше, чем в каждой из 10 последних операций клиента")
    if f == "b_online_streak" and r.get(f, 0) >= 3:
        return ("b_streak", f"{int(r[f])} онлайн-покупок подряд")
    return None


def top_reasons(contrib: pd.DataFrame, rows: pd.DataFrame, k: int = 3) -> pd.DataFrame:
    """contrib — вклад признаков (строки = операции); rows — сырые поля + признаки (+ служебные a_info_*)."""
    out = []
    feats = list(contrib.columns)
    C = contrib.to_numpy()
    recs = rows.to_dict("records")
    for i in range(len(recs)):
        r = recs[i]
        order = np.argsort(-C[i])
        seen, texts = set(), []
        for j in order:
            if C[i, j] <= 0 or len(texts) == k:
                break
            got = _reason(feats[j], r)
            if got and got[0] not in seen:
                seen.add(got[0])
                texts.append(got[1])
        out.append(texts + [""] * (k - len(texts)))
    return pd.DataFrame(out, index=contrib.index, columns=[f"reason_{i + 1}" for i in range(k)])
