$ErrorActionPreference = 'Stop'
$negocioRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $negocioRoot
Write-Host "NEGOCIO disponible en http://localhost:4173" -ForegroundColor Cyan
Write-Host "Presiona Ctrl+C para detener el servidor." -ForegroundColor DarkGray
python -m http.server 4173
