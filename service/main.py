"""Сервис скоринга антифрода — FastAPI (недели 3–5).

Запуск в Docker:  docker compose up -d --build        (база PostgreSQL — контейнер db)
Документация и ручной вызов маршрутов: http://localhost:8000/docs

Маршруты (не изменились с недели 3):
  POST /predict    одна операция в формате строки датасета, без is_fraud -> оценка и решение
  POST /label      фактическая метка для уже оценённой операции
  GET  /metrics    данные для панели мониторинга (?window=5m|1h|all)
  GET  /health     сервис жив, модель загружена, база доступна
  PUT  /threshold  смена порога без перезапуска (дополнительно)

Неделя 5: журнал запросов, решения и метки хранятся в PostgreSQL (service/db.py, db/init.sql).
Каждый HTTP-запрос, включая ошибочные 422, пишется в таблицу request_log в middleware.
Интерфейс оператора и панель мониторинга работают только через эти маршруты и к базе не подключаются.
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
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from service import db
from service.scoring import SERVICE_HISTORY, OnlineScorer

# Рабочая точка: откалиброванная вероятность ≥ 0,5 — «мошенничество вероятнее, чем нет».
# На valid (21.02–21.04.2020): точность 98,3%, чувствительность 94,1%. Меняется через PUT /threshold.
DEFAULT_THRESHOLD = 0.5
MODEL_VERSION = "final_v2"
NOT_LOGGED = {"/docs", "/openapi.json", "/favicon.ico", "/redoc"}   # служебные страницы в журнал не пишем

Category = Literal["entertainment", "food_dining", "gas_transport", "grocery_net", "grocery_pos",
                   "health_fitness", "home", "kids_pets", "misc_net", "misc_pos", "personal_care",
                   "shopping_net", "shopping_pos", "travel"]

STATE: dict = {}


def restore_history_from_db(scorer: OnlineScorer) -> int:
    """Дополнительно: история карт переживает перезапуск — операции, уже оценённые сервисом,
    берутся из transactions.payload и дописываются к стартовой истории."""
    from sqlalchemy import text
    try:
        with db.engine().connect() as c:
            rows = [r[0] for r in c.execute(text("SELECT payload FROM transactions ORDER BY received_at"))]
    except Exception as e:
        print(f"ВНИМАНИЕ: история из базы не загружена ({type(e).__name__}) — база недоступна при старте")
        return 0
    if rows:
        scorer.extend_history(rows)
    return len(rows)


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.time()
    STATE["scorer"] = OnlineScorer()          # модель и история карт — один раз при старте
    STATE["threshold"] = DEFAULT_THRESHOLD
    STATE["started"] = time.time()
    db.engine()                               # подключение к базе создаётся один раз
    n = restore_history_from_db(STATE["scorer"])
    print(f"Сервис готов за {time.time() - t0:.1f} с: модель {STATE['scorer'].version}, "
          f"история карт {STATE['scorer'].history_rows} операций до {STATE['scorer'].history_end}, "
          f"из базы восстановлено {n}; база {'доступна' if db.ping() else 'НЕДОСТУПНА'}")
    if not SERVICE_HISTORY.exists():
        print("ВНИМАНИЕ: не найдена data/cache/service_history.parquet — запустите подготовку (README)")
    yield


app = FastAPI(
    title="Антифрод: сервис скоринга",
    description="Модель v2 (неделя 2): LightGBM + блоки признаков base, a, b, c, e. "
                "Операция приходит по одной, признаки по истории карты считаются тем же кодом, что в score.py. "
                "Журнал, решения и метки — в PostgreSQL.",
    version="5.0",
    lifespan=lifespan,
)
# Нужен только для варианта интерфейса на HTML/JS; Streamlit ходит к API со стороны сервера.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Журнал КАЖДОГО запроса в request_log. Запрос с ошибкой 422 не доходит до функции predict —
    FastAPI отклоняет его раньше, — поэтому журнал пишется здесь, где виден любой запрос и ответ."""
    start = time.perf_counter()
    status, error = 500, None
    try:
        response = await call_next(request)
        status = response.status_code
        error = getattr(request.state, "error", None)
        return response
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        raise
    finally:
        if request.url.path not in NOT_LOGGED:
            # если база упала, log_request молча пропускает запись — клиент всё равно получает ответ
            db.log_request(request.url.path, request.method, status, error,
                           round((time.perf_counter() - start) * 1000, 1))


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
async def bad_request(request: Request, exc: RequestValidationError):
    """Некорректный вход — 422. Причину кладём в request.state, middleware запишет её в request_log."""
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(x) for x in first.get("loc", []) if x != "body")
    request.state.error = f"{where}: {first.get('msg', 'некорректный вход')}"
    return await request_validation_exception_handler(request, exc)


