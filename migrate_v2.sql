-- ============================================================
-- 排球訓練小幫手 — v2 角色權責重劃 + 訓練模式 + 成長追蹤
-- 到 Supabase 後台 → SQL Editor 貼上整份 → Run
-- （DB 目前 0 筆資料，可安全執行）
-- ============================================================

-- 1) 放寬 students 欄位，讓教練可建「只有名字」的空殼帳號
ALTER TABLE students ALTER COLUMN age DROP NOT NULL;
ALTER TABLE students ALTER COLUMN gender DROP NOT NULL;
ALTER TABLE students ALTER COLUMN height_cm DROP NOT NULL;
ALTER TABLE students ALTER COLUMN weight_kg DROP NOT NULL;
ALTER TABLE students ALTER COLUMN target_skill DROP NOT NULL;

-- 2) 新欄位
ALTER TABLE students ADD COLUMN IF NOT EXISTS profile_completed BOOLEAN DEFAULT FALSE;
ALTER TABLE students ADD COLUMN IF NOT EXISTS training_mode TEXT;            -- '綜合訓練（含排球）' / '身體素質強化（不帶球）'
ALTER TABLE students ADD COLUMN IF NOT EXISTS plan_started_at TIMESTAMPTZ;   -- 當前菜單起算日（取代用 created_at 算週數）

-- 3) 身高體重歷史表（成長曲線 + 兩週提醒）
CREATE TABLE IF NOT EXISTS body_metrics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id BIGINT REFERENCES students(id) ON DELETE CASCADE,
    recorded_at DATE NOT NULL DEFAULT CURRENT_DATE,
    height_cm NUMERIC NOT NULL,
    weight_kg NUMERIC NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- MVP 測試期開放（與現有 students 一致，上線前再收緊）
ALTER TABLE body_metrics DISABLE ROW LEVEL SECURITY;
