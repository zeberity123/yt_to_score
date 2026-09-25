@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
where npm >nul 2>nul
if errorlevel 1 (
    echo Node.js was not found. The browser workspace will be available.
) else (
    call npm install
    if errorlevel 1 goto :failed
)
echo.
echo Ready. Double-click run.bat to open Video Sheet to PDF.
pause
exit /b 0
:failed
echo.
echo Setup failed. Install Python 3.11 or newer with 'Add Python to PATH', then retry.
pause
exit /b 1
