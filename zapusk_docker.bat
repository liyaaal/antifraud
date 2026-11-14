@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Antifraud (nedelya 6): Docker + PostgreSQL + Airflow + Ollama ===
docker version >nul 2>&1 || (echo Docker ne zapushen: otkroite Docker Desktop i podozhdite "Engine running". & pause & exit /b 1)
if not exist .env (
  copy .env.example .env >nul
  echo Sozdan fail .env iz .env.example - paroli mozhno pomenyat v .env
)
set "LLM_MODEL=qwen2.5:3b"
for /f "tokens=1,* delims==" %%a in ('findstr /b "LLM_MODEL=" .env') do set "LLM_MODEL=%%b"
if not exist backups mkdir backups
if not exist data\cache\service_history.parquet (
  echo === 1/4 Podgotovka dannyh ===
  docker compose --profile prepare run --rm prepare
)
echo === 2/4 Sborka i zapusk (pervyi raz 10-20 minut: skachivayutsya Airflow i Ollama) ===
docker compose up -d --build
echo === 3/4 Model dlya otcheta: %LLM_MODEL% (pervyi raz ~2 GB) ===
docker compose exec ollama ollama pull %LLM_MODEL%
echo === 4/4 Status konteinerov ===
docker compose ps
echo.
echo Servis:    http://localhost:8000/docs
echo Interfeis: http://localhost:8501
echo Panel:     http://localhost:8502   (vnizu - poslednii otchet preskoringa)
echo Airflow:   http://localhost:8083   (polzovatel admin, parol AIRFLOW_ADMIN_PASSWORD iz .env, po umolchaniyu admin)
echo Adminer:   http://localhost:8081   (PostgreSQL, server db, polzovatel i parol iz .env, baza antifraud)
echo Zapustit DAG bez brauzera: zapusk_dag.bat
echo Ostanovit: docker compose down   (dannye sohranyatsya)
pause
