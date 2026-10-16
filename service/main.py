"""Сервис скоринга антифрода — FastAPI (неделя 3).

Запуск:  uvicorn service.main:app --port 8000
Документация и ручной вызов маршрутов: http://localhost:8000/docs

Маршруты:
  POST /predict    одна операция в формате строки датасета, без is_fraud -> оценка и решение
  POST /label      фактическая метка для уже оценённой операции
  GET  /metrics    данные для панели мониторинга
  GET  /health     сервис жив, модель загружена
  PUT  /threshold  смена порога без перезапуска (дополнительно)
  POST /session/new  начать новую сессию показателей (дополнительно)

Интерфейс оператора и панель мониторинга работают только через эти маршруты.
"""
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from service.journal import Journal, compute_metrics
from service.scoring import SERVICE_HISTORY, OnlineScorer

# Рабочая точка: откалиброванная вероятность ≥ 0,5 — «мошенничество вероятнее, чем нет».
# На valid (21.02–21.04.2020): точность 98,3%, чувствительность 94,1%. Меняется через PUT /threshold.
DEFAULT_THRESHOLD = 0.5

Category = Literal["entertainment", "food_dining", "gas_transport", "grocery_net", "grocery_pos",
                   "health_fitness", "home", "kids_pets", "misc_net", "misc_pos", "personal_care",
                   "shopping_net", "shopping_pos", "travel"]

STATE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.time()
    STATE["scorer"] = OnlineScorer()          # модель и история карт — один раз при старте
    STATE["journal"] = Journal()
    STATE["threshold"] = DEFAULT_THRESHOLD
    STATE["started"] = time.time()
    print(f"Сервис готов за {time.time() - t0:.1f} с: модель {STATE['scorer'].version}, "
          f"история карт {STATE['scorer'].history_rows} операций до {STATE['scorer'].history_end}")
    if not SERVICE_HISTORY.exists():
        print("ВНИМАНИЕ: не найдена data/cache/service_history.parquet — запустите python -m service.prepare")
    yield


app = FastAPI(
    title="Антифрод: сервис скоринга",
    description="Модель v2 (неделя 2): LightGBM + блоки признаков base, a, b, c, e. "
                "Операция приходит по одной, признаки по истории карты считаются тем же кодом, что в score.py.",
    version="3.0",
    lifespan=lifespan,
)
# Нужен только для варианта интерфейса на HTML/JS; Streamlit ходит к API со стороны сервера.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class Transaction(BaseModel):
    """Одна операция — строка датасета Sparkov без колонки is_fraud."""
    trans_date_trans_time: datetime = Field(description="время операции, например 2020-12-01 00:00:55")
    cc_num: int = Field(description="номер карты")
    merchant: str
    category: Category
    amt: float = Field(ge=0, description="сумма, у.е.")
    first: str | None = None
    last: str | None = None
    gender: Literal["F", "M"]
    street: str | None = None
    city: str
    state: str
    zip: int | str | None = None
    lat: float
    long: float
    city_pop: float = Field(ge=0)
    job: str | None = None
    dob: date = Field(description="дата рождения держателя")
    trans_num: str | None = Field(default=None, description="номер операции из датасета; если нет — выдаётся новый")
    unix_time: int | None = None
    merch_lat: float
    merch_long: float

    model_config = {"json_schema_extra": {"examples": [{
        "trans_date_trans_time": "2020-12-01 00:00:55", "cc_num": 676292294938,
        "merchant": "fraud_Stracke-Lemke", "category": "grocery_pos", "amt": 92.04,
        "first": "Lisa", "last": "Fitzpatrick", "gender": "F", "street": "58761 Brewer Rapids",
        "city": "Skytop", "state": "PA", "zip": 18357, "lat": 41.2336, "long": -75.2389,
        "city_pop": 104, "job": "Financial trader", "dob": "1927-08-25",
        "trans_num": "7734521672b0d4226e8beb2f32a18be6", "unix_time": 1385856055,
        "merch_lat": 42.146482, "merch_long": -74.328717}]}}


class Prediction(BaseModel):
    transaction_id: str
    fraud_score: float = Field(description="откалиброванная вероятность мошенничества, 0..1")
    is_fraud_pred: int = Field(description="1 — фрод (fraud_score ≥ threshold), 0 — не фрод")
    threshold: float
    risk_level: str = Field(description="группа риска недели 2: высокий ≥ 0,9 / средний 0,1–0,9 / низкий < 0,1")
    expected_value: float = Field(description="EV проверки, у.е.: p·(сумма+5) − 3 − (1−p)·25")
    reasons: list[str] = Field(description="главные причины оценки (вклад признаков); только при fraud_score ≥ 0,1")
    card_history: int = Field(description="сколько прошлых операций карты видел сервис")
    latency_ms: float


