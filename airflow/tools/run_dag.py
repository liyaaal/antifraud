"""Запуск DAG prescoring из командной строки и ожидание результата (для bat-файлов и проверки).

docker compose exec airflow python /opt/airflow/tools/run_dag.py
Печатает состояние каждой задачи и итог. То же самое можно сделать кнопкой ▶ в веб-интерфейсе.
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone

run_id = "manual__" + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
subprocess.run(["airflow", "dags", "unpause", "prescoring"], check=False, capture_output=True)
subprocess.run(["airflow", "dags", "trigger", "prescoring", "-r", run_id], check=True, capture_output=True)
print(f"Запущен DAG prescoring, run_id = {run_id}", flush=True)
seen, t0 = {}, time.time()
while True:
    time.sleep(10)
    out = subprocess.run(["airflow", "tasks", "states-for-dag-run", "prescoring", run_id, "-o", "json"],
                         capture_output=True, text=True).stdout
    try:
        states = {r["task_id"]: r["state"] for r in json.loads(out[out.index("["):])}
    except ValueError:
        continue
    for k, v in states.items():
        if seen.get(k) != v and v:
            print(f"  {time.time() - t0:5.0f} c  {k:16s} {v}", flush=True)
            seen[k] = v
    if states and all(v in ("success", "failed", "upstream_failed", "skipped") for v in states.values()):
        break
ok = all(v == "success" for v in states.values())
print("ИТОГ:", "все задачи выполнены успешно" if ok else f"есть ошибки: {states}")
sys.exit(0 if ok else 1)
