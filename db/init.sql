-- Схема базы антифрода (неделя 5). Postgres выполняет этот файл сам при первом запуске
-- контейнера db с ПУСТЫМ томом pgdata. Если том уже создан, изменения здесь не применятся:
-- для чистого старта нужен `docker compose down -v` (удаляет все данные).

-- 1. Каждый HTTP-запрос к сервису, включая ошибочные (422, 500, 503).
--    Пишется в middleware FastAPI, поэтому сюда попадают и запросы, отклонённые до функции predict.
CREATE TABLE IF NOT EXISTS request_log (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    endpoint    TEXT NOT NULL,           -- /predict, /label, /metrics, /health ...
    method      TEXT NOT NULL DEFAULT 'GET',
    status_code INT  NOT NULL,           -- 200, 404, 422, 500, 503
    error       TEXT,                    -- причина ошибки, если была
    latency_ms  REAL
);

-- 2. Каждая успешно оценённая операция: входные поля, оценка, решение, порог, версия модели.
CREATE TABLE IF NOT EXISTS transactions (
    id             UUID PRIMARY KEY,            -- transaction_id, который сервис вернул клиенту
    received_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    trans_num      TEXT,                        -- номер операции из датасета
    card_id        TEXT,                        -- cc_num
    amount         NUMERIC(12, 2),
    category       TEXT,
    merchant       TEXT,
    tx_time        TIMESTAMP,                   -- время операции из датасета
    payload        JSONB NOT NULL,              -- операция целиком, как пришла
    fraud_score    REAL NOT NULL,               -- откалиброванная вероятность фрода
    is_fraud_pred  SMALLINT NOT NULL,           -- 1 = фрод (fraud_score >= threshold)
    threshold      REAL NOT NULL,
    risk_level     TEXT,                        -- высокий / средний / низкий
    expected_value REAL,                        -- польза проверки, у.е.
    model_version  TEXT,
    latency_ms     REAL
);

-- 3. Фактическая метка, пришедшая позже через /label.
CREATE TABLE IF NOT EXISTS labels (
    transaction_id UUID PRIMARY KEY REFERENCES transactions(id),
    is_fraud       SMALLINT NOT NULL CHECK (is_fraud IN (0, 1)),
    labeled_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Индексы под запросы /metrics: окна по времени и лента срабатываний.
CREATE INDEX IF NOT EXISTS request_log_ts_idx          ON request_log (ts);
CREATE INDEX IF NOT EXISTS request_log_endpoint_ts_idx ON request_log (endpoint, ts);
CREATE INDEX IF NOT EXISTS transactions_received_idx   ON transactions (received_at);
CREATE INDEX IF NOT EXISTS transactions_flagged_idx    ON transactions (received_at DESC) WHERE is_fraud_pred = 1;
CREATE INDEX IF NOT EXISTS transactions_card_idx       ON transactions (card_id);