class Label(BaseModel):
    transaction_id: str
    is_fraud: Literal[0, 1]


class Threshold(BaseModel):
    threshold: float = Field(ge=0, le=1)


@app.exception_handler(RequestValidationError)
async def log_bad_request(request: Request, exc: RequestValidationError):
    """Некорректный вход FastAPI отклоняет с кодом 422; для /predict он тоже идёт в журнал как ошибка."""
    if request.url.path == "/predict" and "journal" in STATE:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        STATE["journal"].add(status="error", http_code=422, error=f"{where}: {first.get('msg', 'некорректный вход')}",
                             threshold=STATE["threshold"])
    return await request_validation_exception_handler(request, exc)


@app.post("/predict", response_model=Prediction, summary="Оценить одну операцию")
def predict(tx: Transaction):
    t0 = time.perf_counter()
    raw = tx.model_dump()
    raw["trans_date_trans_time"] = tx.trans_date_trans_time.strftime("%Y-%m-%d %H:%M:%S")
    raw["dob"] = tx.dob.isoformat()
    raw["trans_num"] = tx.trans_num or uuid.uuid4().hex
    tx_id = str(uuid.uuid4())
    thr = STATE["threshold"]
    journal: Journal = STATE["journal"]
    try:
        r = STATE["scorer"].score(raw)
    except Exception as e:  # модель или признаки упали — запрос в журнал со статусом «ошибка», код 500
        journal.add(transaction_id=tx_id, trans_num=raw["trans_num"], cc_num=str(tx.cc_num),
                    category=tx.category, amt=tx.amt, op_time=raw["trans_date_trans_time"], threshold=thr,
                    status="error", http_code=500, error=f"{type(e).__name__}: {e}",
                    latency_ms=round((time.perf_counter() - t0) * 1000, 1))
        raise HTTPException(status_code=500, detail=f"Ошибка скоринга: {e}")
    pred = int(r["p"] >= thr)
    latency = round((time.perf_counter() - t0) * 1000, 1)
    journal.add(transaction_id=tx_id, trans_num=raw["trans_num"], cc_num=str(r["cc_num"]), category=r["category"],
                amt=r["amt"], op_time=r["op_time"], score=r["p"], pred=pred, threshold=thr,
                risk_level=r["risk_level"], status="ok", http_code=200, latency_ms=latency)
    return Prediction(transaction_id=tx_id, fraud_score=r["p"], is_fraud_pred=pred, threshold=thr,
                      risk_level=r["risk_level"], expected_value=r["ev"],
                      reasons=r["reasons"] if r["p"] >= 0.1 else [],   # причины — только для подозрительных
                      card_history=r["card_history"], latency_ms=latency)


@app.post("/label", summary="Передать фактическую метку оценённой операции")
def label(lb: Label):
    if not STATE["journal"].set_label(lb.transaction_id, lb.is_fraud):
        raise HTTPException(status_code=404, detail="transaction_id не найден среди успешных запросов")
    return {"status": "ok", "transaction_id": lb.transaction_id, "is_fraud": lb.is_fraud}


@app.get("/metrics", summary="Показатели для панели мониторинга")
def metrics(bucket: int = 50):
    j: Journal = STATE["journal"]
    m = compute_metrics(j.rows(), STATE["threshold"], bucket=max(5, bucket))
    m["session"] = j.session
    m["session_started"] = time.strftime("%H:%M:%S", time.localtime(j.session_started))
    return m


@app.get("/health", summary="Сервис жив, модель загружена")
def health():
    s: OnlineScorer = STATE.get("scorer")
    if s is None:
        raise HTTPException(status_code=503, detail="модель не загружена")
    return {"status": "ok", "model": s.version, "threshold": STATE["threshold"],
            "history_rows": s.history_rows, "history_end": s.history_end,
            "session_ops": s.session_rows, "uptime_s": round(time.time() - STATE["started"], 1)}


@app.put("/threshold", summary="Сменить порог без перезапуска (дополнительно)")
def set_threshold(t: Threshold):
    old = STATE["threshold"]
    STATE["threshold"] = round(float(t.threshold), 4)
    return {"status": "ok", "old_threshold": old, "threshold": STATE["threshold"]}


@app.post("/session/new", summary="Начать новую сессию показателей (дополнительно)")
def new_session():
    return {"status": "ok", "session": STATE["journal"].new_session()}
