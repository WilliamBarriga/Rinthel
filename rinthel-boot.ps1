[CmdletBinding()]
param(
    [switch]$Stop
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$ClientDir = Join-Path $ProjectRoot 'rinthel-client'
$Client = Join-Path $ClientDir 'target\release\rinthel.exe'
$PidFile = Join-Path $ProjectRoot '.rinthel-daemon.pid'
$LogDir = Join-Path $ProjectRoot 'logs'
$Port = 8765

function Add-VisualStudioCMakeToPath {
    if (Get-Command cmake -ErrorAction SilentlyContinue) { return }
    $SearchRoot = Join-Path $env:ProgramFiles 'Microsoft Visual Studio'
    $VsCMake = Get-ChildItem -Path $SearchRoot -Filter cmake.exe -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -like '*CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe' } |
        Select-Object -First 1
    if ($VsCMake) {
        $env:Path = "$($VsCMake.DirectoryName);$env:Path"
    }
}

Add-VisualStudioCMakeToPath

$EnvFile = Join-Path $ProjectRoot '.env'
if (Test-Path -LiteralPath $EnvFile) {
    $PortLine = Get-Content -LiteralPath $EnvFile | Where-Object { $_ -match '^RINTHEL_DAEMON_PORT=' } | Select-Object -Last 1
    if ($PortLine) { $Port = [int](($PortLine -split '=', 2)[1].Trim()) }
}

function Test-LocalPort([int]$Number) {
    $ClientSocket = [System.Net.Sockets.TcpClient]::new()
    try {
        $Result = $ClientSocket.BeginConnect('127.0.0.1', $Number, $null, $null)
        return $Result.AsyncWaitHandle.WaitOne(300) -and $ClientSocket.Connected
    } catch {
        return $false
    } finally {
        $ClientSocket.Dispose()
    }
}

if ($Stop) {
    if (-not (Test-Path -LiteralPath $PidFile)) {
        Write-Host '[boot] el daemon no tiene pidfile; no se detuvo ningún proceso.'
        return
    }
    $DaemonPid = [int](Get-Content -LiteralPath $PidFile -Raw)
    Stop-Process -Id $DaemonPid -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $PidFile -Force
    Write-Host "[boot] daemon $DaemonPid detenido."
    return
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw 'No existe .venv\Scripts\python.exe. Ejecuta .\install.ps1 primero.'
}

$Cargo = Get-Command cargo -ErrorAction SilentlyContinue
if ($Cargo) {
    Push-Location $ClientDir
    try { & $Cargo.Source build --release } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0 -and -not (Test-Path -LiteralPath $Client)) {
        throw 'Falló la compilación del cliente y no existe un binario anterior.'
    }
} elseif (-not (Test-Path -LiteralPath $Client)) {
    throw 'Falta cargo y tampoco existe rinthel.exe. Ejecuta .\install.ps1.'
}

if (-not (Test-LocalPort $Port)) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    $env:RINTHEL_DAEMON_PORT = [string]$Port
    $Daemon = Start-Process -FilePath $Python -ArgumentList @('-m', 'rinthel_tui.daemon') `
        -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $LogDir 'daemon.out.log') `
        -RedirectStandardError (Join-Path $LogDir 'daemon.err.log')
    Set-Content -LiteralPath $PidFile -Value $Daemon.Id -Encoding ASCII
    foreach ($Attempt in 1..40) {
        if (Test-LocalPort $Port) { break }
        Start-Sleep -Milliseconds 250
    }
    if (-not (Test-LocalPort $Port)) {
        throw "El daemon no respondió en el puerto $Port. Revisa logs\daemon.err.log."
    }
}

& $Client --port $Port
