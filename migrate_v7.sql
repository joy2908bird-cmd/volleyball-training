-- ============================================================
-- Volleyball Training Helper v7: point events
-- Run this in the Supabase SQL Editor.
-- ============================================================

-- Stores bonus/manual point adjustments separately from training_logs.
-- This keeps check-in history safe and gives every bonus a reason.
CREATE TABLE IF NOT EXISTS point_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id BIGINT REFERENCES students(id) ON DELETE CASCADE,
    points INT NOT NULL,
    reason TEXT NOT NULL,
    note TEXT,
    event_type TEXT DEFAULT 'manual',
    event_key TEXT,
    created_by TEXT DEFAULT 'coach',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Prevent automatic milestone rewards from being issued more than once.
CREATE UNIQUE INDEX IF NOT EXISTS point_events_student_event_key_idx
ON point_events(student_id, event_key)
WHERE event_key IS NOT NULL;

ALTER TABLE point_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "point_events_allow_app_access" ON point_events;
CREATE POLICY "point_events_allow_app_access"
ON point_events
FOR ALL
TO anon, authenticated
USING (true)
WITH CHECK (true);

