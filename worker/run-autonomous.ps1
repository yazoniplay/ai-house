$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path "worker/.env")) {
  Copy-Item "worker/.env.example" "worker/.env"
  Write-Host "Created worker/.env. Add your API keys, then run this script again."
  exit 1
}
python -m pip install -r worker/requirements.txt
python worker/autonomous_engine.py --loop
