@echo off
setlocal
cd /d "%~dp0"

if not exist "worker\.env" (
  echo Missing worker\.env. Copy worker\.env.example to worker\.env and add your keys, then run this again.
  pause
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.12 from python.org and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

python -m pip install --quiet -r worker\requirements.txt flask

start "AI House Engine" cmd /k "cd /d %~dp0 && python worker\autonomous_engine.py --loop"

start "AI House Dashboard" cmd /k "cd /d %~dp0dashboard && python server.py"

timeout /t 4 /nobreak >nul
start "" http://127.0.0.1:8000
