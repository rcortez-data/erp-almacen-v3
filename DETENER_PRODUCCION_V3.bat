@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root=(Resolve-Path '%~dp0').Path.TrimEnd('\');" ^
  "$listener=Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1;" ^
  "if(-not $listener){Write-Host 'ERP V3 ya estaba detenido.'; exit 0};" ^
  "$process=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $listener.OwningProcess);" ^
  "$cmd=[string]$process.CommandLine;" ^
  "$esWaitress=($cmd -like '*waitress*' -and $cmd -like '*wsgi:application*' -and $cmd -like '*5000*');" ^
  "$esAppPy=($cmd -like '*app.py*');" ^
  "$esERP=($cmd -like ('*' + $root + '*') -and ($esWaitress -or $esAppPy));" ^
  "if(-not $esERP){Write-Host 'Seguridad: el puerto 5000 pertenece a otro programa.'; Write-Host $cmd; exit 2};" ^
  "Stop-Process -Id $listener.OwningProcess -Force;" ^
  "Write-Host 'ERP V3 detenido correctamente.'"

if errorlevel 2 (
    pause
    exit /b 2
)

powershell.exe -NoProfile -Command "Start-Sleep -Seconds 3"
