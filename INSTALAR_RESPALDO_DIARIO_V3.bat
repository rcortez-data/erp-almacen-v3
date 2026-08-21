@echo off
setlocal
cd /d "%~dp0"
set TAREA=ERP_Almacen_V3_Respaldo_Diario
schtasks /Create /F /SC DAILY /ST 02:00 /TN "%TAREA%" /TR "cmd /c \"%CD%\RESPALDO_AUTOMATICO_V3.bat\"" 
if errorlevel 1 (
  echo No se pudo crear la tarea. Ejecuta este archivo como administrador.
  pause
  exit /b 1
)
echo Tarea instalada: %TAREA% todos los dias a las 02:00.
pause
