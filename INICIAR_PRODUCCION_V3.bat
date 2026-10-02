@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue) { exit 10 }"
if errorlevel 10 (
    echo ERP V3 ya esta funcionando en http://127.0.0.1:5000
    start "" "http://127.0.0.1:5000"
    timeout /t 3 /nobreak >nul 2>nul
    exit /b 0
)

rem Arranca por Programador de tareas para que NO dependa de Codex, ChatGPT,
rem VS Code ni de esta ventana. Si la tarea no existe o no tiene permisos,
rem usa WMI como arranque independiente.
schtasks /Query /TN "ERP Almacen V3 Produccion" >nul 2>nul
if errorlevel 1 (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0REGISTRAR_TAREA_PRODUCCION_V3.ps1" >nul 2>nul
)

schtasks /Run /TN "ERP Almacen V3 Produccion" >nul 2>nul
if errorlevel 1 (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0ARRANCAR_PRODUCCION_INDEPENDIENTE.ps1"
)

rem Espera hasta 20 segundos porque a veces Python tarda en cargar el ERP.
for /L %%I in (1,1,20) do (
    powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>nul
    if not errorlevel 1 goto iniciado
    timeout /t 1 /nobreak >nul 2>nul
)

:iniciado
powershell.exe -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue)) { exit 1 }" >nul 2>nul
if errorlevel 1 (
    echo No se pudo iniciar ERP V3. Revisa logs\erp_almacen.log
    pause
    exit /b 1
)

echo ERP V3 iniciado correctamente.
start "" "http://127.0.0.1:5000"
timeout /t 2 /nobreak >nul 2>nul
