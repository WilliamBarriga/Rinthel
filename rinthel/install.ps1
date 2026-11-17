[CmdletBinding()]
param(
    [switch]$SkipLaunch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not [Environment]::Is64BitProcess) {
    throw 'Rinthel requiere PowerShell de 64 bits. Cierra esta ventana x86 y abre Windows PowerShell sin la etiqueta (x86).'
}
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstanceRoot = Split-Path -Parent $ProjectRoot
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

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

function Find-Python313 {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        & $launcher.Source -3.13 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 13) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { return @($launcher.Source, '-3.13') }
    }
    foreach ($name in @('python3.13', 'python')) {
        $candidate = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $candidate) { continue }
        & $candidate.Source -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 13) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { return @($candidate.Source) }
    }
    throw 'Falta Python 3.13+. Instálalo desde https://www.python.org/downloads/windows/ (o con winget si está disponible).'
}

$PythonCommand = @(Find-Python313)
if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host '[install] creando entorno Python...'
    $PythonExe = $PythonCommand[0]
    $PythonArgs = @()
    if ($PythonCommand.Count -gt 1) {
        $PythonArgs = $PythonCommand[1..($PythonCommand.Count - 1)]
    }
    & $PythonExe @PythonArgs -m venv (Join-Path $ProjectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear .venv.' }
}

& $VenvPython -m pip install -e $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias Python.' }

$Cargo = Get-Command cargo -ErrorAction SilentlyContinue
if (-not $Cargo) {
    throw 'Falta Rust. Instálalo desde https://www.rust-lang.org/tools/install y abre una terminal nueva.'
}

Push-Location (Join-Path $ProjectRoot 'rinthel-client')
try {
    & $Cargo.Source build --release
    if ($LASTEXITCODE -ne 0) { throw 'Falló la compilación del cliente Rust.' }
} finally {
    Pop-Location
}

$EnvFile = Join-Path $InstanceRoot '.env'
if (-not (Test-Path -LiteralPath $EnvFile)) {
    $DataRoot = (Join-Path $env:USERPROFILE 'Rinthel-data').Replace('\', '/')
    $UserRoot = $env:USERPROFILE.Replace('\', '/')
    # Only machine paths: the Validated profile of Windows lives in the
    # daemon config (rinthel_tui/config.py::VALIDATED_PROFILES), and the
    # Local model in the catalog that [0] INSTALL writes.
    @(
        "RINTHEL_LLAMA_BIN=$DataRoot/llama.cpp/build-cuda/bin/Release/llama-server.exe"
        "RINTHEL_MODELS_DIR=$DataRoot/models"
        "RINTHEL_LLAMA_LOG_PATH=$DataRoot/logs/llama-server.log"
        "RINTHEL_LLAMACPP_REPO_DIR=$DataRoot/llama.cpp"
        "RINTHEL_UNDERSTORY_DIR=$DataRoot/understory"
        "RINTHEL_PITHAGORAS_DIR=$DataRoot/pithagoras"
        "RINTHEL_WORKSPACES_DIR=$UserRoot"
        "RINTHEL_PI_AGENT_DIR=$UserRoot/.pi/agent"
    ) | Set-Content -LiteralPath $EnvFile -Encoding UTF8
    Write-Host "[install] configuración Windows creada en $EnvFile"
}

if (-not $SkipLaunch) {
    & (Join-Path $ProjectRoot 'rinthel-boot.ps1')
}
