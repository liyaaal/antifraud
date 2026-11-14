"""Анализ работы языковой модели (неделя 6): доля отчётов, прошедших проверку чисел с первой попытки.

docker compose exec airflow python /opt/airflow/tools/llm_eval.py --n 10 [--model qwen2.5:1.5b]

Берёт факты последнего запуска DAG (prescoring_runs.facts), N раз генерирует отчёт одним и тем же промптом
с разными seed (temperature 0.2), проверяет числа и пишет сводку в data/llm_eval_<модель>.md.
"""
import argparse
import collections
import json
import os
import sys
import time

import requests
from airflow.providers.postgres.hooks.postgres import PostgresHook

sys.path.insert(0, "/opt/airflow/dags")
import report_lib as rl  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=10)
ap.add_argument("--model", default=os.environ.get("LLM_MODEL", "qwen2.5:3b"))
a = ap.parse_args()

row = PostgresHook(postgres_conn_id="antifraud_db").get_first(
    "SELECT run_id, facts FROM prescoring_runs WHERE facts IS NOT NULL ORDER BY started_at DESC LIMIT 1")
if not row:
    sys.exit("Нет фактов: сначала запустите DAG prescoring")
run_id, facts = row[0], row[1] if isinstance(row[1], dict) else json.loads(row[1])
url = os.environ.get("OLLAMA_URL", "http://ollama:11434")
results, extras = [], collections.Counter()
for i in range(a.n):
    t0 = time.time()
    r = requests.post(f"{url}/api/generate", json={"model": a.model, "prompt": rl.make_prompt(facts), "stream": False,
                                                   "options": {"temperature": 0.2, "seed": 100 + i}}, timeout=900)
    r.raise_for_status()
    text = r.json()["response"].strip()
    ok, extra = rl.check_report(text, facts)
    extras.update(extra)
    results.append((ok, sorted(extra), round(time.time() - t0, 1), text))
    print(f"{i + 1}/{a.n}: {'OK ' if ok else 'НЕТ'} {time.time() - t0:5.1f} c  {sorted(extra) if extra else ''}", flush=True)

passed = sum(r[0] for r in results)
lines = [f"# Анализ LLM: {a.model}", "",
         f"Факты запуска `{run_id}`; {a.n} генераций одним промптом, temperature 0.2, seed 100…{99 + a.n}.", "",
         f"**С первой попытки проверку прошли {passed} из {a.n} ({100 * passed / a.n:.0f}%).** "
         f"Среднее время генерации {sum(r[2] for r in results) / a.n:.0f} с.", "",
         "Числа не из фактов (сколько раз встретились): " +
         (", ".join(f"`{k}` × {v}" for k, v in extras.most_common()) if extras else "нет"), ""]
for i, (ok, extra, sec, text) in enumerate(results, 1):
    lines += [f"## {i}. {'прошёл' if ok else 'не прошёл: ' + ', '.join(extra)} · {sec} с", "", text, ""]
out = f"/opt/airflow/data/llm_eval_{a.model.replace(':', '_')}.md"
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"Итог: {passed}/{a.n} с первой попытки -> {out}")
