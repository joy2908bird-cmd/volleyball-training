-- ============================================================
-- 排球訓練小幫手 — v3 逐日完成追蹤
-- 到 Supabase 後台 → SQL Editor 貼上整份 → Run
-- ============================================================

-- training_logs 新增「第幾天」欄位，讓每一天（第1天~第5天）各自獨立記錄完成
-- 舊資料 day_number 會是 NULL（沒關係，程式有相容處理）
ALTER TABLE training_logs ADD COLUMN IF NOT EXISTS day_number INT;
