param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonPath = Join-Path $ProjectRoot ".venv_web\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "Missing .venv_web. Run: python -m venv .venv_web; .\.venv_web\Scripts\python.exe -m pip install -e '.[dev]'"
}

$LogDirectory = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$ApiOutLog = Join-Path $LogDirectory "phase_e_api.out.log"
$ApiErrorLog = Join-Path $LogDirectory "phase_e_api.error.log"
$env:VIETIRR_API_PORT = "$ApiPort"
$env:VIETIRR_API_PROXY = "http://127.0.0.1:$ApiPort"
$env:VIETIRR_ENV = "development"
if (-not $env:DATABASE_URL) {
    $DatabasePath = (Join-Path $ProjectRoot ".tmp\vietirr-local.db").Replace("\", "/")
    $env:DATABASE_URL = "sqlite+pysqlite:///$DatabasePath"
}

$ApiProcess = Start-Process -FilePath $PythonPath `
    -ArgumentList @((Join-Path $ProjectRoot "scripts\run_phase_e_api.py")) `
    -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $ApiOutLog -RedirectStandardError $ApiErrorLog

try {
    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
        try {
            $Health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/health" -TimeoutSec 1
            if ($Health.status -eq "ready") { $Ready = $true; break }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $Ready) {
        throw "Evidence API did not become ready. See $ApiErrorLog"
    }
    Write-Host "VietIrr Intelligence: http://127.0.0.1:$WebPort" -ForegroundColor Green
    Write-Host "Evidence API: http://127.0.0.1:$ApiPort/api/health" -ForegroundColor DarkGreen
    Push-Location (Join-Path $ProjectRoot "frontend")
    try {
        & cmd /c "npm run dev -- --host 127.0.0.1 --port $WebPort"
    } finally {
        Pop-Location
    }
} finally {
    if ($ApiProcess -and -not $ApiProcess.HasExited) {
        Stop-Process -Id $ApiProcess.Id -Force
    }
}