def db_down(request: Request, e: Exception) -> HTTPException:
    request.state.error = f"база недоступна: {e}"
    return HTTPException(status_code=503, detail="База данных недоступна: решение не записано в журнал, "
                                                 "операция не оценена. Повторите позже.")


@app.post("/predict", response_model=Prediction, summary="Оценить одну операцию")
def predict(tx: Transaction, request: Request):
    t0 = time.perf_counter()
    raw = tx.model_dump()
    raw["trans_date_trans_time"] = tx.trans_date_trans_time.strftime("%Y-%m-%d %H:%M:%S")
    raw["dob"] = tx.dob.isoformat()
    raw["trans_num"] = tx.trans_num or uuid.uuid4().hex
    tx_id = str(uuid.uuid4())
    thr = STATE["threshold"]
    try:
        r = STATE["scorer"].score(raw, update=False)   # историю карты дописываем только после записи в базу
    except Exception as e:  # модель или признаки упали — 500, middleware запишет в request_log
        request.state.error = f"{type(e).__name__}: {e}"
        raise HTTPException(status_code=500, detail=f"Ошибка скоринга: {e}")
    pred = int(r["p"] >= thr)
    latency = round((time.perf_counter() - t0) * 1000, 1)
    try:
        db.insert_transaction({
            "id": tx_id, "trans_num": raw["trans_num"], "card_id": str(r["cc_num"]), "amount": r["amt"],
            "category": r["category"], "merchant": tx.merchant, "tx_time": raw["trans_date_trans_time"],
            "payload": raw, "fraud_score": r["p"], "is_fraud_pred": pred, "threshold": thr,
            "risk_level": r["risk_level"], "expected_value": r["ev"], "model_version": MODEL_VERSION,
            "latency_ms": latency})
    except db.DatabaseUnavailable as e:
        # Решение команды: без записи в журнал решение не выдаём — банку нужен след каждого решения.
        raise db_down(request, e)
    STATE["scorer"].add_history(r)
    return Prediction(transaction_id=tx_id, fraud_score=r["p"], is_fraud_pred=pred, threshold=thr,
                      risk_level=r["risk_level"], expected_value=r["ev"],
                      reasons=r["reasons"] if r["p"] >= 0.1 else [],   # причины — только для подозрительных
                      card_history=r["card_history"], latency_ms=latency)


@app.post("/label", summary="Передать фактическую метку оценённой операции")
def label(lb: Label, request: Request):
    try:
        uuid.UUID(lb.transaction_id)
    except ValueError:
        request.state.error = "transaction_id не UUID"
        raise HTTPException(status_code=404, detail="transaction_id не найден среди оценённых операций")
    try:
        found = db.upsert_label(lb.transaction_id, lb.is_fraud)
    except db.DatabaseUnavailable as e:
        raise db_down(request, e)
    if not found:
        request.state.error = "transaction_id не найден"
        raise HTTPException(status_code=404, detail="transaction_id не найден среди оценённых операций")
    return {"status": "ok", "transaction_id": lb.transaction_id, "is_fraud": lb.is_fraud}


@app.get("/metrics", summary="Показатели для панели мониторинга (SQL-запросы к базе)")
def metrics(request: Request, window: Literal["5m", "1h", "all"] = "all", bucket: int = 25):
    try:
        return db.compute_metrics(window=window, bucket=max(5, bucket), threshold=STATE["threshold"])
    except db.DatabaseUnavailable as e:
        raise db_down(request, e)


@app.get("/health", summary="Сервис жив, модель загружена, база доступна")
def health():
    s: OnlineScorer = STATE.get("scorer")
    if s is None:
        return JSONResponse(status_code=503, content={"status": "down", "detail": "модель не загружена"})
    ok = db.ping()
    return {"status": "ok" if ok else "degraded", "db": "up" if ok else "down", "model": s.version,
            "threshold": STATE["threshold"], "history_rows": s.history_rows, "history_end": s.history_end,
            "session_ops": s.session_rows, "uptime_s": round(time.time() - STATE["started"], 1)}


@app.put("/threshold", summary="Сменить порог без перезапуска (дополнительно)")
def set_threshold(t: Threshold):
    old = STATE["threshold"]
    STATE["threshold"] = round(float(t.threshold), 4)
    return {"status": "ok", "old_threshold": old, "threshold": STATE["threshold"]}
