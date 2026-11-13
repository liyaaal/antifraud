"""DAG prescoring (неделя 6): пакетный скоринг отложенной выборки и бизнес-отчёт.

create_tables → load_holdout → extract → score → load → summarize → build_facts → generate_report → check_report
└──────────────── часть 1: прескоринг ────────────────┘   └────────── часть 2: бизнес-отчёт ──────────┘

Правила:
- через XCom передаются только пути к временным файлам и счётчики — не таблицы;
- is_fraud отбрасывается до скоринга (утечка целевой переменной), используется только в build_facts;
- идемпотентность: load удаляет прежние оценки этой версии модели перед записью, все записи по run_id —
  через ON CONFLICT, поэтому повторный запуск и перезапуск отдельной задачи (Clear) не дают дубликатов;
- все числа считает код (SQL + Python), языковая модель только излагает готовые значения.
"""
import csv
import json
import os
import re
import time
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.operators.python import get_current_context
from airflow.providers.postgres.hooks.postgres import PostgresHook

import report_lib as rl

DAGS_DIR = os.path.dirname(os.path.abspath(__file__))
TMP = "/tmp/prescoring"                          # временные файлы внутри контейнера, не в XCom
MODEL_DIR = os.environ.get("MODEL_DIR", "/opt/airflow/model")  # score.py, src/, artifacts/ (тома из проекта)
MODEL_PYTHON = os.environ.get("MODEL_PYTHON", "/opt/airflow/model-venv/bin/python")  # отдельное окружение модели: Python 3.13 и версии обучения
HISTORY_FILE = os.environ.get("HISTORY_FILE", "/opt/airflow/data/cache/service_history.parquet")  # история карт до выборки
HOLDOUT_FILE = os.environ.get("HOLDOUT_FILE", "/opt/airflow/data/holdout.csv")
VERSIONS = {"v2": "final_v2", "v1": "final"}     # версия модели → папка артефактов

# Колонки датасета в таблице holdout_transactions (порядок не важен: загрузка идёт по именам колонок).
DATASET_COLS = ["trans_date_trans_time", "cc_num", "merchant", "category", "amt", "first", "last", "gender",
                "street", "city", "state", "zip", "lat", "long", "city_pop", "job", "dob", "trans_num",
                "unix_time", "merch_lat", "merch_long"]


def db() -> PostgresHook:
    return PostgresHook(postgres_conn_id="antifraud_db")   # Connection из AIRFLOW_CONN_ANTIFRAUD_DB


def params() -> dict:
    """Параметры запуска. Значения по умолчанию — в коде; переопределяются в Admin → Variables."""
    return {
        "model_version": Variable.get("model_version", default_var="v2"),
        "compare_model": Variable.get("compare_model", default_var="v1"),   # "" — без сравнения
        "threshold": float(Variable.get("threshold", default_var=0.5)),     # рабочая точка недели 2
        "llm_model": Variable.get("llm_model", default_var=os.environ.get("LLM_MODEL", "qwen2.5:3b")),
        "llm_attempts": int(Variable.get("llm_attempts", default_var=3)),
        "assumptions": {
            "currency": rl.ASSUMPTIONS["currency"],
            "review_cost": float(Variable.get("review_cost", default_var=rl.ASSUMPTIONS["review_cost"])),
            "commission_rate": float(Variable.get("commission_rate", default_var=rl.ASSUMPTIONS["commission_rate"])),
        },
    }


def run_dir() -> str:
    run_id = get_current_context()["run_id"]
    d = os.path.join(TMP, re.sub(r"[^A-Za-z0-9_.-]", "_", run_id))
    os.makedirs(d, exist_ok=True)
    return d


