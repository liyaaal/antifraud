"""Панель мониторинга (неделя 3) — Streamlit.

streamlit run dashboard/app.py --server.port 8502

Данные берутся только из GET /metrics сервиса. Панель обновляется сама каждые несколько секунд.
"""
import os

import altair as alt
import pandas as pd
import requests
import streamlit as st

API = os.environ.get("ANTIFRAUD_API", "http://localhost:8000")
# Адрес сервиса для ссылок в браузере (в Docker сервис внутри сети называется service, а браузер ходит на localhost)
API_PUBLIC = os.environ.get("ANTIFRAUD_API_PUBLIC", API)

st.set_page_config(page_title="Антифрод — мониторинг", page_icon="📈", layout="wide")
st.title("Антифрод — панель мониторинга")

with st.sidebar:
    st.header("Настройки")
    every = st.select_slider("Обновлять каждые, с", [2, 3, 5, 10], value=5)
    win_label = st.radio("Окно наблюдения", ["последние 5 минут", "последний час", "всё время"], index=2)
    window = {"последние 5 минут": "5m", "последний час": "1h", "всё время": "all"}[win_label]
    axis = st.radio("График по", ["каждым N запросам", "минутам"])
    bucket = st.select_slider("N запросов в точке", [10, 20, 25, 50, 100], value=25)
    st.caption(f"Источник: {API_PUBLIC}/metrics")
    st.markdown(
        "**Определения**\n\n"
        "- **Success rate** — доля запросов к /predict без ошибки (422 или 500) от всех запросов. "
        "Это здоровье сервиса, а не качество модели.\n"
        "- **Fraud rate, модель** — доля операций с is_fraud_pred = 1 среди успешно обработанных. "
        "Известен сразу, в момент операции.\n"
        "- **Fraud rate, факт** — доля is_fraud = 1 среди операций, для которых пришла метка. "
        "Известен только позже, после расследования.")


def tile(col, label, value, sub=None, help=None):
    """Плитка показателя; подпись снизу без стрелки (delta_arrow есть в новых Streamlit, в старых — без него)."""
    try:
        col.metric(label, value, sub, delta_color="off", delta_arrow="off", help=help, border=True)
    except TypeError:
        col.metric(label, value, sub, delta_color="off", help=help)


COLORS = {"success rate": "#1F6B45", "fraud rate, модель": "#B42318", "fraud rate, факт": "#6F7889"}


def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:.{nd}f}%".replace(".", ",")


def num(x):
    return f"{x:,.0f}".replace(",", " ")


def line(df: pd.DataFrame, cols: dict, title: str, fmt=".1%"):
    long = df.melt(id_vars=["bucket", "order"], value_vars=list(cols), var_name="ряд", value_name="значение")
    long["ряд"] = long["ряд"].map(cols)
    return (alt.Chart(long).mark_line(point=True)
            .encode(x=alt.X("bucket:N", sort=alt.SortField("order"), title=None),
                    y=alt.Y("значение:Q", axis=alt.Axis(format=fmt), title=None),
                    color=alt.Color("ряд:N", legend=alt.Legend(orient="bottom", title=None),
                                    scale=alt.Scale(domain=list(cols.values()),
                                                    range=[COLORS[v] for v in cols.values()])),
                    strokeDash=alt.StrokeDash("ряд:N", legend=None,
                                              scale=alt.Scale(domain=list(cols.values()),
                                                              range=[[1, 0], [6, 4]][:len(cols)])),
                    tooltip=["bucket", "ряд", alt.Tooltip("значение:Q", format=fmt)])
            .properties(title=title, height=260))


