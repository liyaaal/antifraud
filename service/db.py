"""Работа сервиса с PostgreSQL (неделя 5).

Подключение — SQLAlchemy + драйвер psycopg, адрес берётся из переменной окружения DATABASE_URL:
  в Docker:            postgresql+psycopg://antifraud:<пароль>@db:5432/antifraud   (db — имя контейнера)
  с компьютера (отладка): postgresql+psycopg://antifraud:<пароль>@localhost:5433/antifraud

Движок создаётся один раз при старте и переиспользуется. pool_pre_ping=True проверяет соединение
перед каждым запросом: если база перезапускалась, сервис сам переподключится без перезапуска.

Все SQL-запросы — только с параметрами (:amount, :since), без склейки строк: защита от SQL-инъекций.
"""
import json
import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import InterfaceError, OperationalError

WINDOWS = {"5m": "5 minutes", "1h": "1 hour", "all": None}   # окно наблюдения панели

_engine: Engine | None = None


class DatabaseUnavailable(Exception):
    """База недоступна: сервис отвечает 503, а не зависает."""


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Не задана переменная DATABASE_URL (см. .env.example и README, раздел «Неделя 5»)")
    return url


def engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(database_url(), pool_pre_ping=True, pool_size=5, max_overflow=5,
                                connect_args={"connect_timeout": 3})
    return _engine


def _run(fn):
    """Выполнить работу с базой; любая ошибка соединения превращается в DatabaseUnavailable."""
    try:
        return fn()
    except (OperationalError, InterfaceError, ConnectionError, TimeoutError) as e:   # нет связи с базой
        raise DatabaseUnavailable(f"{type(e).__name__}: {str(e).splitlines()[0][:200]}") from e


def ping() -> bool:
    try:
        with engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- запись

def log_request(endpoint: str, method: str, status: int, error: str | None, latency_ms: float) -> None:
    """Журнал каждого HTTP-запроса. Если база упала — молча пропускаем: ответ клиенту важнее журнала."""
    try:
        with engine().begin() as c:
            c.execute(text("INSERT INTO request_log (endpoint, method, status_code, error, latency_ms) "
                           "VALUES (:ep, :m, :st, :err, :lat)"),
                      {"ep": endpoint, "m": method, "st": status, "err": error, "lat": latency_ms})
    except Exception:
        pass


def insert_transaction(row: dict) -> None:
    def go():
        with engine().begin() as c:
            c.execute(text("""
                INSERT INTO transactions (id, trans_num, card_id, amount, category, merchant, tx_time, payload,
                                          fraud_score, is_fraud_pred, threshold, risk_level, expected_value,
                                          model_version, latency_ms)
                VALUES (:id, :trans_num, :card_id, :amount, :category, :merchant, :tx_time, CAST(:payload AS JSONB),
                        :fraud_score, :is_fraud_pred, :threshold, :risk_level, :expected_value,
                        :model_version, :latency_ms)
            """), {**row, "payload": json.dumps(row["payload"], ensure_ascii=False, default=str)})
    _run(go)


def upsert_label(transaction_id: str, is_fraud: int) -> bool:
    """Метка для операции. False — такой операции нет в transactions."""
    def go():
        with engine().begin() as c:
            exists = c.execute(text("SELECT 1 FROM transactions WHERE id = CAST(:id AS UUID)"),
                               {"id": transaction_id}).first()
            if not exists:
                return False
            c.execute(text("""
                INSERT INTO labels (transaction_id, is_fraud) VALUES (CAST(:id AS UUID), :y)
                ON CONFLICT (transaction_id) DO UPDATE SET is_fraud = EXCLUDED.is_fraud, labeled_at = now()
            """), {"id": transaction_id, "y": int(is_fraud)})
            return True
    return _run(go)


# ---------------------------------------------------------------- показатели для панели

def _rate(num, den):
    return round(float(num) / float(den), 4) if den else None


