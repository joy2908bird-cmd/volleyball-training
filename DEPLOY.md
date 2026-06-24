# 🚀 部署指南 — 讓小朋友用手機操作

10 人以內的規模，推薦 **Streamlit Community Cloud（免費）**，不用自己架伺服器、手機打開網址就能用，加到主畫面後操作起來就像 App。

---

## 方案一（推薦）：Streamlit Community Cloud 免費上線

### 步驟

1. **把專案推上 GitHub**（private repo 也可以）
   ```bash
   cd 排球訓練
   git init
   git add app.py requirements.txt migration.sql README.md
   git commit -m "volleyball training app"
   # 到 github.com 建一個 repo 後：
   git remote add origin https://github.com/你的帳號/volleyball-app.git
   git push -u origin main
   ```
   ⚠️ `.env` 千萬不要推上去（.gitignore 已排除）。

2. **到 [share.streamlit.io](https://share.streamlit.io) 用 GitHub 帳號登入** → New app → 選擇 repo 和 `app.py`。

3. **設定 Secrets**（App settings → Secrets），貼上：
   ```toml
   SUPABASE_URL = "https://你的專案ID.supabase.co"
   SUPABASE_ANON_KEY = "你的_anon_key"
   GEMINI_API_KEY = "你的_gemini_api_key"
   GEMINI_MODEL = "gemini-3.5-flash"
   APP_PASSWORD = "自訂一組通行碼"
   ADMIN_PASSWORD = "教練後台密碼（務必設定，否則人人可進後台）"
   ```
   > app.py 用 `os.getenv` 讀取，Streamlit Cloud 會把 Secrets 自動注入環境變數。
   > **APP_PASSWORD 一定要設**，因為網址是公開的，設了通行碼才不會被陌生人使用（會消耗你的 API 額度）。

4. **部署完成後會得到一個網址**（例如 `https://xxx.streamlit.app`），把網址傳給家長即可。

### 手機上「像 App」的用法

- **iPhone**：Safari 開啟網址 → 分享 → 「加入主畫面」
- **Android**：Chrome 開啟網址 → 右上角選單 → 「加到主畫面」

之後從主畫面點圖示開啟，全螢幕、有圖示，體驗就像原生 App。

---

## 方案二：本機當伺服器（不推薦長期使用）

只適合「現場訓練時大家連同一個 Wi-Fi」的情境：

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

手機連同一個 Wi-Fi，瀏覽器輸入 `http://你電腦的區網IP:8501`（用 `ipconfig` 查 IP）。

缺點：電腦要一直開著、離開家裡 Wi-Fi 就連不上；要對外開放需要設定路由器轉埠 + 固定 IP，安全風險高。若真的想用自己的機器對外服務，建議用 **Cloudflare Tunnel** 或 **Tailscale Funnel** 取代直接開 port。

---

## 使用人數與額度

| 項目 | 免費額度 | 10 人以內夠用嗎 |
|------|---------|----------------|
| Streamlit Cloud | 1 個公開 app，資源有限 | ✅ 夠 |
| Supabase Free | 500MB DB、1GB Storage、50MB 檔案上限 | ✅ 夠，但影片久了會滿，建議定期清舊影片 |
| Gemini 免費層 | Flash 系列每日有請求數上限 | ✅ 10 人每天各傳 1 部影片沒問題 |

**之後若超過 ~30 人**再考慮：Supabase Pro（$25/月）、Gemini 付費層（Flash 很便宜）、加上正式的登入系統（Supabase Auth）。

---

## API Key 建議

**維持 Google Gemini 即可**，理由：

1. **影片動作分析**需要原生影片多模態能力，Gemini Files API 直接吃 mp4，這是目前最簡單便宜的做法
2. **免費層就涵蓋 Flash 系列**（gemini-3.5-flash），10 人規模幾乎零成本
3. 換其他家（OpenAI/Anthropic）影片要自己抽幀處理，程式會複雜很多

⚠️ 注意：`gemini-1.5-flash` **已退役**（2026 年已關閉，呼叫回 404），程式已改用 `gemini-3.5-flash`，未來若再換代只要改 `.env` 裡的 `GEMINI_MODEL` 即可，不用動程式。

API key 申請：https://aistudio.google.com/apikey （免費，用 Google 帳號登入即可）

---

## 🔐 API Key 安全守則

### 為什麼 key 不會暴露在前端

Streamlit 是**伺服器端**框架：所有 Python 程式（含 `os.getenv` 讀到的金鑰）只在伺服器上執行，瀏覽器只收到渲染結果。使用者按 F12 看原始碼、看網路請求，都看不到你的 GEMINI_API_KEY——對 Gemini 的呼叫是「伺服器 → Google」，不經過使用者的瀏覽器。

### 但仍要遵守這幾條

1. **`.env` 永遠不進 git**（.gitignore 已擋）。推上 GitHub 前用 `git status` 確認沒有 .env。萬一不小心推上去過，**直接到後台撤銷該 key 重發一把**，不要只刪 commit（歷史紀錄還在）
2. **部署用 Streamlit Cloud Secrets** 填金鑰，不要寫死在程式碼裡
3. **錯誤訊息不顯示原始 exception**（app.py 已改：細節進伺服器 log，使用者只看到通用訊息）
4. **設定 APP_PASSWORD**：網址公開後，通行碼是第一道防線，沒密碼的人連介面都進不去，自然碰不到會消耗 API 的功能
5. **設定 ADMIN_PASSWORD**：登入頁分「小選手」與「教練後台」兩種身分——學員輸名字只能看自己的頁面；新增/編輯學員與生成菜單（會消耗 API）全部鎖在教練後台。沒設 ADMIN_PASSWORD 時後台不設防，僅限本機測試
5. 到 [Google AI Studio](https://aistudio.google.com/apikey) 可為 API key 設用量上限警示，被盜用能早期發現

### Supabase 的真正風險點：RLS

`SUPABASE_ANON_KEY` 在 Streamlit 架構下同樣只在伺服器端，但它的設計本來就是「可公開」等級——真正的防線是 **Row Level Security（RLS）**。目前 MVP 若 RLS 是關閉的，任何拿到 anon key 的人都可以直接呼叫 Supabase REST API 讀寫整個資料庫。建議到 Supabase 後台為兩張表開啟 RLS：

```sql
-- 開啟 RLS 並允許 anon 完整存取（因為已有 APP_PASSWORD 擋在前面）
-- 10 人規模的務實做法；之後若加 Supabase Auth 再改成 per-user policy
ALTER TABLE students ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "app_full_access_students" ON students
  FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "app_full_access_logs" ON training_logs
  FOR ALL TO anon USING (true) WITH CHECK (true);
```

> 注意：上面的 policy 等同維持現狀的存取權（一樣是 anon 全可讀寫），主要價值是把 RLS 機制先建起來；**真正要鎖**就需要導入 Supabase Auth 登入後改成 `auth.uid()` 比對的 policy——10 人規模可先不做，超過 30 人再上。

另外 `volleyball-videos` 是 Public Bucket，知道網址的人就能看影片（網址含隨機 timestamp，不易猜中，但並非私密）。若在意小朋友影片隱私，可改成 Private Bucket + signed URL（程式需小改，要做跟我說）。

---

## 更新後的啟動步驟（本機測試）

```bash
# 1. 在 Supabase SQL Editor 重新執行 migration.sql（新增了 equipment 欄位）
# 2. 更新依賴（SDK 已從 google-generativeai 換成新版 google-genai）
pip install -r requirements.txt --upgrade
# 3. .env 補上 GEMINI_MODEL 與 APP_PASSWORD（參考 .env.example）
streamlit run app.py
```
