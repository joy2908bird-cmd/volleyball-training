# 🏐 小朋友排球訓練小幫手

> 專為兒童排球訓練設計的 AI 教練網頁 App — MVP v1.0

---

## 功能簡介

| 功能 | 說明 |
|------|------|
| 🤖 AI 週訓練菜單 | Gemini 依據小朋友體態與目標技巧，生成結構化每週訓練計畫 |
| ✅ 每日打卡 | 一鍵記錄今日練習完成，累積積分 |
| 📊 個人進度追蹤 | 進度條 + 積分統計，著重自我成長 |
| 🎥 影片 AI 分析 | 上傳 10 秒練習短片，Gemini 多模態分析動作並給予兒童友善回饋 |

---

## 技術架構

```
┌─────────────────────────────────────┐
│         Streamlit 前端介面           │
│              app.py                  │
└──────────────┬──────────────────────┘
               │
    ┌──────────┴──────────┐
    ▼                     ▼
┌─────────┐        ┌──────────────┐
│ Supabase│        │  Gemini API  │
│ (DB +   │        │ gemini-1.5-  │
│ Storage)│        │    flash     │
└─────────┘        └──────────────┘
```

---

## 專案結構

```
排球訓練/
├── app.py              # Streamlit 主程式（單檔 MVP）
├── requirements.txt    # Python 套件依賴
├── .env.example        # 環境變數範本（複製為 .env 填入金鑰）
├── .env                # 實際金鑰（已加入 .gitignore，勿上傳！）
├── migration.sql       # Supabase curriculum 欄位補充腳本
├── .gitignore
├── .vscode/
│   ├── settings.json   # Python 格式化、直譯器設定
│   ├── launch.json     # F5 直接啟動 Streamlit
│   └── extensions.json # 建議安裝的 VS Code 擴充套件
└── README.md
```

---

## 快速啟動

### 1. 安裝套件

```bash
# 建立虛擬環境（建議）
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac / Linux

pip install -r requirements.txt
```

### 2. 設定環境變數

```bash
# 複製範本
copy .env.example .env        # Windows
# cp .env.example .env        # Mac / Linux

# 用記事本或 VS Code 開啟 .env，填入三個金鑰：
# SUPABASE_URL=...
# SUPABASE_ANON_KEY=...
# GEMINI_API_KEY=...
```

### 3. 執行 Supabase Migration

在 Supabase 後台 → SQL Editor，貼上 `migration.sql` 內容並執行。
（詳見 `SUPABASE_SETUP.md`）

### 4. 啟動 App

```bash
streamlit run app.py
```

或在 VS Code 按 **F5**（已設定 launch.json）。

瀏覽器開啟 → `http://localhost:8501`

---

## 環境需求

- Python 3.10+
- Supabase 帳號（免費方案即可）
- Google AI Studio 帳號（取得 Gemini API Key）

---

## MVP 測試對象

初期針對 **5 位小朋友** 進行測試，蒐集回饋後再決定是否擴展功能。
