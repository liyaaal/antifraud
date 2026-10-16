"""Тесты сервиса недели 3: python -m pytest tests/test_service.py -q (нужен python -m service.prepare)."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from service.main import app
from service.prepare import HOLDOUT_CSV


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/session/new")
        yield c


@pytest.fixture(scope="module")
def rows():
    h = pd.read_csv(HOLDOUT_CSV, low_memory=False)
    honest = h[h["is_fraud"] == 0].iloc[0].drop(labels=["is_fraud"]).to_dict()
    fraud = h[h["is_fraud"] == 1].iloc[0].drop(labels=["is_fraud"]).to_dict()
    return honest, fraud


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_predict_and_label(client, rows):
    honest, fraud = rows
    r = client.post("/predict", json=honest)
    assert r.status_code == 200
    b = r.json()
    assert set(["transaction_id", "fraud_score", "is_fraud_pred", "threshold"]) <= set(b)
    assert 0 <= b["fraud_score"] <= 1 and b["is_fraud_pred"] == int(b["fraud_score"] >= b["threshold"])
    assert client.post("/label", json={"transaction_id": b["transaction_id"], "is_fraud": 0}).status_code == 200
    f = client.post("/predict", json=fraud).json()
    assert f["is_fraud_pred"] == 1


def test_bad_input_is_422_and_counted(client, rows):
    honest, _ = rows
    before = client.get("/metrics").json()["summary"]["errors"]
    assert client.post("/predict", json={**honest, "amt": "сто"}).status_code == 422
    assert client.post("/predict", json={k: v for k, v in honest.items() if k != "category"}).status_code == 422
    s = client.get("/metrics").json()["summary"]
    assert s["errors"] == before + 2 and s["success_rate"] < 1


def test_unknown_label_404(client):
    assert client.post("/label", json={"transaction_id": "нет-такого", "is_fraud": 1}).status_code == 404


def test_threshold(client, rows):
    honest, _ = rows
    assert client.put("/threshold", json={"threshold": 0.9}).json()["threshold"] == 0.9
    assert client.post("/predict", json=honest).json()["threshold"] == 0.9
    client.put("/threshold", json={"threshold": 0.5})
