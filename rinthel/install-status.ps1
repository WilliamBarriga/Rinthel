[CmdletBinding()]
param(
    [switch]$Watch,
    [int]$IntervalSeconds = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$DataRoot = Join-Path $env:USERPROFILE 'Rinthel-data'
$Server = Join-Path $DataRoot 'llama.cpp\build-cuda\bin\Release\llama-server.exe'
$Model = Join-Path $DataRoot 'models\Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf'
$InstanceRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $InstanceRoot '.env'
$Bundle = Join-Path $InstanceRoot 'data\understory\index.md'

function Test-EnvKey([string]$Key) {
    if (-not (Test-Path -LiteralPath $EnvFile)) { return $false }
    return [bool](Select-String -LiteralPath $EnvFile -Pattern "^$Key=.+" -Quiet)
}

function Test-InstallComplete {
    return (
        (Test-Path -LiteralPath $Server) -and
        (Test-Path -LiteralPath $Model) -and
        ((Get-Item -LiteralPath $Model).Length -gt 1GB) -and
        (Test-EnvKey 'RINTHEL_PANEL_SECRET') -and
        (Test-EnvKey 'UNDERSTORY_TOKEN') -and
        (Test-Path -LiteralPath $Bundle)
    )
}

do {
    if ($Watch) { Clear-Host }

    $BuildCount = @(Get-Process cmake, MSBuild, cl -ErrorAction SilentlyContinue).Count
    $DownloadCount = @(Get-Process curl -ErrorAction SilentlyContinue).Count
    $ModelSizeGB = if (Test-Path -LiteralPath $Model) {
        [math]::Round((Get-Item -LiteralPath $Model).Length / 1GB, 2)
    } else { 0 }

    Write-Host "Rinthel INSTALL - $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Cyan
    Write-Host "Compilacion activa : $BuildCount proceso(s)"
    Write-Host "llama-server.exe   : $(if (Test-Path -LiteralPath $Server) { 'LISTO' } else { 'pendiente' })"
    Write-Host "Descarga activa    : $DownloadCount proceso(s)"
    Write-Host "Modelo descargado  : $ModelSizeGB GB de ~22 GB"
    Write-Host "Secretos (.env)    : $(if (Test-EnvKey 'RINTHEL_PANEL_SECRET') { 'LISTO' } else { 'pendiente' })"
    Write-Host "Understory         : $(if ((Test-EnvKey 'UNDERSTORY_TOKEN') -and (Test-Path -LiteralPath $Bundle)) { 'LISTO' } else { 'pendiente' })"

    if (Test-InstallComplete) {
        Write-Host "`nINSTALL COMPLETO" -ForegroundColor Green
    } elseif ($BuildCount -gt 0) {
        Write-Host "`nFASE ACTUAL: compilando llama.cpp" -ForegroundColor Yellow
    } elseif ($DownloadCount -gt 0 -or $ModelSizeGB -gt 0) {
        Write-Host "`nFASE ACTUAL: descargando o validando el modelo" -ForegroundColor Yellow
    } else {
        Write-Host "`nFASE ACTUAL: preparando la siguiente unidad o esperando respuesta" -ForegroundColor Yellow
    }

    if ($Watch) {
        Write-Host "`nCtrl+C cierra solamente este monitor." -ForegroundColor DarkGray
        Start-Sleep -Seconds $IntervalSeconds
    }
} while ($Watch)