def compute_metrics(window: str = "all", bucket: int = 25, threshold: float = 0.5, recent: int = 20) -> dict:
    """Все показатели панели — SQL-запросами к базе. window: 5m / 1h / all."""
    iv = WINDOWS.get(window, None)
    p = {"iv": iv}
    # NULL-интервал = «всё время»: условие истинно для всех строк
    w_req = "(CAST(:iv AS interval) IS NULL OR ts > now() - CAST(:iv AS interval))"
    w_tx = "(CAST(:iv AS interval) IS NULL OR t.received_at > now() - CAST(:iv AS interval))"

    def go():
        with engine().connect() as c:
            r = c.execute(text(f"""
                SELECT count(*)                                         AS requests,
                       count(*) FILTER (WHERE status_code < 400)       AS ok,
                       count(*) FILTER (WHERE status_code = 422)       AS e422,
                       count(*) FILTER (WHERE status_code >= 500)      AS e5xx,
                       count(*) FILTER (WHERE status_code >= 400)      AS errors,
                       percentile_cont(0.5)  WITHIN GROUP (ORDER BY latency_ms) FILTER (WHERE status_code = 200) AS p50,
                       percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) FILTER (WHERE status_code = 200) AS p95
                FROM request_log
                WHERE endpoint = '/predict' AND {w_req}
            """), p).mappings().one()
            t = c.execute(text(f"""
                SELECT count(*)                                              AS n,
                       coalesce(sum(t.is_fraud_pred), 0)                     AS flagged,
                       avg(t.is_fraud_pred)                                  AS fr_model,
                       count(l.is_fraud)                                     AS labeled,
                       coalesce(sum(l.is_fraud), 0)                          AS fact,
                       avg(l.is_fraud)                                       AS fr_fact,
                       avg(t.is_fraud_pred) FILTER (WHERE l.is_fraud IS NOT NULL) AS fr_model_lab,
                       count(*) FILTER (WHERE t.is_fraud_pred = 1 AND l.is_fraud = 1) AS tp,
                       count(*) FILTER (WHERE t.is_fraud_pred = 1 AND l.is_fraud = 0) AS fp,
                       count(*) FILTER (WHERE t.is_fraud_pred = 0 AND l.is_fraud = 1) AS fn,
                       count(*) FILTER (WHERE t.is_fraud_pred = 0 AND l.is_fraud = 0) AS tn,
                       coalesce(sum(t.amount) FILTER (WHERE t.is_fraud_pred = 1 AND l.is_fraud = 1), 0) AS stopped,
                       coalesce(sum(t.amount) FILTER (WHERE t.is_fraud_pred = 0 AND l.is_fraud = 1), 0) AS missed
                FROM transactions t
                LEFT JOIN labels l ON l.transaction_id = t.id
                WHERE {w_tx}
            """), p).mappings().one()
            total = c.execute(text("SELECT count(*) AS tx, (SELECT count(*) FROM labels) AS lab, "
                                   "(SELECT count(*) FROM request_log) AS req FROM transactions")).mappings().one()

            # ряды для графиков: по минутам и по каждым N операциям
            req_min = c.execute(text(f"""
                SELECT date_trunc('minute', ts) AS m, count(*) AS n, avg((status_code < 400)::int) AS sr
                FROM request_log WHERE endpoint = '/predict' AND {w_req}
                GROUP BY 1 ORDER BY 1
            """), p).mappings().all()
            tx_min = c.execute(text(f"""
                SELECT date_trunc('minute', t.received_at) AS m, avg(t.is_fraud_pred) AS frm, avg(l.is_fraud) AS frf
                FROM transactions t LEFT JOIN labels l ON l.transaction_id = t.id
                WHERE {w_tx} GROUP BY 1 ORDER BY 1
            """), p).mappings().all()
            req_b = c.execute(text(f"""
                SELECT (row_number() OVER (ORDER BY ts, id) - 1) / :b AS k, (status_code < 400)::int AS ok
                FROM request_log WHERE endpoint = '/predict' AND {w_req}
            """), {**p, "b": bucket}).mappings().all()
            tx_b = c.execute(text(f"""
                SELECT (row_number() OVER (ORDER BY t.received_at, t.id) - 1) / :b AS k,
                       t.is_fraud_pred AS pred, l.is_fraud AS y
                FROM transactions t LEFT JOIN labels l ON l.transaction_id = t.id WHERE {w_tx}
            """), {**p, "b": bucket}).mappings().all()

            flagged = c.execute(text(f"""
                SELECT t.received_at, t.id, t.trans_num, t.card_id, t.category, t.amount, t.tx_time,
                       t.fraud_score, t.risk_level, l.is_fraud AS label
                FROM transactions t LEFT JOIN labels l ON l.transaction_id = t.id
                WHERE t.is_fraud_pred = 1 AND {w_tx}
                ORDER BY t.received_at DESC LIMIT :lim
            """), {**p, "lim": recent}).mappings().all()
            errors = c.execute(text(f"""
                SELECT ts, endpoint, status_code, error FROM request_log
                WHERE status_code >= 400 AND endpoint = '/predict' AND {w_req}
                ORDER BY ts DESC LIMIT 10
            """), p).mappings().all()
        return r, t, total, req_min, tx_min, req_b, tx_b, flagged, errors

    r, t, total, req_min, tx_min, req_b, tx_b, flagged, errors = _run(go)

    summary = {
        "window": window,
        "requests": r["requests"], "ok": r["ok"], "errors": r["errors"],
        "errors_422": r["e422"], "errors_500": r["e5xx"],
        "success_rate": _rate(r["ok"], r["requests"]),
        "transactions": t["n"], "flagged": int(t["flagged"]),
        "fraud_rate_model": round(float(t["fr_model"]), 4) if t["fr_model"] is not None else None,
        "labeled": t["labeled"], "fraud_fact": int(t["fact"]),
        "fraud_rate_fact": round(float(t["fr_fact"]), 4) if t["fr_fact"] is not None else None,
        "fraud_rate_model_on_labeled": round(float(t["fr_model_lab"]), 4) if t["fr_model_lab"] is not None else None,
        "tp": t["tp"], "fp": t["fp"], "fn": t["fn"], "tn": t["tn"],
        "precision": _rate(t["tp"], t["tp"] + t["fp"]),
        "recall": _rate(t["tp"], t["tp"] + t["fn"]),
        "money_stopped": round(float(t["stopped"]), 2), "money_missed": round(float(t["missed"]), 2),
        "latency_p50_ms": round(float(r["p50"]), 1) if r["p50"] is not None else None,
        "latency_p95_ms": round(float(r["p95"]), 1) if r["p95"] is not None else None,
        "threshold": threshold,
        "total_transactions_in_db": total["tx"], "total_labels_in_db": total["lab"],
        "total_requests_in_db": total["req"],
    }

    alerts = []
    if r["requests"] >= 10 and summary["success_rate"] is not None and summary["success_rate"] < 0.95:
        alerts.append(f"Success rate {summary['success_rate']:.1%} ниже 95%")
    if summary["latency_p95_ms"] and summary["latency_p95_ms"] > 1000:
        alerts.append(f"Медленные ответы: p95 = {summary['latency_p95_ms']:.0f} мс")
    if t["labeled"] >= 50 and summary["fraud_rate_fact"] is not None and summary["fraud_rate_model_on_labeled"] is not None:
        if abs(summary["fraud_rate_model_on_labeled"] - summary["fraud_rate_fact"]) > 0.02:
            alerts.append("Fraud rate модели и фактический разошлись больше чем на 2 п.п.")

    # минуты
    by_minute = {}
    for x in req_min:
        by_minute[x["m"]] = {"bucket": x["m"].strftime("%H:%M"), "requests": x["n"],
                             "success_rate": round(float(x["sr"]), 4), "fraud_rate_model": None, "fraud_rate_fact": None}
    for x in tx_min:
        d = by_minute.setdefault(x["m"], {"bucket": x["m"].strftime("%H:%M"), "requests": 0, "success_rate": None})
        d["fraud_rate_model"] = round(float(x["frm"]), 4) if x["frm"] is not None else None
        d["fraud_rate_fact"] = round(float(x["frf"]), 4) if x["frf"] is not None else None
    series_by_minute = [by_minute[k] for k in sorted(by_minute)]

    # каждые N операций
    agg: dict[int, dict] = {}
    for x in req_b:
        a = agg.setdefault(int(x["k"]), {"n": 0, "ok": 0, "pred": [], "y": []})
        a["n"] += 1
        a["ok"] += x["ok"]
    for x in tx_b:
        a = agg.setdefault(int(x["k"]), {"n": 0, "ok": 0, "pred": [], "y": []})
        a["pred"].append(x["pred"])
        if x["y"] is not None:
            a["y"].append(x["y"])
    series_by_ops = []
    for k in sorted(agg):
        a = agg[k]
        series_by_ops.append({
            "bucket": f"{k * bucket + 1}–{k * bucket + max(a['n'], len(a['pred']))}",
            "requests": a["n"],
            "success_rate": _rate(a["ok"], a["n"]),
            "fraud_rate_model": _rate(sum(a["pred"]), len(a["pred"])),
            "fraud_rate_fact": _rate(sum(a["y"]), len(a["y"])),
        })

    return {
        "summary": summary,
        "alerts": alerts,
        "series_by_ops": series_by_ops,
        "series_by_minute": series_by_minute,
        "bucket_size": bucket,
        "recent_flagged": [{
            "time": x["received_at"].astimezone().strftime("%H:%M:%S"),
            "transaction_id": str(x["id"]), "trans_num": x["trans_num"],
            "card": ("…" + str(x["card_id"])[-4:]) if x["card_id"] else "",
            "category": x["category"], "amt": float(x["amount"]) if x["amount"] is not None else None,
            "op_time": str(x["tx_time"]), "fraud_score": x["fraud_score"], "risk_level": x["risk_level"],
            "label": x["label"]} for x in flagged],
        "recent_errors": [{"time": x["ts"].astimezone().strftime("%H:%M:%S"), "http_code": x["status_code"],
                           "error": x["error"]} for x in errors],
    }


