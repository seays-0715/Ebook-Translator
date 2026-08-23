# Ebook Translator EXE

Windows EXE ebook processor + Local AI translation tool.

Canonical Book (Content Blocks) core. Spec: Technical Specification v1.0 (Frozen).

## Quick start

```bash
pip install -r requirements.txt
python -m src.main --gui
python -m src.main convert input.epub -o output.epub
python -m src.main translate input.epub -o out.epub --endpoint http://localhost:8000/v1 --model local --target zh-TW
pytest tests/ -q
```

## Build Windows EXE

```powershell
.\scripts\build_windows.ps1
```
