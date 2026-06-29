-- ============================================================
-- Volleyball Training Helper v8: avatar templates and pet companions
-- Run this in the Supabase SQL Editor after migrate_v7.sql.
-- ============================================================

CREATE TABLE IF NOT EXISTS avatar_templates (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    english_name TEXT,
    role_name TEXT,
    description TEXT,
    catchphrase TEXT,
    asset_path TEXT,
    active BOOLEAN NOT NULL DEFAULT FALSE,
    asset_ready BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order INT NOT NULL DEFAULT 999,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pet_catalog (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    rarity TEXT NOT NULL CHECK (rarity IN ('N', 'R', 'SR', 'SSR')),
    species_note TEXT,
    asset_path TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    asset_ready BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INT NOT NULL DEFAULT 999,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS avatar_profiles (
    student_id BIGINT PRIMARY KEY REFERENCES students(id) ON DELETE CASCADE,
    nickname TEXT,
    avatar_template_id TEXT REFERENCES avatar_templates(id),
    companion_pet_id TEXT REFERENCES pet_catalog(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS student_pets (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id BIGINT REFERENCES students(id) ON DELETE CASCADE,
    pet_id TEXT REFERENCES pet_catalog(id),
    quantity INT NOT NULL DEFAULT 1 CHECK (quantity > 0),
    source TEXT DEFAULT 'starter',
    acquired_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (student_id, pet_id)
);

CREATE INDEX IF NOT EXISTS avatar_profiles_avatar_template_id_idx
ON avatar_profiles(avatar_template_id);

CREATE INDEX IF NOT EXISTS avatar_profiles_companion_pet_id_idx
ON avatar_profiles(companion_pet_id);

CREATE INDEX IF NOT EXISTS student_pets_student_id_idx
ON student_pets(student_id);

CREATE INDEX IF NOT EXISTS student_pets_pet_id_idx
ON student_pets(pet_id);

ALTER TABLE avatar_templates ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "avatar_templates_allow_app_access" ON avatar_templates;
CREATE POLICY "avatar_templates_allow_app_access"
ON avatar_templates
FOR ALL
TO anon, authenticated
USING (true)
WITH CHECK (true);

ALTER TABLE pet_catalog ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "pet_catalog_allow_app_access" ON pet_catalog;
CREATE POLICY "pet_catalog_allow_app_access"
ON pet_catalog
FOR ALL
TO anon, authenticated
USING (true)
WITH CHECK (true);

ALTER TABLE avatar_profiles ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "avatar_profiles_allow_app_access" ON avatar_profiles;
CREATE POLICY "avatar_profiles_allow_app_access"
ON avatar_profiles
FOR ALL
TO anon, authenticated
USING (true)
WITH CHECK (true);

ALTER TABLE student_pets ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "student_pets_allow_app_access" ON student_pets;
CREATE POLICY "student_pets_allow_app_access"
ON student_pets
FOR ALL
TO anon, authenticated
USING (true)
WITH CHECK (true);

INSERT INTO avatar_templates (
    id, display_name, english_name, role_name, description, catchphrase,
    asset_path, active, asset_ready, sort_order, updated_at
) VALUES
('beginner', '活力新手', 'Energetic Beginner', '新手入門 / 全能練習生', '第一次加入排球隊，雖然技巧還在練習中，但總是第一個舉手挑戰。', '再試一次，我一定可以！', 'assets/sprites/characters/templates/beginner.png', TRUE, TRUE, 1, NOW()),
('ace', '隊長王牌', 'Captain Ace', '隊長 / 王牌攻擊手', '球隊裡可靠的小隊長，會提醒大家站位，也會鼓勵隊友不要緊張。', '大家一起來，這球我們接得起來！', 'assets/sprites/characters/templates/ace.png', TRUE, TRUE, 2, NOW()),
('libero', '冷酷自由人', 'Cool Libero', '自由球員 / 防守專家', '話不多，但總能出現在球快落地的位置。', '我看到了，這球交給我。', 'assets/sprites/characters/templates/libero.png', TRUE, TRUE, 3, NOW()),
('supporter', '陽光應援', 'Sunny Supporter', '團隊應援 / 氣氛帶動', '總是把隊伍氣氛變好，失誤時會第一個說「沒關係」。', '沒關係，我們下一球會更好！', 'assets/sprites/characters/templates/supporter.png', TRUE, TRUE, 4, NOW()),
('tech', '未來科技', 'Futuristic Tech', '科技分析 / 技巧型', '會用自己的小工具記錄發球、接球和訓練進度。', '資料顯示，我們正在變強！', 'assets/sprites/characters/templates/tech.png', TRUE, TRUE, 5, NOW()),
('setter', '速度舉球手', 'Speed Setter', '舉球員 / 節奏控制', '動作很快，總能把球送到隊友最舒服的位置。', '準備好，我把球送過去！', NULL, FALSE, FALSE, 6, NOW()),
('blocker', '強力攔網手', 'Power Blocker', '攔網 / 前排防守', '看起來很有氣勢，但其實很照顧隊友。', '這球我來擋住！', NULL, FALSE, FALSE, 7, NOW()),
('rainbow', '彩虹扣球手', 'Rainbow Smash', '扣球 / 明星型攻擊', '一登場就很吸睛，喜歡用漂亮的動作完成扣球。', '看我的彩虹扣殺！', NULL, FALSE, FALSE, 8, NOW())
ON CONFLICT (id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    english_name = EXCLUDED.english_name,
    role_name = EXCLUDED.role_name,
    description = EXCLUDED.description,
    catchphrase = EXCLUDED.catchphrase,
    asset_path = EXCLUDED.asset_path,
    active = EXCLUDED.active,
    asset_ready = EXCLUDED.asset_ready,
    sort_order = EXCLUDED.sort_order,
    updated_at = NOW();

INSERT INTO pet_catalog (
    id, display_name, rarity, species_note, asset_path,
    active, asset_ready, sort_order, updated_at
) VALUES
('pet_n_01', '球球汪', 'N', '排球項圈小狗', 'assets/sprites/pets/pet_n_01.png', TRUE, TRUE, 1, NOW()),
('pet_n_02', '啾啾雞', 'N', '穿訓練背心的小雞', 'assets/sprites/pets/pet_n_02.png', TRUE, TRUE, 2, NOW()),
('pet_n_03', '芽芽黏', 'N', '頭上長芽的黏黏球', 'assets/sprites/pets/pet_n_03.png', TRUE, TRUE, 3, NOW()),
('pet_n_04', '躍躍兔', 'N', '綁頭帶的彈跳兔', 'assets/sprites/pets/pet_n_04.png', TRUE, TRUE, 4, NOW()),
('pet_n_05', '竹團熊', 'N', '拿竹子的圓滾滾熊', 'assets/sprites/pets/pet_n_05.png', TRUE, TRUE, 5, NOW()),
('pet_n_06', '旋風狐', 'N', '帶哨子的敏捷小狐', 'assets/sprites/pets/pet_n_06.png', TRUE, TRUE, 6, NOW()),
('pet_r_01', '鋼衛熊', 'R', '守備型機械熊', 'assets/sprites/pets/pet_r_01.png', TRUE, TRUE, 7, NOW()),
('pet_r_02', '音凍凍', 'R', '耳機水母凍', 'assets/sprites/pets/pet_r_02.png', TRUE, TRUE, 8, NOW()),
('pet_r_03', '飛躍豬', 'R', '有翅膀的助跑小豬', 'assets/sprites/pets/pet_r_03.png', TRUE, TRUE, 9, NOW()),
('pet_sr_01', '扣球幼龍', 'SR', '夕陽球場幼龍', 'assets/sprites/pets/pet_sr_01.png', TRUE, TRUE, 10, NOW()),
('pet_sr_02', '星紋絨駝', 'SR', '星紋魔法絨駝', 'assets/sprites/pets/pet_sr_02.png', TRUE, TRUE, 11, NOW()),
('pet_ssr_01', '烈羽凰', 'SSR', '火焰傳說鳳凰', 'assets/sprites/pets/pet_ssr_01.png', TRUE, TRUE, 12, NOW()),
('pet_ssr_02', '極光機狼', 'SSR', '極光科技機械狼', 'assets/sprites/pets/pet_ssr_02.png', TRUE, TRUE, 13, NOW())
ON CONFLICT (id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    rarity = EXCLUDED.rarity,
    species_note = EXCLUDED.species_note,
    asset_path = EXCLUDED.asset_path,
    active = EXCLUDED.active,
    asset_ready = EXCLUDED.asset_ready,
    sort_order = EXCLUDED.sort_order,
    updated_at = NOW();

-- First release has no gacha UI yet, so each existing student gets one starter pet.
INSERT INTO student_pets (student_id, pet_id, quantity, source)
SELECT id, 'pet_n_01', 1, 'starter'
FROM students
ON CONFLICT (student_id, pet_id) DO NOTHING;
