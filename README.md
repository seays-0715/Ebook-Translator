# Ebook Translator EXE

Windows EXE 電子書處理 ＋ Local AI 翻譯工具。

以 **Canonical Book（Content Blocks）** 為核心：輸入格式可自由擴充，輸出統一為乾淨 EPUB；透過 OpenAI-compatible Local AI 翻譯，並以 Glossary 累積專有名詞知識。

實作依據：Technical Specification v1.0 (Frozen)。

## 快速開始（Windows，目前無預建 EXE）

1. 安裝 [Python 3.11+](https://www.python.org/downloads/)（勾選 **Add python.exe to PATH**）
2. 下載源碼並解壓：
   - https://github.com/seays-0715/Ebook-Translator/archive/refs/heads/main.zip
3. 雙擊 **`run_gui.bat`**（首次會自動建立 venv 並安裝依賴）
4. 或在資料夾開 PowerShell：`.un_gui.ps1`

### 命令列

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

## 打包 Windows EXE（必須在 Windows 本機）

```powershell
.\scripts\build_windows.ps1
```

產物：`dist\EbookTranslator.exe`

之後可自行到 GitHub → Releases → 建立 Release 並上傳該 EXE。

> 遠端 Linux 環境無法產出可用的 Windows GUI EXE；源碼 zip 已可由上面連結下載。

## 授權

MIT
