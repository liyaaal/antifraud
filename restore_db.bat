@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Vosstanovlenie bazy iz backups\antifraud.dump (tekushchie dannye budut zameneny) ===
docker compose exec db pg_restore -U antifraud -d antifraud --clean --if-exists /backups/antifraud.dump && echo Gotovo
pause
