"""Интерфейс оператора (неделя 3) — Streamlit.

streamlit run frontend/app.py --server.port 8501

Работает только через API сервиса (по умолчанию http://localhost:8000): модель не загружает,
журнал не читает. Файл data/holdout.csv читает сам — это источник операций для подачи.
"""
import json
import os
import random
import time
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

API = os.environ.get("ANTIFRAUD_API", "http://localhost:8000")
ROOT = Path(__file__).resolve().parents[1]
HOLDOUT = ROOT / "data" / "holdout.csv"
CATEGORIES = ["entertainment", "food_dining", "gas_transport", "grocery_net", "grocery_pos", "health_fitness",
              "home", "kids_pets", "misc_net", "misc_pos", "personal_care", "shopping_net", "shopping_pos", "travel"]
CAT_RU = {"entertainment": "развлечения", "food_dining": "кафе и рестораны", "gas_transport": "АЗС и транспорт",
          "grocery_net": "продукты онлайн", "grocery_pos": "продукты в магазине", "health_fitness": "здоровье и спорт",
          "home": "товары для дома", "kids_pets": "дети и животные", "misc_net": "разное онлайн",
          "misc_pos": "разное в магазине", "personal_care": "уход за собой", "shopping_net": "покупки онлайн",
          "shopping_pos": "покупки в магазине", "travel": "путешествия"}
DEMO_START = 0          # holdout начинается 02.12.2020 22:00 — вечерняя волна мошенничества в первых 200 строках

st.set_page_config(page_title="Антифрод — оператор", page_icon="🛡️", layout="wide")


@st.cache_data
def load_holdout() -> pd.DataFrame:
    return pd.read_csv(HOLDOUT, low_memory=False)


def row_payload(row: pd.Series) -> dict:
    """Строка датасета -> JSON для /predict (без is_fraud)."""
    d = json.loads(row.drop(labels=["is_fraud"], errors="ignore").to_json(force_ascii=False))
    return {k: v for k, v in d.items() if v is not None}


def call(method: str, path: str, **kw):
    try:
        r = requests.request(method, API + path, timeout=30, **kw)
        try:
            body = r.json()
        except ValueError:
            body = {"detail": r.text}
        return r.status_code, body
    except requests.RequestException as e:
        return None, {"detail": f"сервис недоступен: {e}"}


