@echo off
setlocal

net session >nul 2>&1
if errorlevel 1 (
    powershell.exe -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

netsh advfirewall firewall delete rule name="ERP Almacen V3 - Red local" >nul 2>&1
netsh advfirewall firewall add rule name="ERP Almacen V3 - Red local" dir=in action=allow protocol=TCP localport=5000 remoteip=LocalSubnet profile=private program="C:\Users\Almacen\AppData\Local\Python\pythoncore-3.14-64\python.exe" enable=yes

if errorlevel 1 (
    echo No se pudo configurar el Firewall.
    pause
    exit /b 1
)

echo.
echo ERP V3 habilitado solamente para la red local privada.
echo Direccion: http://192.168.1.58:5000
pause
