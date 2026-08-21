@echo off
setlocal
cd /d "%~dp0"
python scripts\backup_sqlite.py --retention 1
if errorlevel 1 exit /b 1
