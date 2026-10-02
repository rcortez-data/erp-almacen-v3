$ErrorActionPreference = 'Stop'

$taskName = 'ERP Almacen V3 Produccion'
$root = Split-Path -Parent $PSCommandPath
$serverScript = Join-Path $root 'SERVIDOR_V3_SIN_VENTANA.ps1'

if (-not (Test-Path -LiteralPath $serverScript)) {
    throw "No se encontro el script del servidor: $serverScript"
}

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$serverScript`""

$trigger = New-ScheduledTaskTrigger -AtLogOn

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description 'Arranca el ERP de almacen V3 en produccion, independiente de Codex/ChatGPT.' `
    -Force | Out-Null

Write-Host "Tarea registrada: $taskName"
