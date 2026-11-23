@echo off
setlocal
cd /d "%~dp0"
echo.
echo  AI HOUSE - LOCAL STARTUP
echo  ----------------------
echo  This launcher installs dependencies, safely replaces an old AI House
echo  dashboard on port 8000, then shows startup errors in a visible console.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-house.ps1"
if errorlevel 1 (
    echo.
    echo AI House did not start. The error above should explain why.
    pause
)
