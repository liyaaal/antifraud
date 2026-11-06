@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === psql vnutri konteinera db. Vyhod: \q ===
echo Primer: SELECT count(*) FROM transactions;
docker compose exec db psql -U antifraud -d antifraud
pause
