@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "LLM_MODEL=qwen2.5:3b"
for /f "tokens=1,* delims==" %%a in ('findstr /b "LLM_MODEL=" .env') do set "LLM_MODEL=%%b"
echo === Analiz LLM: 10 generacii otcheta po faktam poslednego zapuska, model %LLM_MODEL% ===
docker compose exec airflow python /opt/airflow/tools/llm_eval.py --n 10 --model %LLM_MODEL%
echo Rezultat: papka data, fail llm_eval_*.md
pause
