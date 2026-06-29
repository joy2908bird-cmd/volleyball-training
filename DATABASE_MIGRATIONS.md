# Database Migration Notes

這份文件先整理目前專案內的資料庫 schema / migration 狀態，方便之後部署新環境或檢查正式環境時使用。

## Current Status

- 最新 migration 檔案版本：`migrate_v8.sql`
- 正式環境目前已套用到哪一版：待確認
- 新環境目前需要手動依序執行多個 SQL 檔，容易漏跑
- 之後建議收斂成 `schema_latest.sql` 或 `migrations/` 目錄

> 注意：在確認正式環境版本前，不要直接重跑所有 SQL 到正式環境。雖然多數語法用了 `IF NOT EXISTS`，但仍應先確認目前 schema 狀態。

## Current SQL Files

| 順序 | 檔案 | 用途 |
| --- | --- | --- |
| 1 | `setup_all.sql` | 建立基礎資料表與 RLS policy，例如 `students`、`training_logs` |
| 2 | `migrate_v2.sql` | 放寬學生基本資料欄位限制，新增訓練模式、身高體重紀錄 `body_metrics` |
| 3 | `migrate_v3.sql` | 在 `training_logs` 新增 `day_number` |
| 4 | `migrate_v4.sql` | 新增每週心得 / 照片紀錄 `weekly_journals`，並記錄 `journal-photos` bucket 的手動設定 |
| 5 | `migrate_v5.sql` | 新增比賽資料表 `competitions` |
| 6 | `migrate_v6.sql` | 新增影片分析紀錄 `video_analyses` |
| 7 | `migrate_v7.sql` | 新增額外積分 / 獎勵紀錄 `point_events` |
| 8 | `migrate_v8.sql` | 新增角色養成最小版：`avatar_templates`、`avatar_profiles`、`pet_catalog`、`student_pets`，並 seed 8 位角色與 13 隻寵物 |

另有舊檔 `migration.sql`，目前看起來是早期 Supabase 初始化說明或舊版 schema。之後整理時要確認它是否仍需要保留，或改成歸檔。

## Recommended Deployment Flow For A New Environment

目前若要建立全新 Supabase 環境，暫時依序執行：

```text
setup_all.sql
migrate_v2.sql
migrate_v3.sql
migrate_v4.sql
migrate_v5.sql
migrate_v6.sql
migrate_v7.sql
migrate_v8.sql
```

同時需要手動確認 Supabase Storage bucket：

```text
volleyball-videos
journal-photos
```

Storage policy / public bucket 設定散落在 `SUPABASE_SETUP.md` 與 `migrate_v4.sql` 的註解中，之後建議一起整理。

## Next Cleanup Options

### Option A: 建立 `schema_latest.sql`

適合小型專案、部署頻率低的情境。

- 優點：新環境只要跑一份 SQL，最不容易漏
- 缺點：正式環境升級時仍需要知道從舊版到新版的差異

建議做法：

```text
schema_latest.sql       # 最新完整 schema，給全新環境使用
migrations_archive/     # 舊 migration 歷史紀錄
```

### Option B: 建立 `migrations/` 目錄

適合之後還會繼續新增功能、欄位、資料表的情境。

- 優點：版本歷史清楚，可以知道每個環境跑到哪裡
- 缺點：部署時仍需要 migration runner 或人工確認版本

建議做法：

```text
migrations/
  001_setup.sql
  002_profile_and_body_metrics.sql
  003_training_log_day_number.sql
  004_weekly_journals.sql
  005_competitions.sql
  006_video_analyses.sql
  007_point_events.sql
  008_avatar_and_pets.sql
```

README 或這份文件中固定維護：

```text
正式環境目前 schema 版本：vX
最新 schema 版本：v8
```

## Suggested Next Step

等回來確認資料庫時，建議照這個順序檢查：

1. 到 Supabase SQL Editor 查正式環境有哪些 table / column。
2. 對照上方 `Current SQL Files`，確認正式環境實際跑到哪一版。
3. 把「正式環境目前 schema 版本」補到本文件。
4. 決定要採用 `schema_latest.sql` 還是 `migrations/` 目錄。
5. 若採用 `schema_latest.sql`，從現有正式 schema 或所有 migration 合併出一份最新完整 SQL。
6. 若採用 `migrations/`，把現有 SQL 依版本重新命名，並在新增功能時只新增下一版 migration。
