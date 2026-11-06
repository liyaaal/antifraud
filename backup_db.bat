@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist backups mkdir backups
echo === Rezervnaya kopiya bazy -^> backups\antifraud.dump ===
docker compose exec db pg_dump -U antifraud -d antifraud -Fc -f /backups/antifraud.dump && echo Gotovo: backups\antifraud.dump
pause
