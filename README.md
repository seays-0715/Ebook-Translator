# Ebook Translator EXE

Windows EXE 電子書處理 ＋ Local AI 翻譯工具。

以 **Canonical Book（Content Blocks）** 為核心：輸入格式可自由擴充，輸出統一為乾淨 EPUB；透過 OpenAI-compatible Local AI 翻譯，並以 Glossary 累積專有名詞知識。

實作依據：Technical Specification v1.0 (Frozen)。

## 快速開始（Windows，目前無預建 EXE）

1. 安裝 [Python 3.11+](https://www.python.org/downloads/)（勾選 **Add python.exe to PATH**）
2. 下載源碼並解壓：
   - https://github.com/seays-0715/Ebook-Translator/archive/refs/heads/main.zip
3. 雙擊 **`run_gui.bat`**（首次會自動建立 venv 並安裝依賴）
4. 或在資料夾開 PowerShell：`.\\run_gui.ps1`

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
.\\scripts\\build_windows.ps1
```

產物：`dist\\EbookTranslator.exe`

之後可自行到 GitHub → Releases → 建立 Release 並上傳該 EXE。

> 遠端 Linux 環境無法產出可用的 Windows GUI EXE；源碼 zip 已可由上面連結下載。


## 轉換模式（conversion_mode）

Convert 輸出乾淨 EPUB 時可選兩種模式。兩種都是**程式自訂的乾淨樣式**，不會讀取或保留原檔 CSS／出版社排版；Normalize 階段已去掉出版社專用呈現。

| 模式 | 標題／閱讀結構 | 版面傾向 |
|------|----------------|----------|
| **clean**（預設） | 保留正規化後有意義的完整標題階層（h1–h6）、章節與段落結構 | 舒適的一般閱讀字距／邊距 |
| **compact** | **呈現階層可簡化**：3 級或更深標題（h3–h6）改以帶 `subhead` class 的段落呈現，標題文字仍保留；章節、段落、閱讀順序不變 | 較緊湊的統一版式 |

重點：`compact` 是**呈現階層**的精簡，**不是**刪內容。不會刪章節、標題文字、有意義段落，也不會打亂閱讀順序。兩種模式的差異包含標題 HTML 結構與間距，不單是 CSS 數值微調。

## 授權

MIT
