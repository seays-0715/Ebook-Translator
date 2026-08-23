# Build Windows EXE with PyInstaller
# Usage (from repo root, in a Windows PowerShell with venv activated):
#   .\scripts\build_windows.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

python -m pip install -r requirements.txt
python -m pip install pyinstaller

$args = @(
  "--noconfirm",
  "--clean",
  "--onefile",
  "--windowed",
  "--name", "EbookTranslator",
  "--paths", ".",
  "--add-data", "src/i18n/en.json;src/i18n",
  "--add-data", "src/i18n/zh-HK.json;src/i18n",
  "--hidden-import", "customtkinter",
  "--hidden-import", "ebooklib",
  "--hidden-import", "bs4",
  "--hidden-import", "lxml",
  "--hidden-import", "PIL",
  "--hidden-import", "openai",
  "--collect-all", "customtkinter",
  "src/main.py"
)

python -m PyInstaller @args
Write-Host "Output: dist\EbookTranslator.exe"
