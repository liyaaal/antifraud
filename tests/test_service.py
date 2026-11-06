"""Тесты сервиса (недели 3–5). Нужна база PostgreSQL:
  DATABASE_URL=postgresql+psycopg://antifraud:<пароль>@localhost:5433/antifraud python -m pytest tests/test_service.py -q
(с запущенным `docker compose up -d db`). Без DATABASE_URL тесты пропускаются."""
import os

import pandas as pd
import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="нужен DATABASE_URL к PostgreSQL")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from service.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def rows():
    from service.prepare import HOLDOUT_CSV
    h = pd.read_csv(HOLDOUT_CSV, low_memory=False)
    honest = h[h["is_fraud"] == 0].iloc[0].drop(labels=["is_fraud"]).to_dict()
    fraud = h[h["is_fraud"] == 1].iloc[0].drop(labels=["is_fraud"]).to_dict()
    return honest, fraud


def _db_count(sql):
    from sqlalchemy import text
    from service import db
    with db.engine().connect() as c:
        return c.execute(text(sql)).scalar()


def test_health(client):
    b = client.get("/health").json()
    assert b["status"] == "ok" and b["db"] == "up"


def test_predict_writes_transaction_and_label(client, rows):
    honest, fraud = rows
    before = _db_count("SELECT count(*) FROM transactions")
    b = client.post("/predict", json=honest).json()
    assert b["is_fraud_pred"] == int(b["fraud_score"] >= b["threshold"])
    assert _db_count("SELECT count(*) FROM transactions") == before + 1
    assert client.post("/label", json={"transaction_id": b["transaction_id"], "is_fraud": 0}).status_code == 200
    assert _db_count(f"SELECT is_fraud FROM labels WHERE transaction_id = '{b['transaction_id']}'") == 0
    assert client.post("/predict", json=fraud).json()["is_fraud_pred"] == 1


def test_422_is_logged_in_request_log(client, rows):
    honest, _ = rows
    before = _db_count("SELECT count(*) FROM request_log WHERE status_code = 422")
    assert client.post("/predict", json={**honest, "amt": "сто"}).status_code == 422
    assert _db_count("SELECT count(*) FROM request_log WHERE status_code = 422") == before + 1
    s = client.get("/metrics?window=5m").json()["summary"]
    assert s["errors_422"] >= 1 and s["success_rate"] < 1


def test_metrics_from_db(client):
    s = client.get("/metrics?window=all").json()["summary"]
    assert s["total_transactions_in_db"] == _db_count("SELECT count(*) FROM transactions")


def test_unknown_label_404(client):
    assert client.post("/label", json={"transaction_id": "нет-такого", "is_fraud": 1}).status_code == 404
    assert client.post("/label", json={"transaction_id": "00000000-0000-0000-0000-000000000000",
                                       "is_fraud": 1}).status_code == 404