def verdict_box(res: dict):
    fraud = res["is_fraud_pred"] == 1
    color = "#B42318" if fraud else "#1F6B45"
    bg = "#FDECEA" if fraud else "#E6F4EC"
    text = "ФРОД — операцию остановить" if fraud else "НЕ ФРОД — пропустить"
    st.markdown(
        f"<div style='background:{bg};border-left:8px solid {color};padding:14px 18px;border-radius:6px'>"
        f"<div style='font-size:28px;font-weight:700;color:{color}'>{text}</div>"
        f"<div style='font-size:16px;margin-top:4px'>Оценка модели (вероятность фрода): "
        f"<b>{res['fraud_score']:.3f}</b> · порог {res['threshold']:.2f} · группа риска: <b>{res['risk_level']}</b></div>"
        f"</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("EV проверки", f"{res['expected_value']:.0f} у.е.", help="p·(сумма+5) − 3 − (1−p)·25")
    c2.metric("Прошлых операций карты", res["card_history"], help="сколько операций этой карты видел сервис")
    c3.metric("Время ответа", f"{res['latency_ms']:.0f} мс")
    if res.get("reasons"):
        st.markdown("**Почему:** " + " · ".join(res["reasons"]))


def truth_box(pred: int, label: int):
    names = {(1, 1): ("Верно: мошенничество остановлено", "success"),
             (0, 0): ("Верно: честная операция пропущена", "success"),
             (1, 0): ("Ошибка: ложная тревога — честная операция помечена как фрод", "warning"),
             (0, 1): ("Ошибка: пропуск — мошенничество не замечено", "error")}
    text, kind = names[(pred, label)]
    getattr(st, kind)(f"Фактическая метка: **{'мошенничество' if label else 'честная'}**. {text}. Метка отправлена в /label.")


# ---------------------------------------------------------------- боковая панель
with st.sidebar:
    st.header("Сервис")
    code, h = call("GET", "/health")
    if code == 200:
        st.success(f"Работает · модель {h['model']} · порог {h['threshold']}")
        st.caption(f"История карт: {h['history_rows']:,} операций до {h['history_end']}".replace(",", " "))
    else:
        st.error(h.get("detail", "сервис недоступен"))
    st.caption(f"API: {API} · [документация /docs]({API}/docs)")

    st.subheader("Порог (дополнительно)")
    thr = st.slider("Порог решения «фрод»", 0.05, 0.99, float(h.get("threshold", 0.5)) if code == 200 else 0.5, 0.01)
    if st.button("Применить порог"):
        c, b = call("PUT", "/threshold", json={"threshold": thr})
        st.toast(f"Порог: {b.get('old_threshold')} → {b.get('threshold')}" if c == 200 else str(b))
    if st.button("Новая сессия показателей"):
        c, b = call("POST", "/session/new")
        st.toast("Панель начнёт счёт заново" if c == 200 else str(b))

hold = load_holdout()
n_hold = len(hold)
st.title("Антифрод — интерфейс оператора")
st.caption(f"Holdout: {n_hold:,} операций ({hold['trans_date_trans_time'].iloc[0]} – {hold['trans_date_trans_time'].iloc[-1]}), "
           f"мошеннических {int(hold['is_fraud'].sum())}. Метка в /predict не передаётся — только после ответа, в /label."
           .replace(",", " "))

tab1, tab2, tab3 = st.tabs(["Одна операция", "Серия операций", "Некорректный запрос"])

# ---------------------------------------------------------------- одна операция
with tab1:
    src = st.radio("Источник", ["Строка из holdout", "Ручной ввод"], horizontal=True)
    if "row_idx" not in st.session_state:
        st.session_state.row_idx = 0
    if src == "Строка из holdout":
        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
        idx = c1.number_input("Номер строки holdout", 0, n_hold - 1, st.session_state.row_idx, step=1)
        st.session_state.row_idx = int(idx)
        if c2.button("Случайная строка"):
            st.session_state.row_idx = random.randrange(n_hold)
            st.rerun()
        if c3.button("Случайная честная"):
            st.session_state.row_idx = int(random.choice(hold.index[hold["is_fraud"] == 0]))
            st.rerun()
        if c4.button("Случайная мошенническая", help="для демонстрации: выбор по метке, сама метка в сервис не уходит"):
            st.session_state.row_idx = int(random.choice(hold.index[hold["is_fraud"] == 1]))
            st.rerun()
        base = row_payload(hold.iloc[st.session_state.row_idx])
        label = int(hold.iloc[st.session_state.row_idx]["is_fraud"])
    else:
        base = row_payload(hold.iloc[0])
        base["trans_num"] = None
        label = None

    key = f"{src}-{st.session_state.row_idx}"
    with st.form("tx"):
        st.markdown("**Операция** — значения можно поменять перед отправкой")
        a, b, c = st.columns(3)
        f_time = a.text_input("Время операции", base["trans_date_trans_time"], key="t" + key)
        f_amt = b.number_input("Сумма, у.е.", 0.0, 100000.0, float(base["amt"]), step=1.0, key="a" + key)
        f_cat = c.selectbox("Категория", CATEGORIES, CATEGORIES.index(base["category"]),
                            format_func=lambda x: f"{x} — {CAT_RU[x]}", key="c" + key)
        a, b, c = st.columns(3)
        f_cc = a.text_input("Номер карты (cc_num)", str(base["cc_num"]), key="cc" + key)
        f_merch = b.text_input("Магазин (merchant)", base["merchant"], key="m" + key)
        f_gender = c.selectbox("Пол держателя", ["F", "M"], ["F", "M"].index(base["gender"]), key="g" + key)
        with st.expander("Остальные поля датасета"):
            a, b, c = st.columns(3)
            f_dob = a.text_input("Дата рождения (dob)", base["dob"], key="d" + key)
            f_city = b.text_input("Город", base["city"], key="ci" + key)
            f_state = c.text_input("Штат", base["state"], key="s" + key)
            a, b, c = st.columns(3)
            f_lat = a.number_input("lat", value=float(base["lat"]), format="%.4f", key="la" + key)
            f_long = b.number_input("long", value=float(base["long"]), format="%.4f", key="lo" + key)
            f_pop = c.number_input("city_pop", value=float(base["city_pop"]), key="p" + key)
            a, b = st.columns(2)
            f_mlat = a.number_input("merch_lat", value=float(base["merch_lat"]), format="%.6f", key="ml" + key)
            f_mlong = b.number_input("merch_long", value=float(base["merch_long"]), format="%.6f", key="mo" + key)
        sent = st.form_submit_button("Отправить в сервис", type="primary")

    if sent:
        payload = dict(base)
        payload.update({"trans_date_trans_time": f_time, "amt": f_amt, "category": f_cat, "merchant": f_merch,
                        "gender": f_gender, "dob": f_dob, "city": f_city, "state": f_state, "lat": f_lat,
                        "long": f_long, "city_pop": f_pop, "merch_lat": f_mlat, "merch_long": f_mlong})
        try:
            payload["cc_num"] = int(f_cc)
        except ValueError:
            payload["cc_num"] = f_cc            # пусть сервис сам вернёт 422
        payload = {k: v for k, v in payload.items() if v is not None}
        code, res = call("POST", "/predict", json=payload)
        if code == 200:
            verdict_box(res)
            changed = (f_time != base["trans_date_trans_time"] or abs(f_amt - float(base["amt"])) > 1e-9
                       or f_cat != base["category"] or f_cc != str(base["cc_num"]) or f_merch != base["merchant"])
            if label is not None and not changed:
                call("POST", "/label", json={"transaction_id": res["transaction_id"], "is_fraud": label})
                truth_box(res["is_fraud_pred"], label)
            elif label is not None:
                st.info("Поля изменены — фактическая метка к этой операции уже не относится и в /label не отправлена.")
            with st.expander("Ответ сервиса (JSON)"):
                st.json(res)
        else:
            st.error(f"HTTP {code}: сервис отклонил запрос")
            st.json(res)

# ---------------------------------------------------------------- серия
with tab2:
    st.markdown("Следующие N строк holdout подаются **по одной** через `/predict`, после каждого ответа метка "
                "уходит в `/label`. Панель мониторинга в это время обновляется сама.")
    if "next_idx" not in st.session_state:
        st.session_state.next_idx = DEMO_START
    c1, c2, c3 = st.columns(3)
    n = c1.number_input("Сколько операций (N)", 1, 2000, 150, step=10)
    start = c2.number_input("С какой строки holdout", 0, n_hold - 1, int(st.session_state.next_idx), step=1)
    pause = c3.number_input("Пауза между операциями, с", 0.0, 5.0, 0.1, step=0.1)
    st.caption("Строки 0–199 — вечер 02.12.2020: там вечерняя волна мошенничества (13 операций).")
    if st.button(f"Отправить {int(n)} операций", type="primary"):
        rows = hold.iloc[int(start):int(start) + int(n)]
        bar = st.progress(0.0, "отправка…")
        stats = st.empty()
        flagged_box = st.empty()
        cnt = {"отправлено": 0, "успешно": 0, "ошибок": 0, "помечено фродом": 0, "фрод по факту": 0,
               "поймано": 0, "ложных тревог": 0, "пропущено": 0}
        flagged = []
        for k, (i, row) in enumerate(rows.iterrows()):
            code, res = call("POST", "/predict", json=row_payload(row))
            cnt["отправлено"] += 1
            y = int(row["is_fraud"])
            if code == 200:
                cnt["успешно"] += 1
                call("POST", "/label", json={"transaction_id": res["transaction_id"], "is_fraud": y})
                pred = res["is_fraud_pred"]
                cnt["помечено фродом"] += pred
                cnt["фрод по факту"] += y
                cnt["поймано"] += int(pred == 1 and y == 1)
                cnt["ложных тревог"] += int(pred == 1 and y == 0)
                cnt["пропущено"] += int(pred == 0 and y == 1)
                if pred or y:
                    flagged.append({"строка": i, "время": row["trans_date_trans_time"], "категория": row["category"],
                                    "сумма": row["amt"], "оценка": res["fraud_score"],
                                    "решение": "фрод" if pred else "не фрод", "факт": "фрод" if y else "честная"})
            else:
                cnt["ошибок"] += 1
            bar.progress((k + 1) / len(rows), f"{k + 1} из {len(rows)}")
            stats.dataframe(pd.DataFrame([cnt]), hide_index=True)
            if flagged:
                flagged_box.dataframe(pd.DataFrame(flagged), hide_index=True)
            if pause:
                time.sleep(pause)
        st.session_state.next_idx = int(start) + len(rows)
        st.success(f"Готово. Следующая серия начнётся со строки {st.session_state.next_idx}.")

# ---------------------------------------------------------------- ошибки
with tab3:
    st.markdown("Сервис должен отклонить некорректный вход кодом **422** и записать запрос в журнал как ошибку — "
                "тогда success rate на панели снизится. То же самое можно показать на странице "
                f"[{API}/docs]({API}/docs).")
    good = row_payload(hold.iloc[0])
    cases = {
        "Сумма текстом (amt = «сто»)": {**good, "amt": "сто"},
        "Нет поля category": {k: v for k, v in good.items() if k != "category"},
        "Неизвестная категория": {**good, "category": "casino"},
        "Отрицательная сумма": {**good, "amt": -50},
    }
    choice = st.selectbox("Что сломать", list(cases))
    if st.button("Отправить некорректную операцию"):
        code, res = call("POST", "/predict", json=cases[choice])
        (st.error if code != 200 else st.success)(f"HTTP {code}")
        st.json(res)
