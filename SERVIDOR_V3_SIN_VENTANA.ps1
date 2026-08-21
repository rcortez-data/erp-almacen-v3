$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSCommandPath
Set-Location $root

$env:ERP_DB_BACKEND = 'sqlite'
$env:ERP_HOST = '0.0.0.0'
$env:ERP_PORT = '5000'
$env:DEBUG = 'False'
$env:FLASK_ENV = 'production'

$python = 'C:\Users\Almacen\AppData\Local\Python\pythoncore-3.14-64\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python no encontrado: $python"
}

& $python 'scripts\production_preflight.py'
if ($LASTEXITCODE -ne 0) {
    throw 'El preflight de produccion no fue aprobado.'
}

& $python -m waitress --listen=0.0.0.0:5000 --threads=8 wsgi:application
