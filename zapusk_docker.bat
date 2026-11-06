@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Antifraud (nedelya 5): zapusk v Docker s PostgreSQL ===
docker version >/dev/null 2>&1 || (echo Docker ne zapushen: otkroite Docker Desktop i podozhdite "Engine running". & pause & exit /b 1)
if not exist .env (
  copy .env.example .env >nul
  echo Sozdan fail .env iz .env.example - parol mozhno pomenyat v .env
)
if not exist backups mkdir backups
if not exist data\cache\service_history.parquet (
  echo === 1/3 Podgotovka dannyh ===
  docker compose --profile prepare run --rm prepare
)
echo === 2/3 Sborka i zapusk ===
docker compose up -d --build
echo === 3/3 Status konteinerov ===
docker compose ps
echo.
echo Servis:    http://localhost:8000/docs
echo Interfeis: http://localhost:8501
echo Panel:     http://localhost:8502
echo Adminer:   http://localhost:8080  (sistema PostgreSQL, server db, polzovatel i parol iz .env, baza antifraud)
echo Ostanovit: docker compose down   (dannye sohranyatsya)
pause