@st.fragment(run_every=f"{every}s")
def live():
    try:
        r = requests.get(f"{API}/metrics", params={"bucket": bucket, "window": window}, timeout=10)
        if r.status_code == 503:
            st.error("База данных недоступна: показатели считаются по PostgreSQL и сейчас не обновляются. "
                     "Как только база вернётся, панель продолжит работу сама.")
            return
        r.raise_for_status()
        m = r.json()
    except requests.RequestException as e:
        st.error(f"Сервис недоступен: {e}")
        return
    s = m["summary"]
    st.caption(f"Данные из PostgreSQL · окно: {win_label} · порог {s['threshold']} · "
               f"обновлено автоматически каждые {every} с")
    st.info(f"Всего в базе: **{num(s['total_transactions_in_db'])}** операций, "
            f"**{num(s['total_labels_in_db'])}** меток, **{num(s['total_requests_in_db'])}** запросов в журнале — "
            "не обнуляется при перезапуске контейнеров.")

    c = st.columns(4)
    tile(c[0], "Запросов к /predict", num(s["requests"]), help="в выбранном окне наблюдения")
    tile(c[1], "Success rate", pct(s["success_rate"]), f"ошибок {s['errors']} (422: {s['errors_422']}, 500: {s['errors_500']})")
    tile(c[2], "Fraud rate, модель", pct(s["fraud_rate_model"], 2), f"{s['flagged']} операций помечено")
    tile(c[3], "Fraud rate, факт", pct(s["fraud_rate_fact"], 2), f"{s['fraud_fact']} фрода по {s['labeled']} меткам")

    if m["alerts"]:
        for a in m["alerts"]:
            st.error("Тревога: " + a)
    elif s["requests"]:
        st.success("Норма: success rate ≥ 95%, ответы быстрые")

    c = st.columns(5)
    tile(c[0], "Точность", pct(s["precision"]), f"TP {s['tp']} · FP {s['fp']}",
         help="из помеченных моделью — сколько оказались фродом (по операциям с меткой)")
    tile(c[1], "Чувствительность", pct(s["recall"]), f"TP {s['tp']} · FN {s['fn']}",
         help="из фактического фрода — сколько модель поймала")
    tile(c[2], "Остановлено, у.е.", num(s["money_stopped"]), "сумма пойманного фрода")
    tile(c[3], "Пропущено, у.е.", num(s["money_missed"]), "сумма пропущенного фрода")
    tile(c[4], "Ответ p95", "—" if s["latency_p95_ms"] is None else f"{s['latency_p95_ms']:.0f} мс",
                "—" if s["latency_p50_ms"] is None else f"медиана {s['latency_p50_ms']:.0f} мс")

    ser = pd.DataFrame(m["series_by_ops"] if axis.startswith("каждым") else m["series_by_minute"])
    if len(ser):
        ser["order"] = range(len(ser))
        g1, g2 = st.columns(2)
        g1.altair_chart(line(ser, {"success_rate": "success rate"}, "Success rate"), use_container_width=True)
        g2.altair_chart(line(ser, {"fraud_rate_model": "fraud rate, модель", "fraud_rate_fact": "fraud rate, факт"},
                             "Fraud rate: модель и факт", fmt=".2%"), use_container_width=True)
    else:
        st.info("Запросов пока нет — отправьте операции из интерфейса оператора.")

    st.subheader("Последние срабатывания (модель сказала «фрод»)")
    rf = pd.DataFrame(m["recent_flagged"])
    if len(rf):
        rf["метка"] = rf["label"].map({1: "мошенничество ✓", 0: "честная ✗ (ложная тревога)"}).fillna("ещё нет")
        rf = rf.rename(columns={"time": "время запроса", "card": "карта", "category": "категория", "amt": "сумма, у.е.",
                                "op_time": "время операции", "fraud_score": "оценка", "risk_level": "риск"})
        st.dataframe(rf[["время запроса", "время операции", "карта", "категория", "сумма, у.е.", "оценка", "риск", "метка"]],
                     hide_index=True, use_container_width=True)
    else:
        st.caption("Срабатываний пока нет.")

    if m["recent_errors"]:
        st.subheader("Последние ошибки")
        st.dataframe(pd.DataFrame(m["recent_errors"]).rename(columns={"time": "время", "http_code": "код",
                                                                      "error": "причина"}),
                     hide_index=True, use_container_width=True)

    st.caption("Почему два fraud rate различаются: модель ошибается в обе стороны (ложные тревоги FP и пропуски FN), "
               "а метки приходят не для всех операций и позже. Fraud rate модели известен в момент операции, "
               "фактический — только после проверки.")


def prescoring_report():
    """Неделя 6: последний отчёт DAG prescoring из GET /reports/latest (не обновляется каждые N секунд)."""
    st.divider()
    st.subheader("Прескоринг (Airflow): последний бизнес-отчёт")
    try:
        r = requests.get(f"{API}/reports/latest", timeout=10)
    except requests.RequestException as e:
        st.caption(f"Сервис недоступен: {e}")
        return
    if r.status_code == 404:
        st.caption("Отчётов пока нет — запустите DAG prescoring в Airflow (http://localhost:8083).")
        return
    if r.status_code != 200:
        st.caption(f"Отчёт недоступен (HTTP {r.status_code}).")
        return
    rep = r.json()
    c = st.columns(4)
    tile(c[0], "Предотвращено, USD", num(rep["tp_sum"]), "пойманный фрод")
    tile(c[1], "Пропущено, USD", num(rep["fn_sum"]), "понесённые потери")
    tile(c[2], "Чистый эффект, USD", num(rep["net_effect"]), "после затрат на проверку")
    tile(c[3], "Покрытие фрода", "—" if rep["coverage_pct"] is None else f"{rep['coverage_pct']:.1f}%".replace(".", ","),
         f"модель {rep['model_version']}, порог {rep['threshold']}")
    ok = rep["check_passed"]
    (st.success if ok else st.warning)(
        ("Проверка чисел пройдена" if ok else f"Проверка чисел НЕ пройдена: {', '.join(rep['extra_numbers'] or [])}")
        + f" · {rep['llm_model']} · попыток: {rep['attempts']} · запуск {rep['run_id']}")
    st.markdown(rep["report_text"])
    with st.expander("Входные показатели (facts) и допущения"):
        st.json({"facts": rep["facts"], "assumptions": rep["assumptions"], "compare": rep["compare"]})


live()
prescoring_report()

