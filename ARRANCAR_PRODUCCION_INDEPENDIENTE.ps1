$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSCommandPath
$serverScript = Join-Path $root 'SERVIDOR_V3_SIN_VENTANA.ps1'

if (-not (Test-Path -LiteralPath $serverScript)) {
    throw "No se encontro el script del servidor: $serverScript"
}

$listener = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    Write-Host 'ERP V3 ya esta funcionando en http://127.0.0.1:5000'
    exit 0
}

$command = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $serverScript + '"'
$startup = ([wmiclass]'Win32_ProcessStartup').CreateInstance()
$startup.ShowWindow = 0

$result = ([wmiclass]'Win32_Process').Create($command, $root, $startup)
if ($result.ReturnValue -ne 0) {
    throw "No se pudo arrancar ERP V3 por WMI. Codigo: $($result.ReturnValue)"
}

Write-Host "ERP V3 arrancado independiente. PID inicial: $($result.ProcessId)"