# ---------------------------------------------------------------- неделя 6: отчёт прескоринга
def latest_report() -> dict | None:
    """Последний бизнес-отчёт DAG prescoring (Airflow) вместе с записью о запуске. None — отчётов ещё нет."""
    def go():
        with engine().connect() as c:
            exists = c.execute(text("SELECT to_regclass('public.business_reports') IS NOT NULL")).scalar()
            if not exists:
                return None
            row = c.execute(text("""
                SELECT b.run_id, b.created_at, b.llm_model, b.facts, b.report_text, b.check_passed,
                       b.extra_numbers, b.attempts, r.model_version, r.threshold, r.rows_scored, r.flagged,
                       r.tp_sum, r.fn_sum, r.fp_sum, r.net_effect, r.coverage_pct, r.assumptions, r.compare
                FROM business_reports b LEFT JOIN prescoring_runs r ON r.run_id = b.run_id
                ORDER BY b.created_at DESC LIMIT 1""")).mappings().first()
            if row is None:
                return None
            d = dict(row)
            d["created_at"] = d["created_at"].isoformat()
            for k in ("threshold", "tp_sum", "fn_sum", "fp_sum", "net_effect", "coverage_pct"):
                d[k] = None if d[k] is None else float(d[k])
            return d
    return _run(go)
