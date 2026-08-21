@echo off
setlocal

powershell.exe -NoProfile -Command "$listener=Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if(-not $listener){Write-Host 'ERP V3 ya estaba detenido.'; exit 0}; $process=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $listener.OwningProcess); $cmd=$process.CommandLine; if($cmd -notlike '*waitress*' -or $cmd -notlike '*wsgi:application*' -or $cmd -notlike '*5000*'){Write-Host 'Seguridad: el puerto 5000 pertenece a otro programa.'; exit 2}; Stop-Process -Id $listener.OwningProcess -Force; Write-Host 'ERP V3 detenido correctamente.'"

if errorlevel 2 (
    pause
    exit /b 2
)

timeout /t 3 /nobreak >nul
