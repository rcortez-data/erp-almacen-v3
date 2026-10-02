param(
    [ValidateSet("iniciar", "detener", "estado")]
    [string]$Accion = "estado"
)

$ProjectPath = Split-Path -Parent $PSScriptRoot
$PythonPath = Join-Path $ProjectPath ".venv\Scripts\python.exe"
$PidFile = Join-Path $ProjectPath ".server.pid"
$LogPath = Join-Path $ProjectPath "logs"
$OutLog = Join-Path $LogPath "servidor.log"
$ErrorLog = Join-Path $LogPath "servidor-error.log"
$ServerUrl = "http://127.0.0.1:8000/"

function Get-WebServerProcess {
    if (-not (Test-Path -LiteralPath $PidFile)) { return $null }
    $SavedPid = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    if ($SavedPid -notmatch "^\d+$") { return $null }
    $Process = Get-Process -Id ([int]$SavedPid) -ErrorAction SilentlyContinue
    if (-not $Process) { return $null }
    $CommandLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $SavedPid" -ErrorAction SilentlyContinue).CommandLine
    if ($CommandLine -notlike "*manage.py runserver 127.0.0.1:8000*") { return $null }
    return $Process
}

if ($Accion -eq "iniciar") {
    $Existing = Get-WebServerProcess
    if ($Existing) {
        Write-Host "El sistema ya esta iniciado (PID $($Existing.Id))." -ForegroundColor Yellow
        Write-Host "Abre: $ServerUrl"
        exit 0
    }
    if (-not (Test-Path -LiteralPath $PythonPath)) {
        Write-Host "No se encontro el entorno virtual en .venv." -ForegroundColor Red
        Write-Host "Consulta README.md para crearlo con Python 3.12."
        exit 1
    }
    New-Item -ItemType Directory -Force -Path $LogPath | Out-Null
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    $Process = Start-Process -FilePath $PythonPath -ArgumentList "manage.py", "runserver", "127.0.0.1:8000", "--noreload" -WorkingDirectory $ProjectPath -WindowStyle Hidden -RedirectStandardOutput $OutLog -RedirectStandardError $ErrorLog -PassThru
    Set-Content -LiteralPath $PidFile -Value $Process.Id
    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 20; $Attempt++) {
        Start-Sleep -Milliseconds 250
        try {
            $Response = Invoke-WebRequest -Uri $ServerUrl -UseBasicParsing -TimeoutSec 2
            if ($Response.StatusCode -eq 200) { $Ready = $true; break }
        } catch { }
    }
    if ($Ready) {
        Write-Host "Sistema iniciado correctamente (PID $($Process.Id))." -ForegroundColor Green
        Write-Host "Tienda: $ServerUrl"
        Write-Host "Administracion: ${ServerUrl}admin/"
        exit 0
    }
    Write-Host "El servidor no respondio a tiempo. Revisa logs\servidor-error.log." -ForegroundColor Red
    exit 1
}

if ($Accion -eq "detener") {
    $Process = Get-WebServerProcess
    if (-not $Process) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        Write-Host "El sistema ya estaba detenido." -ForegroundColor Yellow
        exit 0
    }
    Stop-Process -Id $Process.Id -Force
    $Process.WaitForExit(5000)
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "Sistema detenido correctamente." -ForegroundColor Green
    exit 0
}

$Process = Get-WebServerProcess
if ($Process) {
    Write-Host "Estado: INICIADO (PID $($Process.Id))" -ForegroundColor Green
    Write-Host "Tienda: $ServerUrl"
} else {
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "Estado: DETENIDO" -ForegroundColor Yellow
}
