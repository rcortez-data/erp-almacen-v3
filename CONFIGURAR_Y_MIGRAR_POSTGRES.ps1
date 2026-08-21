$ErrorActionPreference = 'Stop'
trap {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    Write-Host ''
    Write-Host 'NO SE PUDO COMPLETAR LA MIGRACION:' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Yellow
    Write-Host $_.InvocationInfo.PositionMessage -ForegroundColor DarkYellow
    Read-Host 'Presiona Enter para cerrar'
    exit 1
}

$root = Split-Path -Parent $PSCommandPath
$psql = 'C:\Program Files\PostgreSQL\18\bin\psql.exe'
if (-not (Test-Path -LiteralPath $psql)) { throw 'No se encontro PostgreSQL 18.' }

Write-Host 'CONFIGURACION POSTGRESQL PARA ERP V3 LAB' -ForegroundColor Cyan
$postgresSecure = Read-Host 'Contrasena actual del usuario postgres' -AsSecureString
$appSecure1 = Read-Host 'Nueva contrasena para erp_v3_user (minimo 12 caracteres)' -AsSecureString
$appSecure2 = Read-Host 'Confirmar contrasena de erp_v3_user' -AsSecureString
$postgresPassword = [Net.NetworkCredential]::new('', $postgresSecure).Password
$appPassword = [Net.NetworkCredential]::new('', $appSecure1).Password
$confirmation = [Net.NetworkCredential]::new('', $appSecure2).Password
if ($appPassword.Length -lt 12) { throw 'La contrasena de erp_v3_user debe tener al menos 12 caracteres.' }
if ($appPassword -ne $confirmation) { throw 'Las contrasenas de erp_v3_user no coinciden.' }

$env:PGPASSWORD = $postgresPassword
$testOutput = @(& $psql -X -w -h 127.0.0.1 -U postgres -d postgres -tAc 'SELECT 1;')
if ($LASTEXITCODE -ne 0 -or $testOutput -notcontains '1') { throw 'La contrasena de postgres no fue aceptada.' }

$escaped = $appPassword.Replace("'", "''")
$roleOutput = @(& $psql -X -w -h 127.0.0.1 -U postgres -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='erp_v3_user';")
if ($roleOutput -contains '1') {
    "ALTER ROLE erp_v3_user WITH LOGIN PASSWORD '$escaped';" | & $psql -X -w -h 127.0.0.1 -U postgres -d postgres -v ON_ERROR_STOP=1
} else {
    "CREATE ROLE erp_v3_user WITH LOGIN PASSWORD '$escaped';" | & $psql -X -w -h 127.0.0.1 -U postgres -d postgres -v ON_ERROR_STOP=1
}
if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear o actualizar erp_v3_user.' }

$dbOutput = @(& $psql -X -w -h 127.0.0.1 -U postgres -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='erp_almacen_v3_lab';")
if ($dbOutput -notcontains '1') {
    & $psql -X -w -h 127.0.0.1 -U postgres -d postgres -v ON_ERROR_STOP=1 -c 'CREATE DATABASE erp_almacen_v3_lab OWNER erp_v3_user;'
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear erp_almacen_v3_lab.' }
}
& $psql -X -w -h 127.0.0.1 -U postgres -d postgres -v ON_ERROR_STOP=1 -c 'ALTER DATABASE erp_almacen_v3_lab OWNER TO erp_v3_user;'

$encoded = [Uri]::EscapeDataString($appPassword)
$databaseUrl = "postgresql://erp_v3_user:$encoded@127.0.0.1:5432/erp_almacen_v3_lab"
$env:DATABASE_URL = $databaseUrl
$env:PGPASSWORD = $appPassword

$envFile = Join-Path $root '.env'
$envLines = @(
    'ERP_DB_BACKEND=sqlite'
    'ERP_DATABASE_PATH=./almacen.db'
    "DATABASE_URL=$databaseUrl"
    'DEBUG=False'
)
[IO.File]::WriteAllLines($envFile, $envLines, [Text.UTF8Encoding]::new($false))

Push-Location $root
try {
    python scripts\migrate_sqlite_to_postgres.py --apply --replace
    if ($LASTEXITCODE -ne 0) { throw 'El migrador detecto un error y revirtio PostgreSQL.' }
} finally {
    Pop-Location
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    $postgresPassword = $null; $appPassword = $null
}

Write-Host ''
Write-Host 'POSTGRESQL CONFIGURADO Y MIGRACION APROBADA.' -ForegroundColor Green
Write-Host 'El ERP sigue usando SQLite hasta terminar las pruebas del nuevo motor.'
Read-Host 'Presiona Enter para cerrar'
