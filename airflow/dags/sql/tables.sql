-- Таблицы недели 6 (прескоринг). Создаются первой задачей DAG через CREATE TABLE IF NOT EXISTS:
-- db/init.sql для этого не подходит — он выполняется только при инициализации пустого тома pgdata.

-- Отложенная выборка: поля датасета Sparkov + is_fraud (только для финансовых показателей, в модель не идёт).
CREATE TABLE IF NOT EXISTS holdout_transactions (
    trans_date_trans_time TIMESTAMP NOT NULL,
    cc_num        BIGINT,
    merchant      TEXT,
    category      TEXT,
    amt           NUMERIC(12, 2) NOT NULL,
    first         TEXT,
    last          TEXT,
    gender        TEXT,
    street        TEXT,
    city          TEXT,
    state         TEXT,
    zip           TEXT,
    lat           DOUBLE PRECISION,
    long          DOUBLE PRECISION,
    city_pop      DOUBLE PRECISION,
    job           TEXT,
    dob           DATE,
    trans_num     TEXT NOT NULL,
    unix_time     BIGINT,
    merch_lat     DOUBLE PRECISION,
    merch_long    DOUBLE PRECISION,
    is_fraud      SMALLINT NOT NULL CHECK (is_fraud IN (0, 1)),
    -- уникальный идентификатор операции: в датасете это trans_num
    transaction_id TEXT GENERATED ALWAYS AS (trans_num) STORED PRIMARY KEY
);

-- Результат прескоринга. Ключ (transaction_id, model_version): одна оценка на операцию и версию модели.
CREATE TABLE IF NOT EXISTS scored_transactions (
    transaction_id TEXT        NOT NULL,
    model_version  TEXT        NOT NULL,
    fraud_score    REAL        NOT NULL,
    is_fraud_pred  SMALLINT    NOT NULL,
    threshold      REAL        NOT NULL,
    run_id         TEXT        NOT NULL,
    scored_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (transaction_id, model_version)
);

-- Одна запись на запуск DAG: объём, срабатывания, финансовые показатели, допущения.
CREATE TABLE IF NOT EXISTS prescoring_runs (
    run_id             TEXT PRIMARY KEY,
    started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at        TIMESTAMPTZ,
    model_version      TEXT NOT NULL,
    threshold          REAL NOT NULL,
    period_from        TIMESTAMP,
    period_to          TIMESTAMP,
    rows_holdout       INT,
    rows_scored        INT,
    flagged            INT,
    tp_count           INT,
    tp_sum             NUMERIC(14, 2),
    fn_count           INT,
    fn_sum             NUMERIC(14, 2),
    fp_count           INT,
    fp_sum             NUMERIC(14, 2),
    fraud_sum          NUMERIC(14, 2),
    review_cost_total  NUMERIC(14, 2),
    lost_commission    NUMERIC(14, 2),
    net_effect         NUMERIC(14, 2),
    coverage_pct       NUMERIC(6, 2),
    assumptions        JSONB,
    compare            JSONB,
    facts              JSONB,              -- готовые строки для отчёта (вход языковой модели)
    report_check_passed BOOLEAN,
    status             TEXT NOT NULL DEFAULT 'scored'
);

-- Отчёт для руководства: входные показатели (facts), текст, результат проверки чисел.
CREATE TABLE IF NOT EXISTS business_reports (
    run_id       TEXT PRIMARY KEY,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    llm_model    TEXT  NOT NULL,
    facts        JSONB NOT NULL,
    report_text  TEXT  NOT NULL,
    check_passed BOOLEAN NOT NULL,
    extra_numbers TEXT[],
    attempts     INT
);

-- Все попытки языковой модели — для анализа: доля отчётов, прошедших проверку с первой попытки.
CREATE TABLE IF NOT EXISTS llm_attempts (
    run_id        TEXT NOT NULL,
    attempt       INT  NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    llm_model     TEXT NOT NULL,
    passed        BOOLEAN NOT NULL,
    extra_numbers TEXT[],
    seconds       REAL,
    report_text   TEXT NOT NULL,
    PRIMARY KEY (run_id, attempt)
);

-- для баз, созданных до добавления колонки
ALTER TABLE prescoring_runs ADD COLUMN IF NOT EXISTS facts JSONB;

CREATE INDEX IF NOT EXISTS scored_transactions_run_idx ON scored_transactions (run_id);
