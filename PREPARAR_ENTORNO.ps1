$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSCommandPath
Set-Location $root

$systemPython = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $systemPython) {
    $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $systemPython = $pyLauncher
    }
}

if (-not $systemPython) {
    throw 'No se encontro Python. Instala Python 3.11 o posterior y habilita Python en PATH.'
}

$pythonCommand = $systemPython.Source
$venvDir = Join-Path $root '.venv'
$venvPython = Join-Path $root '.venv\Scripts\python.exe'

# Un entorno virtual copiado desde otra PC no es portable. Si esta roto,
# se reconstruye localmente para que las rutas internas apunten a esta PC.
$venvWorks = $false
if (Test-Path -LiteralPath $venvPython) {
    try {
        & $venvPython -c 'import sys; print(sys.executable)' *> $null
        $venvWorks = ($LASTEXITCODE -eq 0)
    } catch {
        $venvWorks = $false
    }
}

if (-not $venvWorks) {
    Write-Host 'Creando un entorno virtual local para esta computadora...'
    & $pythonCommand -m venv $venvDir | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw 'No se pudo crear el entorno virtual.'
    }
}

Write-Host 'Instalando o actualizando dependencias...'
& $venvPython -m pip install --upgrade pip | Out-Host
& $venvPython -m pip install -r (Join-Path $root 'requirements.txt') | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw 'No se pudieron instalar las dependencias del ERP.'
}

Write-Host 'Entorno listo. Ya puedes ejecutar INICIAR_PRODUCCION_V3.bat.'
