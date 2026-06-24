# Supabase 設定完整步驟

> 本文件記錄讓「排球訓練小幫手」正常運作所需的 Supabase 設定。
> 第一次部署時，請依序執行以下所有步驟。

---

## Step 1 — 建立 Supabase 專案

1. 前往 [https://supabase.com](https://supabase.com)，登入後點 **New Project**
2. 填入專案名稱（如 `volleyball-training`）、設定資料庫密碼、選擇離你最近的地區
3. 等待約 1–2 分鐘，專案建立完成

---

## Step 2 — 取得 API 金鑰

1. 進入專案後，點左側 ⚙️ **Project Settings → API**
2. 複製以下兩個值，填入你的 `.env`：

```
SUPABASE_URL    → Project URL（格式：https://xxxx.supabase.co）
SUPABASE_ANON_KEY → Project API Keys → anon public
```

---

## Step 3 — 建立資料庫資料表

前往左側 **SQL Editor**，貼上以下腳本並點 **Run**：

```sql
-- 學員基本資料表
CREATE TABLE students (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    age INT NOT NULL,
    gender TEXT NOT NULL,
    height_cm NUMERIC NOT NULL,
    weight_kg NUMERIC NOT NULL,
    target_skill TEXT NOT NULL,
    total_weeks INT NOT NULL DEFAULT 4,
    curriculum JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 每日訓練與影片紀錄表
CREATE TABLE training_logs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id BIGINT REFERENCES students(id) ON DELETE CASCADE,
    training_date DATE NOT NULL DEFAULT CURRENT_DATE,
    week_number INT NOT NULL,
    is_completed BOOLEAN NOT NULL DEFAULT FALSE,
    video_url TEXT,
    ai_feedback TEXT,
    score INT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

> 如果 `students` 表已存在但缺少 `curriculum` 欄位，執行：
> ```sql
> ALTER TABLE students ADD COLUMN IF NOT EXISTS curriculum JSONB;
> ```

---

## Step 4 — 建立 Storage Bucket

1. 點左側 **Storage**
2. 點 **New Bucket**
3. 設定如下：

| 項目 | 值 |
|------|----|
| Name | `volleyball-videos` |
| Public bucket | ✅ 開啟（讓影片可公開讀取） |
| File size limit | `50 MB` |
| Allowed MIME types | `video/mp4, video/quicktime, video/avi` |

4. 點 **Save**

---

## Step 5 — 設定 Storage RLS 政策（重要！）

> RLS（Row Level Security）控制誰能讀寫 Storage，預設是全部拒絕。
> MVP 階段使用「允許所有人」的開放政策，上線後可再收緊。

前往 **Storage → volleyball-videos → Policies**，新增以下兩條政策：

### Policy 1：允許上傳（INSERT）

```sql
-- Policy Name: Allow public uploads
-- Allowed operation: INSERT
-- Target roles: public（不選 = 全部）

CREATE POLICY "Allow public uploads"
ON storage.objects FOR INSERT
TO public
WITH CHECK (bucket_id = 'volleyball-videos');
```

### Policy 2：允許讀取（SELECT）

```sql
-- Policy Name: Allow public reads
-- Allowed operation: SELECT
-- Target roles: public

CREATE POLICY "Allow public reads"
ON storage.objects FOR SELECT
TO public
USING (bucket_id = 'volleyball-videos');
```

> 💡 你也可以直接在 Supabase Storage UI 的 Policies 頁面點「New Policy → Get started quickly → Allow access to all users」快速建立。

---

## Step 6 — 設定資料表 RLS（開發期暫時開放）

MVP 測試期間，可在 SQL Editor 執行以下腳本暫時關閉 RLS，方便開發：

```sql
-- 暫時關閉 RLS（MVP 測試用，上線前記得重新啟用）
ALTER TABLE students DISABLE ROW LEVEL SECURITY;
ALTER TABLE training_logs DISABLE ROW LEVEL SECURITY;
```

---

## 設定完成確認清單

- [ ] Supabase 專案已建立
- [ ] `.env` 已填入 `SUPABASE_URL` 與 `SUPABASE_ANON_KEY`
- [ ] `students` 資料表已建立（含 `curriculum` 欄位）
- [ ] `training_logs` 資料表已建立
- [ ] `volleyball-videos` Storage Bucket 已建立（Public）
- [ ] Storage RLS Policy 已設定（INSERT + SELECT）
- [ ] 資料表 RLS 已調整（MVP 測試期暫時關閉）
