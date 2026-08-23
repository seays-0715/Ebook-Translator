# Ebook Translator — first-run setup + GUI
Set-Location $PSScriptRoot
$ErrorActionPreference = "Stop"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Host "[ERROR] Python not found. Install Python 3.11+ and add to PATH."
  exit 1
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  Write-Host "Creating virtual environment..."
  python -m venv .venv
  Write-Host "Installing dependencies..."
  & .\.venv\Scripts\python.exe -m pip install -U pip
  & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}

Write-Host "Starting GUI..."
& .\.venv\Scripts\python.exe -m src.main --gui
