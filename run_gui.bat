@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3.11+ from https://www.python.org/downloads/
  echo Remember to check "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create venv.
    pause
    exit /b 1
  )
  echo Installing dependencies (first run may take a few minutes)...
  ".venv\Scripts\python.exe" -m pip install -U pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
  )
)

echo Starting Ebook Translator GUI...
".venv\Scripts\python.exe" -m src.main --gui
if errorlevel 1 (
  echo.
  echo [ERROR] App exited with an error.
  pause
)
