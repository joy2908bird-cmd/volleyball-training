-- ============================================================
-- 排球訓練小幫手 — v5 賽事行事曆（功能 D）
-- 到 Supabase 後台 → SQL Editor 貼上整份 → Run
-- ============================================================

-- 全隊共用的賽事行事曆：教練新增比賽日期，生成菜單時據此提醒訓練階段（週期化）
CREATE TABLE IF NOT EXISTS competitions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,              -- 比賽名稱（例：XX盃少年排球賽）
    event_date DATE NOT NULL,        -- 比賽日期
    level TEXT,                      -- 重要程度（A級重點賽 / B級一般賽）
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- MVP 測試期開放（與其他表一致，上線前再收緊）
ALTER TABLE competitions DISABLE ROW LEVEL SECURITY;
