@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root=(Resolve-Path '%~dp0').Path.TrimEnd('\');" ^
  "$listener=Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1;" ^
  "if(-not $listener){exit 0};" ^
  "$process=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $listener.OwningProcess);" ^
  "$cmd=[string]$process.CommandLine;" ^
  "$esWaitress=($cmd -like '*waitress*' -and $cmd -like '*wsgi:application*' -and $cmd -like '*5000*');" ^
  "$esAppPy=($cmd -like '*app.py*');" ^
  "$esERP=($cmd -like ('*' + $root + '*') -and ($esWaitress -or $esAppPy));" ^
  "if($esERP){exit 10};" ^
  "Write-Host 'Seguridad: el puerto 5000 pertenece a otro programa.';" ^
  "Write-Host $cmd;" ^
  "exit 2"
if errorlevel 10 (
    echo ERP V3 ya esta funcionando en http://127.0.0.1:5000
    start "" "http://127.0.0.1:5000"
    powershell.exe -NoProfile -Command "Start-Sleep -Seconds 3"
    exit /b 0
)
if errorlevel 2 (
    pause
    exit /b 2
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
    powershell.exe -NoProfile -Command "Start-Sleep -Seconds 1"
)

:iniciado
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root=(Resolve-Path '%~dp0').Path.TrimEnd('\');" ^
  "$listener=Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1;" ^
  "if(-not $listener){exit 1};" ^
  "$process=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $listener.OwningProcess);" ^
  "$cmd=[string]$process.CommandLine;" ^
  "$esERP=($cmd -like ('*' + $root + '*') -and (($cmd -like '*waitress*' -and $cmd -like '*wsgi:application*') -or $cmd -like '*app.py*'));" ^
  "if($esERP){exit 0}else{Write-Host 'El puerto 5000 fue ocupado por otro proceso.'; Write-Host $cmd; exit 2}"
if errorlevel 2 (
    pause
    exit /b 2
)
if errorlevel 1 (
    echo No se pudo iniciar ERP V3. Revisa logs\erp_almacen.log
    pause
    exit /b 1
)

echo ERP V3 iniciado correctamente.
start "" "http://127.0.0.1:5000"
powershell.exe -NoProfile -Command "Start-Sleep -Seconds 2"
