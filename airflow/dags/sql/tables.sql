CREATE TABLE IF NOT EXISTS holdout_transactions (
    transaction_id TEXT PRIMARY KEY,
    is_fraud SMALLINT NOT NULL CHECK (is_fraud IN (0, 1)),
    amount NUMERIC(14, 2) NOT NULL,
    row_data JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS scored_transactions (
    transaction_id TEXT NOT NULL,
    fraud_score REAL NOT NULL,
    is_fraud_pred SMALLINT NOT NULL CHECK (is_fraud_pred IN (0, 1)),
    threshold REAL,
    model_version TEXT NOT NULL,
    run_id TEXT NOT NULL,
    scored_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (transaction_id, model_version)
);

CREATE TABLE IF NOT EXISTS prescoring_runs (
    run_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    row_count BIGINT NOT NULL,
    flagged_count BIGINT NOT NULL,
    prevented_count BIGINT NOT NULL,
    prevented_amount NUMERIC(16, 2) NOT NULL,
    missed_count BIGINT NOT NULL,
    missed_amount NUMERIC(16, 2) NOT NULL,
    false_positive_count BIGINT NOT NULL,
    false_positive_amount NUMERIC(16, 2) NOT NULL,
    review_cost NUMERIC(16, 2) NOT NULL,
    missed_commission NUMERIC(16, 2) NOT NULL,
    net_effect NUMERIC(16, 2) NOT NULL,
    fraud_coverage_pct NUMERIC(7, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS business_reports (
    run_id TEXT PRIMARY KEY REFERENCES prescoring_runs(run_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    llm_model TEXT NOT NULL,
    facts JSONB NOT NULL,
    report_text TEXT NOT NULL,
    check_passed BOOLEAN NOT NULL,
    unexpected_numbers JSONB NOT NULL DEFAULT '[]'::jsonb
);
