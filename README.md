# Ebook Translator EXE

Windows EXE 電子書處理 ＋ Local AI 翻譯工具。

以 **Canonical Book（Content Blocks）** 為核心：輸入格式可自由擴充，輸出統一為乾淨 EPUB；透過 OpenAI-compatible Local AI 翻譯，並以 Glossary 累積專有名詞知識。

實作依據：Technical Specification v1.0 (Frozen)。

## 快速開始

```bash
pip install -r requirements.txt
python -m src.main --gui
python -m src.main convert input.epub -o output.epub
python -m src.main translate input.epub -o out.epub --endpoint http://localhost:8000/v1 --model local --target zh-TW
pytest tests/ -q
```

## 主要功能

| 模組 | 說明 |
|------|------|
| Canonical Book | 結構化 Content Blocks（段落 / 圖片 / 標題等） |
| Convert | EPUB/TXT 解析、章節 Preview（Merge/Split/Rename/Remove）、乾淨 EPUB 輸出 |
| Translate | Batch Queue、Checkpoint/Resume、L1/L2/L3 驗證、Force Export |
| Glossary | 專有名詞表、Builder（原文+官方譯本對齊） |
| GUI | Convert / Translate / Glossary 三頁 + Settings |
| After completion | nothing / sleep / shutdown / open_folder |

## 打包 Windows EXE

```powershell
.\scripts\build_windows.ps1
```

產物：`dist\EbookTranslator.exe`

## 授權

MIT
