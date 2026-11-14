@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Zapusk DAG prescoring i ozhidanie rezultata (to zhe, chto knopka v Airflow) ===
docker compose exec airflow python /opt/airflow/tools/run_dag.py
echo.
echo === Poslednii otchet (business_reports) ===
docker compose exec -T db psql -U antifraud -d antifraud -x -c "SELECT run_id, llm_model, check_passed, attempts, report_text FROM business_reports ORDER BY created_at DESC LIMIT 1"
echo === Zapis o zapuske (prescoring_runs) ===
docker compose exec -T db psql -U antifraud -d antifraud -x -c "SELECT run_id, rows_holdout, rows_scored, flagged, tp_count, tp_sum, fn_count, fn_sum, fp_count, fp_sum, review_cost_total, lost_commission, net_effect, coverage_pct, assumptions, report_check_passed FROM prescoring_runs ORDER BY started_at DESC LIMIT 1"
if not exist reports\week6 mkdir reports\week6
docker compose exec -T db psql -U antifraud -d antifraud -x -c "SELECT * FROM business_reports ORDER BY created_at DESC LIMIT 1" > reports\week6\last_report.txt
docker compose exec -T db psql -U antifraud -d antifraud -x -c "SELECT * FROM prescoring_runs ORDER BY started_at DESC LIMIT 1" > reports\week6\last_run.txt
echo Sohraneno: reports\week6\last_report.txt, reports\week6\last_run.txt
pause
