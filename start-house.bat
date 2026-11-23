@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
pushd "%ROOT%" || (
  echo Could not open the AI House folder.
  pause
  exit /b 1
)

if not exist "worker\.env" if not exist ".env" (
  echo Missing API key configuration.
  if exist "worker\.env.example" (
    copy "worker\.env.example" "worker\.env" >nul
    echo Created worker\.env from the example. Add your API keys there, then run this file again.
  ) else if exist ".env.example" (
    copy ".env.example" "worker\.env" >nul
    echo Created worker\.env from the root example. Add your API keys there, then run this file again.
  ) else (
    echo Create worker\.env or .env and add your provider API keys.
  )
  pause
  exit /b 1
)

set "PYTHON_EXE="
for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE (
  echo Python was not found on PATH.
  echo Install Python 3.12 from python.org and enable "Add python.exe to PATH".
  pause
  exit /b 1
)

echo Installing or updating AI House dependencies...
"%PYTHON_EXE%" -m pip install -r "worker\requirements.txt" flask
if errorlevel 1 (
  echo Dependency installation failed. Check your internet connection and Python pip setup.
  pause
  exit /b 1
)

if not exist "dashboard\server.py" (
  echo Dashboard server.py was not found in the dashboard folder.
  pause
  exit /b 1
)

echo Starting AI House dashboard.
echo The dashboard starts and supervises the single local engine process.
start "AI House Dashboard" /D "%ROOT%" "%PYTHON_EXE%" "dashboard\server.py"
if errorlevel 1 (
  echo Could not start the dashboard.
  pause
  exit /b 1
)

timeout /t 4 /nobreak >nul
start "" "http://127.0.0.1:8000"
popd
exit /b 0
