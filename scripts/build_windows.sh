#!/usr/bin/env bash
# Cross-note: produce a onefile binary (primarily for testing on Linux).
# For a real Windows EXE, run scripts/build_windows.ps1 on Windows.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --onefile --name EbookTranslator \
  --paths . \
  --add-data "src/i18n/en.json:src/i18n" \
  --add-data "src/i18n/zh-HK.json:src/i18n" \
  --hidden-import customtkinter \
  --hidden-import ebooklib \
  --hidden-import bs4 \
  --hidden-import lxml \
  --hidden-import PIL \
  --hidden-import openai \
  src/main.py
echo "Output: dist/EbookTranslator"
