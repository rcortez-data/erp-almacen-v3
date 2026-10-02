@echo off
setlocal
cd /d "%~dp0"

if /I "%~1"=="iniciar" goto iniciar
if /I "%~1"=="detener" goto detener
if /I "%~1"=="estado" goto estado

echo.
echo ========================================
echo        WEB PRICE SHOES - SERVIDOR
echo ========================================
echo  1. Iniciar sistema
echo  2. Detener sistema
echo  3. Ver estado
echo  4. Salir
echo.
set /p opcion=Selecciona una opcion: 
if "%opcion%"=="1" goto iniciar
if "%opcion%"=="2" goto detener
if "%opcion%"=="3" goto estado
goto fin

:iniciar
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\servidor.ps1" iniciar
goto fin

:detener
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\servidor.ps1" detener
goto fin

:estado
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\servidor.ps1" estado
goto fin

:fin
endlocal
