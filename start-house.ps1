$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
$PythonArgs = @()
if ($PythonCommand) {
    $PythonExe = $PythonCommand.Source
} else {
    $PythonCommand = Get-Command py -ErrorAction SilentlyContinue
    if (-not $PythonCommand) {
        Write-Host "Python 3.12 or newer is required. Install it from https://www.python.org/downloads/ and enable Add Python to PATH."
        exit 1
    }
    $PythonExe = $PythonCommand.Source
    $PythonArgs = @("-3")
}

$EnvFile = Join-Path $Root "worker\.env"
$EnvExample = Join-Path $Root "worker\.env.example"
if (-not (Test-Path $EnvFile) -and (Test-Path $EnvExample)) {
    Copy-Item $EnvExample $EnvFile
    Write-Host "Created worker\.env from the example. Add your provider keys to it."
}

Write-Host "Installing/updating AI House Python packages..."
& $PythonExe @PythonArgs -m pip install -r (Join-Path $Root "worker\requirements.txt") flask
if ($LASTEXITCODE -ne 0) {
    Write-Host "Dependency installation failed. Check Python and your internet connection."
    exit 1
}

# Port 8000 may still be held by the old dashboard after a previous launcher
# started it in a hidden window. Stop only a Python process running dashboard/server.py.
$listeners = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
foreach ($ListenerPid in $listeners) {
    $ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $ListenerPid" -ErrorAction SilentlyContinue
    if ($ProcessInfo -and $ProcessInfo.CommandLine -match "(?i)dashboard[\\/]+server\.py") {
        Write-Host "Stopping the previous AI House dashboard (PID $ListenerPid)..."
        & taskkill.exe /PID $ListenerPid /T /F | Out-Null
        Start-Sleep -Seconds 2
    } else {
        $Name = if ($ProcessInfo) { $ProcessInfo.Name } else { "unknown process" }
        Write-Host "Port 8000 is already used by $Name (PID $ListenerPid). Close that program and run start-house.bat again."
        exit 1
    }
}

$Arguments = @()
$Arguments += $PythonArgs
$Arguments += @("dashboard\server.py")
Write-Host "Starting the dashboard in a visible console so startup errors are not hidden..."
$Server = Start-Process -FilePath $PythonExe -ArgumentList $Arguments -WorkingDirectory $Root -PassThru

$Ready = $false
for ($Attempt = 0; $Attempt -lt 25; $Attempt++) {
    Start-Sleep -Seconds 1
    if ($Server.HasExited) {
        Write-Host "The dashboard process exited. Read the AI House console for the Python error."
        exit 1
    }
    $Listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($Listener) {
        $Ready = $true
        break
    }
}
if (-not $Ready) {
    Write-Host "Dashboard did not open port 8000 within 25 seconds. Check the AI House console."
    exit 1
}
Start-Process "http://127.0.0.1:8000"
Write-Host "AI House dashboard is listening at http://127.0.0.1:8000"
