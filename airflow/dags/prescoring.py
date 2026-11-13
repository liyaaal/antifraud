"""Пакетный прескоринг и проверяемый бизнес-отчёт для учебного стенда."""
from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import psycopg
import requests
from psycopg.types.json import Jsonb

from airflow.sdk import dag, get_current_context, task

PROJECT = Path("/opt/airflow/model")
ARTIFACTS = PROJECT / "artifacts" / "final_v2"
INPUT_CSV = Path("/opt/airflow/data/holdout.csv")
TMP = Path("/opt/airflow/data/tmp")
MODEL_VERSION = "final_v2"
ASSUMPTIONS = {"currency": "USD", "review_cost": 2.0, "commission_rate": 0.015}


def db_connect():
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"], port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=os.environ["POSTGRES_DB"], user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


@dag(
    dag_id="prescoring",
    start_date=datetime(2026, 11, 1),
    schedule=None,
    catchup=False,
    default_args={"retries": 2},
    tags=["antifraud", "batch-scoring"],
    description="Загрузка выборки → скоринг → финансовые факты → проверенный отчёт Ollama",
)
def prescoring():
    @task
    def create_tables():
        sql = Path("/opt/airflow/dags/sql/tables.sql").read_text(encoding="utf-8")
        with db_connect() as conn:
            conn.execute(sql)

    @task
    def load_holdout():
        """Однократно загружает предоставленный CSV; уже загруженную выборку не дублирует."""
        if not INPUT_CSV.exists():
            raise FileNotFoundError(
                "Положите отложенную выборку преподавателя в data/holdout.csv и повторите запуск DAG."
            )
        with db_connect() as conn:
            existing = conn.execute("SELECT count(*) FROM holdout_transactions").fetchone()[0]
            if existing:
                return existing
        frame = pd.read_csv(INPUT_CSV, low_memory=False)
        required = {"trans_num", "is_fraud", "amt"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"В holdout.csv отсутствуют обязательные колонки: {sorted(missing)}")
        frame["trans_num"] = frame["trans_num"].astype(str)
        if frame["trans_num"].duplicated().any():
            raise ValueError("В holdout.csv колонка trans_num должна быть уникальной")
        frame["is_fraud"] = pd.to_numeric(frame["is_fraud"], errors="raise").astype(int)
        if not frame["is_fraud"].isin([0, 1]).all():
            raise ValueError("Колонка is_fraud должна содержать только 0 или 1")
        frame["amt"] = pd.to_numeric(frame["amt"], errors="raise")
        rows = []
        def json_value(value):
            if pd.isna(value):
                return None
            if hasattr(value, "item"):
                value = value.item()
            return value.isoformat() if hasattr(value, "isoformat") else value

        for record in frame.to_dict(orient="records"):
            clean = {k: json_value(v) for k, v in record.items()}
            rows.append((str(record["trans_num"]), int(record["is_fraud"]), float(record["amt"]), Jsonb(clean)))
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO holdout_transactions(transaction_id,is_fraud,amount,row_data) VALUES (%s,%s,%s,%s)",
                    rows,
                )
        return len(rows)

    @task
    def extract(_loaded: int) -> str:
        with db_connect() as conn:
            rows = conn.execute(
                "SELECT row_data FROM holdout_transactions ORDER BY transaction_id"
            ).fetchall()
        frame = pd.DataFrame([row[0] for row in rows])
        TMP.mkdir(parents=True, exist_ok=True)
        path = TMP / f"{uuid.uuid4().hex}.pkl"
        frame.to_pickle(path)
        return str(path)

    @task
    def score(path: str) -> str:
        sys.path.insert(0, str(PROJECT))
        from score import load_artifacts, score_frame

        frame = pd.read_pickle(path)
        # score_frame сам исключает is_fraud до вызова модели.
        scored = score_frame(frame, load_artifacts(ARTIFACTS), with_reasons=False)
        out_path = path.replace(".pkl", "_scored.pkl")
        scored.to_pickle(out_path)
        return out_path

    @task
    def load(path: str) -> int:
        context = get_current_context()
        run_id = context["run_id"]
        frame = pd.read_pickle(path)
        rows = [
            (str(r.trans_num), float(r.fraud_probability), int(r.decision), MODEL_VERSION, run_id)
            for r in frame.itertuples(index=False)
        ]
        with db_connect() as conn:
            with conn.cursor() as cur:
                # Перезаписываем только версию этой модели: повтор запуска идемпотентен.
                cur.execute("DELETE FROM scored_transactions WHERE model_version = %s", (MODEL_VERSION,))
                cur.executemany(
                    """INSERT INTO scored_transactions
                    (transaction_id,fraud_score,is_fraud_pred,threshold,model_version,run_id)
                    VALUES (%s,%s,%s,NULL,%s,%s)""",
                    rows,
                )
        return len(rows)

    @task
    def summarize(_loaded_count: int) -> str:
        run_id = get_current_context()["run_id"]
        with db_connect() as conn:
            counts = conn.execute(
                """SELECT count(*), count(*) FILTER (WHERE s.is_fraud_pred=1)
                   FROM holdout_transactions h JOIN scored_transactions s USING(transaction_id)
                   WHERE s.model_version=%s AND s.run_id=%s""",
                (MODEL_VERSION, run_id),
            ).fetchone()
            expected = conn.execute("SELECT count(*) FROM holdout_transactions").fetchone()[0]
            if counts[0] != expected:
                raise ValueError(f"Скоринг записал {counts[0]} строк из {expected}")
        return run_id

    @task
    def build_facts(run_id: str) -> dict:
        q = """WITH joined AS (
          SELECT h.is_fraud actual, h.amount, s.is_fraud_pred pred
          FROM holdout_transactions h JOIN scored_transactions s USING(transaction_id)
          WHERE s.model_version=%s AND s.run_id=%s
        ), agg AS (
          SELECT count(*) total,
            count(*) FILTER (WHERE actual=1 AND pred=1) tp,
            coalesce(sum(amount) FILTER (WHERE actual=1 AND pred=1),0) tp_amount,
            count(*) FILTER (WHERE actual=1 AND pred=0) fn,
            coalesce(sum(amount) FILTER (WHERE actual=1 AND pred=0),0) fn_amount,
            count(*) FILTER (WHERE actual=0 AND pred=1) fp,
            coalesce(sum(amount) FILTER (WHERE actual=0 AND pred=1),0) fp_amount,
            count(*) FILTER (WHERE pred=1) flagged,
            coalesce(sum(amount) FILTER (WHERE actual=1),0) all_fraud_amount
          FROM joined
        ) SELECT *, flagged * %s AS review_cost,
          fp_amount * %s AS missed_commission,
          tp_amount - flagged * %s - fp_amount * %s AS net_effect,
          CASE WHEN all_fraud_amount=0 THEN 0 ELSE 100.0*tp_amount/all_fraud_amount END AS coverage
        FROM agg"""
        with db_connect() as conn:
            row = conn.execute(q, (MODEL_VERSION, run_id, ASSUMPTIONS["review_cost"],
                ASSUMPTIONS["commission_rate"], ASSUMPTIONS["review_cost"],
                ASSUMPTIONS["commission_rate"])).fetchone()
            # Имена колонок фиксированы запросом, чтобы JSON фактов был читаемым.
            (total,tp,tp_amount,fn,fn_amount,fp,fp_amount,flagged,all_fraud,review_cost,missed_commission,net_effect,coverage) = row
            facts = {
                "операций": str(total), "срабатываний": str(flagged),
                "предотвращённые потери": f"{tp} операций на сумму {tp_amount:.2f} {ASSUMPTIONS['currency']}",
                "понесённые потери": f"{fn} операций на сумму {fn_amount:.2f} {ASSUMPTIONS['currency']}",
                "покрытие мошенничества": f"{coverage:.2f}%",
                "ложные блокировки": f"{fp} операций на сумму {fp_amount:.2f} {ASSUMPTIONS['currency']}",
                "операционные затраты": f"{review_cost:.2f} {ASSUMPTIONS['currency']}",
                "упущенный комиссионный доход": f"{missed_commission:.2f} {ASSUMPTIONS['currency']}",
                "чистый эффект": f"{net_effect:.2f} {ASSUMPTIONS['currency']}",
                "допущения": f"проверка {ASSUMPTIONS['review_cost']:.2f} {ASSUMPTIONS['currency']}; комиссия {ASSUMPTIONS['commission_rate']:.3%}",
            }
            conn.execute(
                """INSERT INTO prescoring_runs
                (run_id,row_count,flagged_count,prevented_count,prevented_amount,missed_count,missed_amount,
                 false_positive_count,false_positive_amount,review_cost,missed_commission,net_effect,fraud_coverage_pct)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(run_id) DO UPDATE SET row_count=excluded.row_count,flagged_count=excluded.flagged_count,
                prevented_count=excluded.prevented_count,prevented_amount=excluded.prevented_amount,
                missed_count=excluded.missed_count,missed_amount=excluded.missed_amount,
                false_positive_count=excluded.false_positive_count,false_positive_amount=excluded.false_positive_amount,
                review_cost=excluded.review_cost,missed_commission=excluded.missed_commission,
                net_effect=excluded.net_effect,fraud_coverage_pct=excluded.fraud_coverage_pct""",
                (run_id,total,flagged,tp,tp_amount,fn,fn_amount,fp,fp_amount,review_cost,missed_commission,net_effect,coverage),
            )
        return facts

    @task
    def generate_report(facts: dict) -> str:
        prompt = (
            "Ты финансовый аналитик банка. Напиши руководителю резюме прескоринга на 5–7 предложений. "
            "Используй только числа и факты из JSON без изменений. Не считай, не округляй и не добавляй числа. "
            "Укажи предотвращённые и понесённые потери, ложные блокировки, затраты, чистый эффект и вопрос для обсуждения.\n"
            "ФАКТЫ:\n" + json.dumps(facts, ensure_ascii=False, indent=2)
        )
        response = requests.post(
            f"{os.environ['OLLAMA_URL']}/api/generate",
            json={"model":os.environ["LLM_MODEL"],"prompt":prompt,"stream":False,
                  "options":{"temperature":0.2}}, timeout=600,
        )
        response.raise_for_status()
        return response.json()["response"].strip()

    @task
    def check_report(facts: dict, report: str) -> bool:
        def numbers(value: str) -> set[str]:
            found = re.findall(r"\d{1,3}(?:[ \u00a0]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?", value)
            return {re.sub(r"[ \u00a0]", "", n).replace(",", ".") for n in found}

        allowed = set().union(*(numbers(str(v)) for v in facts.values()))
        unexpected = sorted(numbers(report) - allowed)
        passed = not unexpected
        run_id = get_current_context()["run_id"]
        with db_connect() as conn:
            conn.execute(
                """INSERT INTO business_reports(run_id,llm_model,facts,report_text,check_passed,unexpected_numbers)
                   VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(run_id) DO UPDATE SET
                   created_at=now(),llm_model=excluded.llm_model,facts=excluded.facts,
                   report_text=excluded.report_text,check_passed=excluded.check_passed,
                   unexpected_numbers=excluded.unexpected_numbers""",
                (run_id,os.environ["LLM_MODEL"],Jsonb(facts),report,passed,Jsonb(unexpected)),
            )
        if not passed:
            raise ValueError(f"В отчёте обнаружены числа, которых нет во входных фактах: {unexpected}")
        return passed

    tables = create_tables()
    loaded = load_holdout()
    tables >> loaded
    path = extract(loaded)
    scored_path = score(path)
    count = load(scored_path)
    run = summarize(count)
    facts = build_facts(run)
    report = generate_report(facts)
    check_report(facts, report)


prescoring()
