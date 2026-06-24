-- ============================================================
-- 補充 migration：在 students 表新增 curriculum 欄位
-- 請到 Supabase 後台 → SQL Editor 執行此腳本
-- ============================================================

ALTER TABLE students
ADD COLUMN IF NOT EXISTS curriculum JSONB;

-- 2026-06-11：新增器材欄位（家中可用的輔助器材清單）
ALTER TABLE students
ADD COLUMN IF NOT EXISTS equipment JSONB DEFAULT '["排球"]'::jsonb;

-- 2026-06-11：新增年級欄位（國小中年級/高年級，啞鈴僅限高年級）
ALTER TABLE students
ADD COLUMN IF NOT EXISTS grade_level TEXT DEFAULT '中年級（三、四年級）';

-- 確認兩張表結構（可選，執行後在 Results 面板確認）
-- SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'students';
-- SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'training_logs';
