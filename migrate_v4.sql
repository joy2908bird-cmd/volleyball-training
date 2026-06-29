-- ============================================================
-- 排球訓練小幫手 — v4 每週訓練日誌
-- 到 Supabase 後台 → SQL Editor 貼上整份 → Run
-- ============================================================

-- 每週訓練日誌：一套菜單的每一週一篇（綁 plan_started_at，讓不同菜單的同週數不衝突、累積成長歷史）
CREATE TABLE IF NOT EXISTS weekly_journals (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id BIGINT REFERENCES students(id) ON DELETE CASCADE,
    plan_started_at TEXT,           -- 對應 students.plan_started_at（識別是哪一套菜單）
    week_number INT NOT NULL,
    mood TEXT,                       -- 心情（表情字串）
    content TEXT,                    -- 文字心得
    photo_url TEXT,                  -- 一張照片（選填）
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- MVP 測試期開放（與其他表一致，上線前再收緊）
ALTER TABLE weekly_journals ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "weekly_journals_allow_app_access" ON weekly_journals;
CREATE POLICY "weekly_journals_allow_app_access"
ON weekly_journals
FOR ALL
TO anon, authenticated
USING (true)
WITH CHECK (true);

-- ============================================================
-- 另外要在 Supabase Storage 建一個放日誌照片的 Bucket（手動，一次性）：
--   1. 左側 Storage → New Bucket
--   2. Name: journal-photos
--   3. Public bucket: ✅ 開啟
--   4. （可選）File size limit: 5 MB；Allowed MIME types: image/jpeg, image/png
--   5. Save
--   6. Policies → New Policy → 「Allow access to all users」(INSERT + SELECT)
-- ============================================================
