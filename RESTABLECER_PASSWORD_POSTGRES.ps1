$ErrorActionPreference = 'Stop'

trap {
    Write-Host ''
    Write-Host 'NO SE PUDO COMPLETAR EL CAMBIO:' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Yellow
    Write-Host 'La configuracion segura de PostgreSQL fue restaurada.'
    Read-Host 'Presiona Enter para cerrar'
    exit 1
}

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $isAdmin) {
    Start-Process powershell.exe -Verb RunAs -WindowStyle Normal -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $PSCommandPath + '"')
    )
    exit
}

$pgRoot = 'C:\Program Files\PostgreSQL\18'
$pgHba = Join-Path $pgRoot 'data\pg_hba.conf'
$psql = Join-Path $pgRoot 'bin\psql.exe'
$serviceName = 'postgresql-x64-18'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = "$pgHba.pre_password_reset_$stamp.bak"
$plainPassword = $null

try {
    if (-not (Test-Path -LiteralPath $pgHba)) { throw "No se encontro $pgHba" }
    if (-not (Test-Path -LiteralPath $psql)) { throw "No se encontro $psql" }

    Copy-Item -LiteralPath $pgHba -Destination $backup
    $original = [IO.File]::ReadAllText($pgHba)
    $pattern = '(?m)^(\s*host\s+all\s+all\s+127\.0\.0\.1/32\s+)scram-sha-256\s*$'
    $temporary = [Text.RegularExpressions.Regex]::Replace($original, $pattern, '${1}trust')
    if ($temporary -eq $original) {
        throw 'No se encontro la regla local scram-sha-256 esperada. No se modifico PostgreSQL.'
    }

    [IO.File]::WriteAllText($pgHba, $temporary, [Text.UTF8Encoding]::new($false))
    Restart-Service -Name $serviceName

    Write-Host ''
    Write-Host 'Escribe la nueva contrasena para el usuario postgres.' -ForegroundColor Cyan
    Write-Host 'Debe ser larga y no debes compartirla con nadie.'
    $secure1 = Read-Host 'Nueva contrasena' -AsSecureString
    $secure2 = Read-Host 'Confirmar contrasena' -AsSecureString
    $plainPassword = [Net.NetworkCredential]::new('', $secure1).Password
    $confirmation = [Net.NetworkCredential]::new('', $secure2).Password
    if ($plainPassword.Length -lt 12) { throw 'La contrasena debe tener al menos 12 caracteres.' }
    if ($plainPassword -ne $confirmation) { throw 'Las contrasenas no coinciden.' }

    $escaped = $plainPassword.Replace("'", "''")
    "ALTER ROLE postgres WITH PASSWORD '$escaped';" |
        & $psql -X -w -h 127.0.0.1 -U postgres -d postgres -v ON_ERROR_STOP=1
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL rechazo el cambio de contrasena.' }
}
finally {
    if (Test-Path -LiteralPath $backup) {
        Copy-Item -LiteralPath $backup -Destination $pgHba -Force
        Restart-Service -Name $serviceName -ErrorAction SilentlyContinue
    }
}

try {
    $env:PGPASSWORD = $plainPassword
    $result = & $psql -X -w -h 127.0.0.1 -U postgres -d postgres -tAc 'SELECT 1;'
    if ($LASTEXITCODE -ne 0 -or $result.Trim() -ne '1') {
        throw 'No fue posible comprobar la contrasena nueva.'
    }
    Write-Host ''
    Write-Host 'CONTRASENA DE POSTGRES RESTABLECIDA Y VERIFICADA.' -ForegroundColor Green
    Write-Host "Respaldo de configuracion: $backup"
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    $plainPassword = $null
}

Read-Host 'Presiona Enter para cerrar'
