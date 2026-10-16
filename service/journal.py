"""Журнал запросов сервиса — SQLite (logs/journal.sqlite).

Одна строка = один запрос к /predict: время, операция, оценка, решение, статус, метка.
Журнал переживает перезапуск сервиса; показатели панели считаются по текущей сессии
(сессия = один запуск сервиса или явный POST /session/new).
"""
import sqlite3
import threading
import time
import uuid
from pathlib import Path

import numpy as np

from src.data import ROOT

DB_PATH = ROOT / "logs" / "journal.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session       TEXT NOT NULL,
    created       REAL NOT NULL,      -- время запроса (unix, сек)
    transaction_id TEXT,              -- выдаёт сервис
    trans_num     TEXT,               -- номер операции из датасета, если был
    cc_num        TEXT,
    category      TEXT,
    amt           REAL,
    op_time       TEXT,               -- время операции из датасета
    score         REAL,               -- fraud_score (вероятность)
    pred          INTEGER,            -- is_fraud_pred
    threshold     REAL,
    risk_level    TEXT,
    status        TEXT NOT NULL,      -- ok / error
    http_code     INTEGER,
    error         TEXT,
    latency_ms    REAL,
    label         INTEGER,            -- фактическая метка, приходит позже через /label
    label_time    REAL
);
CREATE INDEX IF NOT EXISTS ix_tx ON requests(transaction_id);
CREATE INDEX IF NOT EXISTS ix_session ON requests(session);
"""


class Journal:
    def __init__(self, path: Path = DB_PATH):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(path), check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        self.lock = threading.Lock()
        self.new_session()

    def new_session(self) -> str:
        self.session = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        self.session_started = time.time()
        return self.session

    def add(self, **row) -> None:
        row = {"session": self.session, "created": time.time(), **row}
        cols = ", ".join(row)
        q = ", ".join("?" for _ in row)
        with self.lock:
            self.con.execute(f"INSERT INTO requests ({cols}) VALUES ({q})", list(row.values()))
            self.con.commit()

    def set_label(self, transaction_id: str, label: int) -> bool:
        with self.lock:
            cur = self.con.execute(
                "UPDATE requests SET label = ?, label_time = ? WHERE transaction_id = ? AND status = 'ok'",
                (int(label), time.time(), transaction_id))
            self.con.commit()
            return cur.rowcount > 0

    def rows(self, session: str | None = None) -> list[dict]:
        with self.lock:
            cur = self.con.execute("SELECT * FROM requests WHERE session = ? ORDER BY id",
                                   (session or self.session,))
            return [dict(r) for r in cur.fetchall()]


def _rate(num: int, den: int):
    return round(num / den, 4) if den else None


def compute_metrics(rows: list[dict], threshold: float, bucket: int = 50, recent: int = 20) -> dict:
    """Все показатели панели из строк журнала одной сессии."""
    n = len(rows)
    ok = [r for r in rows if r["status"] == "ok"]
    err = [r for r in rows if r["status"] != "ok"]
    flagged = [r for r in ok if r["pred"] == 1]
    labeled = [r for r in ok if r["label"] is not None]
    fact = [r for r in labeled if r["label"] == 1]
    tp = sum(1 for r in labeled if r["pred"] == 1 and r["label"] == 1)
    fp = sum(1 for r in labeled if r["pred"] == 1 and r["label"] == 0)
    fn = sum(1 for r in labeled if r["pred"] == 0 and r["label"] == 1)
    tn = sum(1 for r in labeled if r["pred"] == 0 and r["label"] == 0)
    lat = [r["latency_ms"] for r in ok if r["latency_ms"] is not None]

    summary = {
        "requests": n,
        "ok": len(ok),
        "errors": len(err),
        "errors_422": sum(1 for r in err if r["http_code"] == 422),
        "errors_500": sum(1 for r in err if r["http_code"] == 500),
        "success_rate": _rate(len(ok), n),
        "flagged": len(flagged),
        "fraud_rate_model": _rate(len(flagged), len(ok)),
        "labeled": len(labeled),
        "fraud_fact": len(fact),
        "fraud_rate_fact": _rate(len(fact), len(labeled)),
        "fraud_rate_model_on_labeled": _rate(sum(1 for r in labeled if r["pred"] == 1), len(labeled)),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": _rate(tp, tp + fp),
        "recall": _rate(tp, tp + fn),
        "money_stopped": round(sum(r["amt"] for r in labeled if r["pred"] == 1 and r["label"] == 1), 2),
        "money_missed": round(sum(r["amt"] for r in labeled if r["pred"] == 0 and r["label"] == 1), 2),
        "latency_p50_ms": round(float(np.percentile(lat, 50)), 1) if lat else None,
        "latency_p95_ms": round(float(np.percentile(lat, 95)), 1) if lat else None,
        "threshold": threshold,
    }

    alerts = []
    if n >= 10 and summary["success_rate"] is not None and summary["success_rate"] < 0.95:
        alerts.append(f"Success rate {summary['success_rate']:.1%} ниже 95%")
    if summary["latency_p95_ms"] and summary["latency_p95_ms"] > 1000:
        alerts.append(f"Медленные ответы: p95 = {summary['latency_p95_ms']:.0f} мс")
    if len(labeled) >= 50 and summary["fraud_rate_fact"] is not None and summary["fraud_rate_model_on_labeled"] is not None:
        if abs(summary["fraud_rate_model_on_labeled"] - summary["fraud_rate_fact"]) > 0.02:
            alerts.append("Fraud rate модели и фактический разошлись больше чем на 2 п.п.")

    def point(chunk, label):
        okc = [r for r in chunk if r["status"] == "ok"]
        labc = [r for r in okc if r["label"] is not None]
        return {
            "bucket": label,
            "requests": len(chunk),
            "success_rate": _rate(len(okc), len(chunk)),
            "fraud_rate_model": _rate(sum(1 for r in okc if r["pred"] == 1), len(okc)),
            "fraud_rate_fact": _rate(sum(1 for r in labc if r["label"] == 1), len(labc)),
        }

    by_ops = [point(rows[i:i + bucket], f"{i + 1}–{min(i + bucket, n)}") for i in range(0, n, bucket)]
    by_min: dict[str, list] = {}
    for r in rows:
        by_min.setdefault(time_label(r["created"]), []).append(r)
    by_minute = [point(v, k) for k, v in by_min.items()]

    def short(r):
        return {
            "time": time_label(r["created"], seconds=True),
            "transaction_id": r["transaction_id"],
            "trans_num": r["trans_num"],
            "card": ("…" + str(r["cc_num"])[-4:]) if r["cc_num"] else "",
            "category": r["category"],
            "amt": r["amt"],
            "op_time": r["op_time"],
            "fraud_score": r["score"],
            "risk_level": r["risk_level"],
            "label": r["label"],
        }

    return {
        "summary": summary,
        "alerts": alerts,
        "series_by_ops": by_ops,
        "series_by_minute": by_minute,
        "bucket_size": bucket,
        "recent_flagged": [short(r) for r in reversed(flagged[-recent:])],
        "recent_errors": [{"time": time_label(r["created"], seconds=True), "http_code": r["http_code"],
                           "error": r["error"]} for r in reversed(err[-10:])],
    }


def time_label(t: float, seconds: bool = False) -> str:
    return time.strftime("%H:%M:%S" if seconds else "%H:%M", time.localtime(t))
