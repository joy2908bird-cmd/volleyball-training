-- ============================================================
-- Volleyball Training Helper v9: custom avatar motto
-- Run this in the Supabase SQL Editor after migrate_v8.sql.
-- Safe for production data: adds one nullable column only.
-- ============================================================

ALTER TABLE avatar_profiles
ADD COLUMN IF NOT EXISTS motto TEXT;

