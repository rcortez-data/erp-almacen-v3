@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue) { exit 10 }"
if errorlevel 10 (
    echo ERP V3 ya esta funcionando en http://127.0.0.1:5000
    start "" "http://127.0.0.1:5000"
    timeout /t 3 /nobreak >nul
    exit /b 0
)

rem WScript inicia PowerShell sin crear una terminal visible y sin depender de esta ventana.
wscript.exe "%~dp0INICIAR_ERP_OCULTO.vbs"
timeout /t 5 /nobreak >nul

powershell.exe -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue)) { exit 1 }"
if errorlevel 1 (
    echo No se pudo iniciar ERP V3. Revisa logs\erp_almacen.log
    pause
    exit /b 1
)

echo ERP V3 iniciado correctamente.
start "" "http://127.0.0.1:5000"
timeout /t 2 /nobreak >nul
