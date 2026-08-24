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
.\scripts\build_windows.ps1
```

產物：`dist\EbookTranslator.exe`

之後可自行到 GitHub → Releases → 建立 Release 並上傳該 EXE。

> 遠端 Linux 環境無法產出可用的 Windows GUI EXE；源碼 zip 已可由上面連結下載。


## 轉換模式（conversion_mode）

Convert 輸出乾淨 EPUB 時可選三種模式。三種都是**程式自訂的乾淨樣式**，不會讀取或保留原檔 CSS／複雜排版；差別在標題結構與預設字距／邊距。

| 模式 | 標題結構 | 版面傾向 |
|------|----------|----------|
| **preserve** | 保留原有標題階層（h1–h6） | 較鬆的行距與邊距，接近常見出版版式 |
| **clean**（預設） | 保留原有標題階層（h1–h6） | 適中閱讀預設（字距／邊距） |
| **simplified** | **結構會變**：章節標題用 h1；**3 級或更深標題（h3–h6）壓平為帶 `subhead` class 的普通段落**，不再輸出 `<h3>`–`<h6>` | 較緊湊的統一版式 |

重點：`preserve` / `clean` 與 `simplified` 的差異**不只是 CSS**——`simplified` 會改變 HTML 標題階層，影響目錄層級與閱讀器對標題的辨識。選模式時請依是否需要保留多層標題來決定。

## 授權

MIT
