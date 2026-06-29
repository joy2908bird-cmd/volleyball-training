-- ============================================================
-- Volleyball Training Helper v6: video analysis records
-- Run this in the Supabase SQL Editor.
-- ============================================================

-- Stores AI feedback and scores for uploaded training videos.
CREATE TABLE IF NOT EXISTS video_analyses (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id BIGINT REFERENCES students(id) ON DELETE CASCADE,
    target_skill TEXT NOT NULL,
    video_url TEXT,
    ai_feedback TEXT,
    score INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Short-term open policy to keep the current app working while RLS is enabled.
ALTER TABLE video_analyses ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "video_analyses_allow_app_access" ON video_analyses;
CREATE POLICY "video_analyses_allow_app_access"
ON video_analyses
FOR ALL
TO anon, authenticated
USING (true)
WITH CHECK (true);
