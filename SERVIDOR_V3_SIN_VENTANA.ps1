$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSCommandPath
Set-Location $root

$env:ERP_DB_BACKEND = 'sqlite'
$env:ERP_HOST = '0.0.0.0'
$env:ERP_PORT = '5000'
$env:DEBUG = 'False'
$env:ERP_AUTO_MIGRATE = 'True'
$env:FLASK_ENV = 'production'

$pythonCandidates = @(
    (Join-Path $root '.venv\Scripts\python.exe'),
    (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1),
    (Get-Command py.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1)
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique

$python = $null
foreach ($candidate in $pythonCandidates) {
    try {
        & $candidate -c 'import sys; print(sys.executable)' *> $null
        if ($LASTEXITCODE -eq 0) {
            $python = $candidate
            break
        }
    } catch {
        # Prueba el siguiente candidato; un venv copiado puede estar roto.
    }
}

if (-not $python) {
    throw "No se encontro un Python funcional. Ejecuta PREPARAR_ENTORNO.ps1 para crear el entorno del ERP."
}

& $python -c 'import waitress' *> $null
if ($LASTEXITCODE -ne 0) {
    throw "El Python encontrado no tiene las dependencias del ERP. Ejecuta PREPARAR_ENTORNO.ps1. Python: $python"
}

& $python 'scripts\production_preflight.py'
if ($LASTEXITCODE -ne 0) {
    throw 'El preflight de produccion no fue aprobado.'
}

& $python -m waitress --listen=0.0.0.0:5000 --threads=8 wsgi:application
