-- ============================================================
-- 排球訓練小幫手 — 新專案一次建好（複製整份貼到 Supabase SQL Editor → Run）
-- 2026-06-22 重建用
-- ============================================================

-- 1) 學員基本資料表（含 curriculum 欄位）
CREATE TABLE IF NOT EXISTS students (
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

-- 2) 每日訓練與影片紀錄表
CREATE TABLE IF NOT EXISTS training_logs (
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

-- 3) 補充欄位（器材清單、年級）
ALTER TABLE students ADD COLUMN IF NOT EXISTS equipment JSONB DEFAULT '["排球"]'::jsonb;
ALTER TABLE students ADD COLUMN IF NOT EXISTS grade_level TEXT DEFAULT '中年級（三、四年級）';

-- 4) MVP 測試期暫時關閉資料表 RLS（上線前記得重新啟用並寫 policy）
ALTER TABLE students DISABLE ROW LEVEL SECURITY;
ALTER TABLE training_logs DISABLE ROW LEVEL SECURITY;