def read_facts(path: str) -> dict:
    """Факты из временного файла; если файла уже нет (контейнер перезапускали) — из prescoring_runs."""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    run_id = get_current_context()["run_id"]
    row = db().get_first("SELECT facts FROM prescoring_runs WHERE run_id = %s", parameters=(run_id,))
    if not row or row[0] is None:
        raise FileNotFoundError(f"нет фактов для {run_id}: перезапустите build_facts")
    return row[0] if isinstance(row[0], dict) else json.loads(row[0])


def copy_out(sql: str, path: str):
    conn = db().get_conn()
    with open(path, "w", encoding="utf-8", newline="") as f, conn.cursor() as cur:
        cur.copy_expert(f"COPY ({sql}) TO STDOUT WITH CSV HEADER", f)
    conn.close()


@dag(dag_id="prescoring", start_date=datetime(2026, 11, 1), schedule=None, catchup=False,
     default_args={"retries": 2, "retry_delay": timedelta(seconds=20)},
     tags=["antifraud", "week6"], doc_md=__doc__)
def prescoring():

    @task
    def create_tables():
        with open(os.path.join(DAGS_DIR, "sql", "tables.sql"), encoding="utf-8") as f:
            db().run(f.read())

    @task
    def load_holdout() -> int:
        """Загружает data/holdout.csv в holdout_transactions, если таблица пуста. Повторно ничего не грузит."""
        hook = db()
        n = hook.get_first("SELECT count(*) FROM holdout_transactions")[0]
        if n:
            print(f"holdout_transactions уже загружена: {n} строк — пропускаю загрузку")
            return int(n)
        with open(HOLDOUT_FILE, encoding="utf-8") as f:
            header = next(csv.reader(f))
        cols = [c for c in DATASET_COLS + ["is_fraud"] if c in header]
        missing = sorted(set(DATASET_COLS + ["is_fraud"]) - set(cols))
        if missing:
            raise ValueError(f"в {HOLDOUT_FILE} нет колонок {missing}")
        # Лишние колонки файла (например, индекс «Unnamed: 0») отбрасываем: COPY грузит только нужные по именам.
        tmp = os.path.join(run_dir(), "holdout_clean.csv")
        with open(HOLDOUT_FILE, encoding="utf-8") as src, open(tmp, "w", encoding="utf-8", newline="") as dst:
            r, w = csv.DictReader(src), csv.writer(dst)
            w.writerow(cols)
            for row in r:
                w.writerow([row[c] for c in cols])
        conn = hook.get_conn()
        with open(tmp, encoding="utf-8") as f, conn.cursor() as cur:
            cur.copy_expert(f"COPY holdout_transactions ({', '.join(cols)}) FROM STDIN WITH CSV HEADER", f)
        conn.commit()
        conn.close()
        n = hook.get_first("SELECT count(*) FROM holdout_transactions")[0]
        print(f"Загружено в holdout_transactions: {n} строк из {HOLDOUT_FILE}")
        return int(n)

    @task
    def extract() -> dict:
        """Выгружает выборку во временный CSV; дальше по XCom идут только путь к файлу и параметры запуска."""
        p = params()
        path = os.path.join(run_dir(), "holdout.csv")
        copy_out(f"SELECT {', '.join(DATASET_COLS)}, is_fraud FROM holdout_transactions "
                 f"ORDER BY trans_date_trans_time, trans_num", path)
        versions = [[p["model_version"], VERSIONS[p["model_version"]]]]
        if p["compare_model"] and p["compare_model"] != p["model_version"]:
            versions.append([p["compare_model"], VERSIONS[p["compare_model"]]])
        print(f"Выгружено во временный файл: {path}; версии модели: {versions}, порог {p['threshold']}")
        return {"path": path, "versions": versions, "threshold": p["threshold"], "model_dir": MODEL_DIR, "history": HISTORY_FILE,
                "run_id": get_current_context()["run_id"]}

    @task.external_python(python=MODEL_PYTHON, expect_airflow=False)
    def score(job: dict) -> str:
        """Выполняется в окружении модели (Python 3.13, версии библиотек как при обучении): функция score_df
        из score.py — та же реализация признаков, что в пакетном скоринге и в онлайн-сервисе."""
        import sys
        import time

        import pandas as pd

        path, versions, threshold, run_id = job["path"], job["versions"], job["threshold"], job["run_id"]
        sys.path.insert(0, job["model_dir"])
        from score import score_df
        from src.data import READ_DTYPES

        df = pd.read_csv(path, dtype=READ_DTYPES, low_memory=False)
        X = df.drop(columns=["is_fraud"])            # утечка целевой переменной исключена до скоринга
        print(f"Операций: {len(X)}; колонка is_fraud удалена до скоринга: {'is_fraud' not in X.columns}")
        parts = []
        for version, folder in versions:
            t0 = time.time()
            out = score_df(X, artifacts=f"{job['model_dir']}/artifacts/{folder}", history=job["history"])
            out["model_version"] = version
            out["is_fraud_pred"] = (out["fraud_score"] >= threshold).astype(int)
            out["threshold"] = threshold
            out["run_id"] = run_id
            parts.append(out)
            print(f"Модель {version}: {len(out)} оценок, срабатываний {int(out['is_fraud_pred'].sum())}, "
                  f"{time.time() - t0:.0f} c")
        res = pd.concat(parts, ignore_index=True)
        out_path = path.replace(".csv", "_scored.csv")
        res[["transaction_id", "model_version", "fraud_score", "is_fraud_pred", "threshold", "run_id"]] \
            .to_csv(out_path, index=False)
        return out_path

    @task
    def load(path: str) -> int:
        """Идемпотентная запись: в одной транзакции удаляем оценки этих версий и записываем новые."""
        with open(path, encoding="utf-8") as f:
            r = csv.reader(f)
            next(r)
            versions = sorted({row[1] for row in r})
        conn = db().get_conn()
        with conn.cursor() as cur, open(path, encoding="utf-8") as f:
            cur.execute("DELETE FROM scored_transactions WHERE model_version = ANY(%s)", (versions,))
            print(f"Удалены прежние оценки версий {versions}: {cur.rowcount} строк")
            # COPY вместо insert_rows: быстрее и без ошибки numpy.int64 — значения идут текстом из CSV
            cur.copy_expert("COPY scored_transactions (transaction_id, model_version, fraud_score, is_fraud_pred, "
                            "threshold, run_id) FROM STDIN WITH CSV HEADER", f)
            n = cur.rowcount
        conn.commit()
        conn.close()
        print(f"Записано в scored_transactions: {n} строк")
        return int(n)

    @task
    def summarize(n_loaded: int) -> dict:
        """Сверка объёма и запись о запуске в prescoring_runs."""
        p = params()
        run_id = get_current_context()["run_id"]
        hook = db()
        rows_holdout, period_from, period_to = hook.get_first(
            "SELECT count(*), min(trans_date_trans_time), max(trans_date_trans_time) FROM holdout_transactions")
        rows_scored, flagged = hook.get_first(
            "SELECT count(*), coalesce(sum(is_fraud_pred), 0) FROM scored_transactions WHERE model_version = %s",
            parameters=(p["model_version"],))
        if rows_scored != rows_holdout:
            raise ValueError(f"оценено {rows_scored} строк, а в выборке {rows_holdout}")
        hook.run("""
            INSERT INTO prescoring_runs (run_id, model_version, threshold, period_from, period_to,
                                         rows_holdout, rows_scored, flagged, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'scored')
            ON CONFLICT (run_id) DO UPDATE SET model_version = EXCLUDED.model_version,
                threshold = EXCLUDED.threshold, period_from = EXCLUDED.period_from, period_to = EXCLUDED.period_to,
                rows_holdout = EXCLUDED.rows_holdout, rows_scored = EXCLUDED.rows_scored,
                flagged = EXCLUDED.flagged, status = 'scored'""",
                 parameters=(run_id, p["model_version"], p["threshold"], period_from, period_to,
                             rows_holdout, rows_scored, flagged))
        print(f"Выборка {rows_holdout} строк = оценено {rows_scored}; срабатываний {flagged}")
        return {"rows": int(rows_scored), "flagged": int(flagged)}

    @task
    def build_facts(_summary: dict) -> str:
        """Финансовые показатели: агрегаты — SQL-запросом, формулы — Python, допущения — из Variables."""
        p, a = params(), params()["assumptions"]
        run_id = get_current_context()["run_id"]
        hook = db()
        sql = """
            SELECT count(*)                                                        AS ops,
                   count(*) FILTER (WHERE s.is_fraud_pred = 1)                     AS flagged,
                   count(*) FILTER (WHERE s.is_fraud_pred = 1 AND h.is_fraud = 1)  AS tp,
                   coalesce(sum(h.amt) FILTER (WHERE s.is_fraud_pred = 1 AND h.is_fraud = 1), 0) AS tp_sum,
                   count(*) FILTER (WHERE s.is_fraud_pred = 0 AND h.is_fraud = 1)  AS fn,
                   coalesce(sum(h.amt) FILTER (WHERE s.is_fraud_pred = 0 AND h.is_fraud = 1), 0) AS fn_sum,
                   count(*) FILTER (WHERE s.is_fraud_pred = 1 AND h.is_fraud = 0)  AS fp,
                   coalesce(sum(h.amt) FILTER (WHERE s.is_fraud_pred = 1 AND h.is_fraud = 0), 0) AS fp_sum,
                   coalesce(sum(h.amt) FILTER (WHERE h.is_fraud = 1), 0)           AS fraud_sum,
                   min(h.trans_date_trans_time) AS period_from, max(h.trans_date_trans_time) AS period_to
            FROM holdout_transactions h
            JOIN scored_transactions s ON s.transaction_id = h.transaction_id
            WHERE s.model_version = %s"""
        names = ["ops", "flagged", "tp", "tp_sum", "fn", "fn_sum", "fp", "fp_sum", "fraud_sum",
                 "period_from", "period_to"]
        agg = dict(zip(names, hook.get_first(sql, parameters=(p["model_version"],))))
        fin = rl.compute_finance(agg, a)
        compare = None
        if p["compare_model"] and p["compare_model"] != p["model_version"]:
            cagg = dict(zip(names, hook.get_first(sql, parameters=(p["compare_model"],))))
            if cagg["ops"]:
                cfin = rl.compute_finance(cagg, a)
                compare = {"model_version": p["compare_model"], "tp": cagg["tp"], "tp_sum": float(cagg["tp_sum"]),
                           "fp": cagg["fp"], "fn": cagg["fn"], **cfin}
        facts = rl.build_facts(agg, fin, a, compare)
        hook.run("""
            UPDATE prescoring_runs SET tp_count = %s, tp_sum = %s, fn_count = %s, fn_sum = %s, fp_count = %s,
                   fp_sum = %s, fraud_sum = %s, review_cost_total = %s, lost_commission = %s, net_effect = %s,
                   coverage_pct = %s, assumptions = %s, compare = %s, facts = %s, status = 'facts'
            WHERE run_id = %s""",
                 parameters=(agg["tp"], agg["tp_sum"], agg["fn"], agg["fn_sum"], agg["fp"], agg["fp_sum"],
                             agg["fraud_sum"], fin["review_cost_total"], fin["lost_commission"],
                             fin["net_effect"], fin["coverage_pct"], json.dumps(a),
                             json.dumps(compare) if compare else None,
                             json.dumps(facts, ensure_ascii=False), run_id))
        path = os.path.join(run_dir(), "facts.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(facts, f, ensure_ascii=False, indent=2)
        print("Допущения:", json.dumps(a, ensure_ascii=False))
        print("ФАКТЫ:\n" + json.dumps(facts, ensure_ascii=False, indent=2))
        return path

    @task
    def generate_report(facts_path: str) -> str:
        """Промпт → Ollama. Если в тексте есть число не из фактов — ещё попытка с подсказкой (до llm_attempts).
        Каждая попытка записывается в llm_attempts. Нет связи с Ollama → задача падает и повторяется (retries)."""
        import requests

        p = params()
        run_id = get_current_context()["run_id"]
        facts = read_facts(facts_path)
        url = os.environ.get("OLLAMA_URL", "http://ollama:11434")
        hook = db()
        hook.run("DELETE FROM llm_attempts WHERE run_id = %s", parameters=(run_id,))

        def ask(prompt: str) -> str:
            body = {"model": p["llm_model"], "prompt": prompt, "stream": False,
                    "options": {"temperature": 0.2, "seed": 42}}
            r = requests.post(f"{url}/api/generate", json=body, timeout=900)
            if r.status_code == 404:              # модель ещё не скачана в контейнер ollama — скачиваем один раз
                print(f"Модель {p['llm_model']} не найдена в Ollama — загружаю (однократно, несколько минут)")
                requests.post(f"{url}/api/pull", json={"model": p["llm_model"], "stream": False},
                              timeout=3600).raise_for_status()
                r = requests.post(f"{url}/api/generate", json=body, timeout=900)
            r.raise_for_status()
            return r.json()["response"].strip()

        extra, text, passed = None, "", False
        for attempt in range(1, p["llm_attempts"] + 1):
            t0 = time.time()
            text = ask(rl.make_prompt(facts, extra))
            passed, extra = rl.check_report(text, facts)
            hook.run("INSERT INTO llm_attempts (run_id, attempt, llm_model, passed, extra_numbers, seconds, "
                     "report_text) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                     parameters=(run_id, attempt, p["llm_model"], passed, sorted(extra),
                                 round(time.time() - t0, 1), text))
            print(f"Попытка {attempt}: {time.time() - t0:.0f} c, проверка {'пройдена' if passed else 'НЕ пройдена'}"
                  + ("" if passed else f", лишние числа: {sorted(extra)}"))
            if passed:
                break
        path = os.path.join(run_dir(), "report.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"text": text, "attempts": attempt, "llm_model": p["llm_model"]}, f, ensure_ascii=False)
        print("ОТЧЁТ:\n" + text)
        return path

    @task
    def check_report(report_path: str, facts_path: str) -> bool:
        """Итоговая проверка чисел и сохранение отчёта. Отчёт сохраняется в любом случае."""
        run_id = get_current_context()["run_id"]
        with open(report_path, encoding="utf-8") as f:
            rep = json.load(f)
        facts = read_facts(facts_path)
        passed, extra = rl.check_report(rep["text"], facts)
        hook = db()
        hook.run("""
            INSERT INTO business_reports (run_id, llm_model, facts, report_text, check_passed, extra_numbers, attempts)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO UPDATE SET created_at = now(), llm_model = EXCLUDED.llm_model,
                facts = EXCLUDED.facts, report_text = EXCLUDED.report_text, check_passed = EXCLUDED.check_passed,
                extra_numbers = EXCLUDED.extra_numbers, attempts = EXCLUDED.attempts""",
                 parameters=(run_id, rep["llm_model"], json.dumps(facts, ensure_ascii=False), rep["text"],
                             passed, sorted(extra), rep["attempts"]))
        hook.run("UPDATE prescoring_runs SET report_check_passed = %s, finished_at = now(), status = 'done' "
                 "WHERE run_id = %s", parameters=(passed, run_id))
        print(f"Проверка чисел: {'пройдена' if passed else 'НЕ пройдена'}"
              + ("" if passed else f"; числа не из фактов: {sorted(extra)}"))
        return passed

    tables = create_tables()
    holdout = load_holdout()
    job = extract()
    tables >> holdout >> job
    scored = score(job)
    facts = build_facts(summarize(load(scored)))
    check_report(generate_report(facts), facts)


prescoring()
