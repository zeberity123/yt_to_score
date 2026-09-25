@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
if exist "node_modules\electron\dist\electron.exe" (
    "node_modules\electron\dist\electron.exe" .
) else (
    echo Opening the browser workspace. Run setup.bat to install the desktop shell.
    ".venv\Scripts\python.exe" -m drumscore.server --open
)
if errorlevel 1 pause
