# ============================================================
# 🏐 小朋友排球訓練小幫手 — MVP v1.0
# Tech Stack: Streamlit + Gemini API + Supabase
# ============================================================

import os
import json
import time
import random
import tempfile
from datetime import datetime, date

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from supabase import create_client, Client
from google import genai
from google.genai import types as genai_types
from google.genai import errors as genai_errors
from dotenv import load_dotenv

load_dotenv()

# ── 環境變數 ─────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")  # 1.5 系列已退役，預設用現行穩定版
# 主模型塞車（503）時依序改用的備援模型，皆支援 JSON 輸出與影片分析；可用 .env 覆寫（逗號分隔）
# 註：gemini-2.0-flash 免費層額度為 0（limit:0），不可當備援，已移除。
GEMINI_MODEL_FALLBACKS = [
    m.strip() for m in os.getenv(
        "GEMINI_MODEL_FALLBACKS", "gemini-2.5-flash"
    ).split(",") if m.strip()
]
APP_PASSWORD = os.getenv("APP_PASSWORD", "")  # 上線後的簡易通行碼，留空 = 不啟用
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")  # 教練後台密碼（新增/編輯學員、生成菜單）
BUCKET_NAME = "volleyball-videos"
JOURNAL_BUCKET = "journal-photos"  # 訓練日誌照片（需在 Supabase 另建此 public bucket，見 migrate_v4.sql）

# ── 訓練日誌心情選項 ──────────────────────────────────────────
JOURNAL_MOODS = ["😄 超開心", "💪 有成就感", "😊 還不錯", "😐 普通", "😓 有點累", "😣 有點挫折"]

# ── 訓練器材清單（註冊表單與 AI prompt 共用） ─────────────────
EQUIPMENT_OPTIONS = ["排球", "沙球", "藥球", "彈力繩", "跳繩", "啞鈴", "角錐/標誌盤", "牆壁（對牆練習）"]

# ── 訓練模式（生成菜單時選擇） ────────────────────────────────
TRAINING_MODE_BALL = "綜合訓練（含排球）"      # 排球技巧為主，含影片分析
TRAINING_MODE_FITNESS = "身體素質強化（不帶球）"  # 純體能基礎，不含影片分析
TRAINING_MODES = [TRAINING_MODE_BALL, TRAINING_MODE_FITNESS]
TARGET_SKILLS = ["低手墊球（接球）", "高手傳球", "扣球步法", "發球練習", "防守移位", "綜合訓練"]

# ── 頁面設定（必須在最前面） ──────────────────────────────────
st.set_page_config(
    page_title="🏐 排球訓練小幫手",
    page_icon="🏐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 全域 CSS ─────────────────────────────────────────────────
st.markdown("""
<style>
    .stProgress > div > div > div > div { background-color: #FF6B35; }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 12px; padding: 16px; color: white; text-align: center;
    }
    .feedback-card {
        background: #f0f9ff; border-left: 4px solid #0ea5e9;
        border-radius: 8px; padding: 16px; margin: 8px 0;
    }
</style>
""", unsafe_allow_html=True)

# ── 初始化客戶端（快取，只建立一次） ─────────────────────────
@st.cache_resource
def init_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("❌ 請先在 .env 設定 SUPABASE_URL 與 SUPABASE_ANON_KEY")
        st.stop()
    return create_client(SUPABASE_URL, SUPABASE_KEY)

@st.cache_resource
def init_gemini() -> genai.Client:
    if not GEMINI_API_KEY:
        st.error("❌ 請先在 .env 設定 GEMINI_API_KEY")
        st.stop()
    return genai.Client(api_key=GEMINI_API_KEY)

supabase = init_supabase()
gemini_client = init_gemini()


# ── 簡易通行碼（部署上線後避免陌生人使用） ────────────────────
def check_password() -> bool:
    """若有設定 APP_PASSWORD，要求輸入通行碼才能使用。"""
    if not APP_PASSWORD:
        return True
    if st.session_state.get("authed"):
        return True

    st.markdown("# 🏐 排球訓練小幫手")
    pwd = st.text_input("請輸入通行碼", type="password")
    if st.button("進入", type="primary"):
        if pwd == APP_PASSWORD:
            st.session_state.authed = True
            st.rerun()
        else:
            st.error("通行碼錯誤，請再試一次。")
    return False


def get_student_by_name(name: str) -> dict | None:
    """以名字查詢學員（學員登入用）"""
    result = supabase.table("students").select("*").eq("name", name).execute()
    return result.data[0] if result.data else None


def _set_current_student(student: dict) -> None:
    """設定目前學員與其菜單到 session"""
    st.session_state.current_student = student
    curriculum_raw = student.get("curriculum")
    if isinstance(curriculum_raw, str):
        st.session_state.curriculum = json.loads(curriculum_raw)
    elif isinstance(curriculum_raw, dict):
        st.session_state.curriculum = curriculum_raw
    else:
        st.session_state.curriculum = None


def render_login():
    """身分選擇頁：學員輸入名字進入自己的頁面；教練輸入後台密碼管理全部。"""
    st.markdown("# 🏐 排球訓練小幫手")
    st.markdown("")

    tab_student, tab_coach = st.tabs(["👦 我是小選手", "🎓 教練後台"])

    with tab_student:
        st.markdown("輸入你的名字，開始今天的訓練吧！")
        name = st.text_input("你的名字", placeholder="例：小明", key="login_name")
        if st.button("🏐 開始訓練！", type="primary", use_container_width=True):
            student = get_student_by_name(name.strip())
            if student is None:
                st.error("找不到這個名字，請確認有沒有打錯字，或請教練先幫你建立資料。")
            else:
                st.session_state.role = "student"
                _set_current_student(student)
                st.rerun()

    with tab_coach:
        if not ADMIN_PASSWORD:
            st.caption("（尚未設定 ADMIN_PASSWORD，本機測試模式：直接按進入即可。上線前務必設定！）")
        pwd = st.text_input("後台密碼", type="password", key="login_admin_pwd")
        if st.button("進入後台", use_container_width=True):
            if not ADMIN_PASSWORD or pwd == ADMIN_PASSWORD:
                st.session_state.role = "admin"
                st.rerun()
            else:
                st.error("密碼錯誤。")


# ══════════════════════════════════════════════════════════════
# 資料庫操作函式
# ══════════════════════════════════════════════════════════════

def get_all_students() -> list[dict]:
    """取得所有學員（按建立時間排序）"""
    result = supabase.table("students").select("*").order("created_at").execute()
    return result.data or []


def create_student_shell(name: str) -> dict:
    """教練端：建立只有名字的空殼帳號（學生首登再完善資料）"""
    result = supabase.table("students").insert(
        {"name": name, "profile_completed": False}
    ).execute()
    return result.data[0]


def delete_student(student_id: int) -> None:
    """刪除學員。training_logs 與 body_metrics 設有 ON DELETE CASCADE，會一併刪除。"""
    supabase.table("students").delete().eq("id", student_id).execute()


def complete_student_profile(
    student_id: int, age: int, gender: str, grade_level: str,
    height_cm: float, weight_kg: float, equipment: list[str],
) -> dict:
    """學生（家長陪同）完善身體資料，並寫入第一筆身高體重歷史"""
    data = {
        "age": age, "gender": gender, "grade_level": grade_level,
        "height_cm": height_cm, "weight_kg": weight_kg,
        "equipment": equipment, "profile_completed": True,
    }
    result = supabase.table("students").update(data).eq("id", student_id).execute()
    record_body_metric(student_id, height_cm, weight_kg)
    return result.data[0]


def record_body_metric(student_id: int, height_cm: float, weight_kg: float) -> None:
    """記錄一筆身高體重歷史，並同步更新 students 的最新值"""
    supabase.table("body_metrics").insert({
        "student_id": student_id,
        "recorded_at": date.today().isoformat(),
        "height_cm": height_cm, "weight_kg": weight_kg,
    }).execute()
    supabase.table("students").update(
        {"height_cm": height_cm, "weight_kg": weight_kg}
    ).eq("id", student_id).execute()


def get_body_metrics(student_id: int) -> list[dict]:
    """取得身高體重歷史（依日期排序，給成長曲線）"""
    result = (
        supabase.table("body_metrics")
        .select("*")
        .eq("student_id", student_id)
        .order("recorded_at")
        .execute()
    )
    return result.data or []


def days_since_last_metric(student_id: int) -> int | None:
    """距上次身高體重紀錄幾天（無紀錄回 None），判斷兩週提醒用"""
    metrics = get_body_metrics(student_id)
    if not metrics:
        return None
    last = date.fromisoformat(metrics[-1]["recorded_at"])
    return (date.today() - last).days


def save_curriculum(
    student_id: int, curriculum: dict,
    training_mode: str, total_weeks: int,
    target_skill: str | None,
) -> None:
    """儲存 AI 生成的菜單，並記錄模式、目標技巧、週數與起算日（每套菜單從現在重新數週）"""
    supabase.table("students").update({
        "curriculum": curriculum,
        "training_mode": training_mode,
        "target_skill": target_skill,  # 體能模式為 None；含球模式存所選技巧（影片分析會用到）
        "total_weeks": total_weeks,
        "plan_started_at": datetime.now().astimezone().isoformat(),
    }).eq("id", student_id).execute()


def update_curriculum_json(student_id: int, curriculum: dict) -> None:
    """只更新菜單內容（手動微調用），不動模式/週數/起算日。"""
    supabase.table("students").update(
        {"curriculum": curriculum}
    ).eq("id", student_id).execute()


def get_training_logs(student_id: int) -> list[dict]:
    """取得學員所有訓練紀錄"""
    result = (
        supabase.table("training_logs")
        .select("*")
        .eq("student_id", student_id)
        .order("training_date")
        .execute()
    )
    return result.data or []


def get_session_log(student_id: int, week_number: int, day_number: int) -> dict | None:
    """取得某一天（第 week 週第 day 天）的訓練紀錄（若已完成過）"""
    result = (
        supabase.table("training_logs")
        .select("*")
        .eq("student_id", student_id)
        .eq("week_number", week_number)
        .eq("day_number", day_number)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data[0] if result.data else None


def create_session_log(student_id: int, week_number: int, day_number: int) -> dict:
    """建立某一天的打卡紀錄（基礎 10 分），記錄是第幾週第幾天"""
    data = {
        "student_id": student_id,
        "training_date": date.today().isoformat(),
        "week_number": week_number,
        "day_number": day_number,
        "is_completed": True,
        "score": 10,
    }
    result = supabase.table("training_logs").insert(data).execute()
    return result.data[0]


def update_training_log(
    log_id: int, video_url: str | None,
    ai_feedback: str, score: int,
) -> dict:
    """更新訓練紀錄（補上影片網址、AI 回饋、分數）"""
    data = {
        "video_url": video_url,
        "ai_feedback": ai_feedback,
        "score": score,
        "is_completed": True,
    }
    result = supabase.table("training_logs").update(data).eq("id", log_id).execute()
    return result.data[0]


def upload_video_to_supabase(student_id: int, video_bytes: bytes, filename: str) -> str:
    """上傳影片至 Supabase Storage，回傳公開網址"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"{student_id}/{timestamp}_{filename}"
    supabase.storage.from_(BUCKET_NAME).upload(
        path, video_bytes, file_options={"content-type": "video/mp4"}
    )
    return supabase.storage.from_(BUCKET_NAME).get_public_url(path)


def upload_journal_photo(student_id: int, image_bytes: bytes, filename: str) -> str:
    """上傳日誌照片至 Supabase Storage（journal-photos bucket），回傳公開網址"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = (filename.rsplit(".", 1)[-1] or "jpg").lower()
    ctype = "image/png" if ext == "png" else "image/jpeg"
    path = f"{student_id}/{timestamp}_{filename}"
    supabase.storage.from_(JOURNAL_BUCKET).upload(
        path, image_bytes, file_options={"content-type": ctype}
    )
    return supabase.storage.from_(JOURNAL_BUCKET).get_public_url(path)


# ── 每週訓練日誌 ──────────────────────────────────────────────

def get_journal(student_id: int, plan_key: str, week_number: int) -> dict | None:
    """取得某套菜單某一週的訓練日誌（若已寫過）"""
    result = (
        supabase.table("weekly_journals")
        .select("*")
        .eq("student_id", student_id)
        .eq("plan_started_at", plan_key)
        .eq("week_number", week_number)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data[0] if result.data else None


def upsert_journal(
    student_id: int, plan_key: str, week_number: int,
    mood: str, content: str, photo_url: str | None,
) -> None:
    """新增或更新某一週的訓練日誌（一套菜單一週一篇）"""
    existing = get_journal(student_id, plan_key, week_number)
    data = {
        "mood": mood, "content": content, "photo_url": photo_url,
        "updated_at": datetime.now().astimezone().isoformat(),
    }
    if existing:
        supabase.table("weekly_journals").update(data).eq("id", existing["id"]).execute()
    else:
        data.update({
            "student_id": student_id, "plan_started_at": plan_key,
            "week_number": week_number,
        })
        supabase.table("weekly_journals").insert(data).execute()


def get_all_journals(student_id: int) -> list[dict]:
    """取得學員所有訓練日誌（依時間排序，給回顧與未來匯出成長日記用）"""
    result = (
        supabase.table("weekly_journals")
        .select("*")
        .eq("student_id", student_id)
        .order("created_at")
        .execute()
    )
    return result.data or []


# ══════════════════════════════════════════════════════════════
# Gemini AI 函式
# ══════════════════════════════════════════════════════════════

class GeminiBusyError(Exception):
    """Gemini 伺服器暫時過載（503/UNAVAILABLE），重試後仍失敗時拋出。"""


def gemini_generate(status_cb=None, **kwargs):
    """
    包裝 gemini_client.models.generate_content，遇到暫時性錯誤時自動重試：
    - 503 UNAVAILABLE / 500：Google 伺服器忙（與你的額度無關）
    - 429 RESOURCE_EXHAUSTED：超過速率/額度限制

    機制：每個模型「指數退避 + 隨機抖動」重試數次；若主模型持續過載，
    自動改用備援模型（GEMINI_MODEL_FALLBACKS）—— 不同模型負載不同，大幅降低全卡住的機率。
    所有模型都試完仍失敗 → 拋 GeminiBusyError 顯示友善提示。
    非過載類錯誤（如 400 請求格式、401/403 金鑰問題）會原樣往上拋，不會被誤判成「太忙」。

    status_cb：可選的回報函式 status_cb(attempt, max_attempts, wait)，
    每次重試前呼叫，讓 UI 能即時顯示「正在多試幾次」而非看起來像當掉。
    """
    RETRYABLE = {429, 500, 503}
    primary = kwargs.pop("model", GEMINI_MODEL)
    # 模型清單：主模型 + 備援（去重、保序）
    models = [primary] + [m for m in GEMINI_MODEL_FALLBACKS if m != primary]
    max_attempts = 3  # 每個模型最多試 3 次（有備援，不必在單一模型上耗太久）
    last_exc = None

    for mi, model in enumerate(models):
        is_fallback = mi > 0
        for attempt in range(1, max_attempts + 1):
            try:
                if is_fallback:
                    print(f"[INFO] 改用備援模型 {model}（第 {attempt} 次）")
                return gemini_client.models.generate_content(model=model, **kwargs)
            # 同時涵蓋 ServerError(5xx) 與 ClientError(4xx，429 屬此類) 的基底類別
            except genai_errors.APIError as e:
                code = getattr(e, "code", None) or getattr(e, "status_code", None)
                if code not in RETRYABLE:
                    raise  # 金鑰錯誤、請求格式錯誤等 → 原樣拋出，交給上層處理
                last_exc = e
                if attempt < max_attempts:
                    wait = min(2 ** attempt, 12) + random.uniform(0, 1)  # 指數退避 + 抖動
                    print(f"[WARN] 模型 {model} 回 {code}，第 {attempt}/{max_attempts} 次，{wait:.1f}s 後重試")
                    if status_cb:
                        try:
                            status_cb(attempt, max_attempts, wait)
                        except Exception:
                            pass  # UI 回報失敗不影響重試本身
                    time.sleep(wait)
                    continue
                # 這個模型試完仍失敗 → 換下一個備援模型（若還有）
                if mi < len(models) - 1:
                    print(f"[WARN] 模型 {model} 持續過載，改用下一個備援模型")
                break

    print(f"[ERROR] 主模型與所有備援模型皆過載: {last_exc}")
    raise GeminiBusyError(
        "AI 教練現在太忙了（Google 伺服器繁忙），請過 1～2 分鐘再試一次 🙏"
    ) from last_exc


# 兩種模式共用的靜態 prompt 區塊（純字串，內含真實大括號，勿改成 f-string）
_GRADE_RULES = """【依年級分級的設計原則（對象為國小生）】
- 中年級（三、四年級）：以基本動作分解與協調為主，體能用自體重與遊戲化方式，單次 15–20 分鐘，**不使用啞鈴**
- 高年級（五、六年級）：完整動作練習 + 輕負重體能，單次 20–30 分鐘，可使用啞鈴（限 1.5 kg 起步，熟練後才用 3 kg，高次數低重量）
- 若體重相對身高偏重，多安排低衝擊訓練（牆壁練習、彈力繩），減少連續跳躍量
- 若身高較高，加強步法與協調；力量相對較小的學員多用沙球、彈力繩建立基礎"""

_EQUIPMENT_RULES = """【器材使用守則（只能使用上面列出的器材，重量規格固定如下）】
- 沙球（12 磅）：不限年級。手感與手臂穩定練習，也可做雙手持球的核心輔助，避免單手高舉過頭
- 藥球（2 kg）：不限年級。核心與爆發力，如雙手胸前推、轉體傳遞、雙手過頭擲
- 彈力繩：肩部熱身、揮臂阻力、低衝擊力量訓練
- 跳繩：腳步敏捷與彈跳耐力，安排在熱身或體能日
- 啞鈴（1.5 kg 與 3 kg 兩種）：**僅限高年級**。從 1.5 kg 開始、高次數低重量；中年級一律改用自體重或彈力繩
- 角錐/標誌盤：移位、步法路線、敏捷折返
- 牆壁：對牆練習、獨自練習的好幫手"""

_STRUCTURE_RULES = """【課表結構要求】
- 每個「訓練日」請拆成 3–6 個具體「訓練項目」放進 items 陣列，讓小朋友一眼看清楚今天要做哪幾項
- 每個項目一定要標明做法，二選一：
  - 計次型 mode="reps"：填 reps（每組次數）與 sets（組數），例如 15 下 × 3 組（適合墊球、傳球、深蹲、開合跳次數等可數動作）
  - 計時型 mode="time"：填 seconds（秒數），例如熱身、棒式、定時對牆練習、收操伸展（適合用時間衡量的動作）
- 每個訓練日的 items 必須依序包含三段：①第 1 項熱身（計時 60–120 秒）②中間 1–4 項主練習（圍繞當日主題，計次或計時）③最後 1 項收操伸展（計時 60–120 秒）
- 每個項目要有：name（簡短任務名）、mode、對應的 reps+sets 或 seconds、equipment（用到的器材陣列，沒有就空陣列）、note（一句國小生看得懂的動作提醒）
- 每個訓練日填 focus（今天主題一句話）與 duration_min（預估總分鐘，約等於所有項目時間總和）
- 數量與強度依年級與體型調整，難度逐週提升，每週主題明確
- 每週安排 5 個訓練日（週一至週五），第 6、7 天為休息日（is_rest=true，items 給空陣列，改用 task 寫一句休息建議）
- 每天附一句 tip「小叮嚀」：訓練日輪流給「訓練安全、休息恢復、飲食營養」三類叮嚀（例：練完 30 分鐘內喝牛奶或吃點蛋白質、睡滿 9 小時、訓練前 1 小時不要吃太飽、多喝水少含糖飲料）；休息日的 tip 以恢復與飲食為主。語氣親切、講給小朋友和家長聽
- 每週額外附一句 parent_note「家長小提醒」：用親切口吻提醒家長這週可以怎麼陪伴、觀察孩子的哪個重點、或如何鼓勵"""

_CURRICULUM_JSON_SCHEMA = """⚠️ 請「只」回傳以下 JSON，不要加入任何說明文字（items 內的 reps/sets 與 seconds 二擇一填寫，依 mode 而定）：
{
  "weeks": [
    {
      "week": 1,
      "focus": "本週訓練主題",
      "parent_note": "給家長的一句陪伴提醒",
      "days": [
        {
          "day": 1, "day_name": "週一", "is_rest": false, "duration_min": 20,
          "focus": "今天主題（一句話）",
          "items": [
            {"name": "開合跳熱身", "mode": "time", "seconds": 60, "equipment": [], "note": "輕鬆跳，把身體活動開"},
            {"name": "對牆低手墊球", "mode": "reps", "reps": 15, "sets": 3, "equipment": ["排球", "牆壁（對牆練習）"], "note": "手臂打直夾緊，用前臂接球"},
            {"name": "收操伸展", "mode": "time", "seconds": 90, "equipment": [], "note": "拉拉手臂和腿，慢慢深呼吸"}
          ],
          "tip": "訓練/休息/飲食小叮嚀"
        },
        {"day": 6, "day_name": "週六", "is_rest": true, "duration_min": 10, "items": [], "task": "輕鬆伸展放鬆，讓身體休息", "tip": "休息恢復小叮嚀"},
        {"day": 7, "day_name": "週日", "is_rest": true, "duration_min": 0, "items": [], "task": "完全休息，和家人一起享受假日！", "tip": "飲食營養小叮嚀"}
      ]
    }
  ]
}"""


def generate_curriculum(
    student: dict, training_mode: str,
    target_skill: str | None, total_weeks: int,
    status_cb=None,
) -> dict:
    """
    呼叫 Gemini，依學員資料與所選訓練模式生成結構化週訓練菜單（JSON 輸出）。
    - 綜合訓練（含排球）：圍繞目標技巧 target_skill 的排球菜單
    - 身體素質強化（不帶球）：純體能基礎，不含任何持球/排球技術
    兩種模式輸出相同 JSON schema，下游渲染不需區分。
    """
    equipment = student.get("equipment") or ["排球"]
    equipment_str = "、".join(equipment)
    grade_level = student.get("grade_level") or "中年級（三、四年級）"
    bmi = round(student["weight_kg"] / ((student["height_cm"] / 100) ** 2), 1)

    profile = f"""【學員資料】
- 姓名：{student['name']}
- 年級：{grade_level}
- 年齡：{student['age']} 歲
- 性別：{student['gender']}
- 身高：{student['height_cm']} cm
- 體重：{student['weight_kg']} kg（BMI 約 {bmi}，請依體型調整跑跳量與負重）
- 訓練週期：{total_weeks} 週
- 可用器材：{equipment_str}"""

    if training_mode == TRAINING_MODE_FITNESS:
        intro = "你是一位專業的國小體能教練，具備兒童動作發展知識。請設計一份**不使用排球**的身體素質強化計畫，幫小球員打好運動底子。"
        focus_rules = """【訓練目標：身體素質強化（不帶球）】
- **完全不安排任何持球或排球技術動作**
- 五大素質均衡發展：①敏捷與腳步 ②協調與平衡 ③適齡肌力（以核心、自體重為主）④彈跳與爆發 ⑤柔軟度與伸展
- 以遊戲化、循序漸進方式進行，避免單調；每週聚焦不同素質但保持均衡
- 主練習可善用跳繩、彈力繩、角錐、藥球/沙球（當作負重或目標物），絕不做排球技巧"""
    else:
        intro = "你是一位專業的國小排球教練，具備兒童體能發展知識。請設計一份完整、有趣、適齡的排球訓練計畫。"
        skills_list = parse_skills(target_skill)
        if len(skills_list) > 1:
            skills_clause = (
                f"主攻技巧有多項：{target_skill}。\n"
                "- 主練習要涵蓋以上「所有」技巧，分散在不同訓練日輪流安排，讓每項都有練到\n"
                "- 同一天可聚焦 1–2 項技巧，整週下來各項都均衡"
            )
        else:
            skills_clause = (
                f"主攻技巧「{target_skill}」。\n"
                f"- 主練習必須圍繞目標技巧「{target_skill}」循序漸進"
            )
        focus_rules = f"""【訓練目標：綜合訓練（含排球）】
- {skills_clause}
- 並穿插 1–2 天體能/器材輔助日；球感與基本動作分解優先，再進階到完整技術"""

    prompt = (
        intro + "\n\n" + profile + "\n\n" + _GRADE_RULES + "\n\n"
        + _EQUIPMENT_RULES + "\n\n" + focus_rules + "\n\n" + _STRUCTURE_RULES
        + "\n\n" + _CURRICULUM_JSON_SCHEMA
        + f"\n\n請生成完整的 {total_weeks} 週計畫。"
    )

    response = gemini_generate(
        status_cb=status_cb,
        model=GEMINI_MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json"
        ),
    )
    return json.loads(response.text)


# 各技巧的動作檢核點（給 AI 分析影片時逐項對照）
SKILL_CHECKPOINTS: dict[str, str] = {
    "低手墊球（接球）": """
1. 準備姿勢：雙腳與肩同寬、膝蓋微彎、重心放低、雙眼盯球
2. 手型：雙手交疊互握、手臂打直夾緊形成平台、手腕下壓
3. 擊球點：在腰部以下、用前臂（不是手腕或手掌）擊球
4. 發力：靠腿部蹬地與身體上送，而不是甩手臂
5. 落點控制：球的軌跡是否穩定向上、向目標方向""",
    "高手傳球": """
1. 準備姿勢：雙手抬至額頭前上方、手指張開呈球形、手肘自然外張
2. 擊球點：額頭正上方，雙眼透過雙手看球
3. 手指觸球：用十指指腹彈球，不是手掌拍球
4. 全身協調：膝蓋彎曲後伸展，力量由下而上傳遞
5. 球的旋轉與軌跡是否平穩""",
    "發球練習": """
1. 站姿：兩腳前後站、側身對網、重心在後腳
2. 拋球：拋球高度穩定、落點在擊球手前上方，不可忽高忽低
3. 揮臂：手臂伸直由後向前揮、用掌跟或全掌擊球的中下部
4. 重心轉移：擊球瞬間重心由後腳轉到前腳
5. 擊球後的隨揮動作是否完整""",
    "扣球步法": """
1. 助跑節奏：是否有「一大步＋併步」的二步或三步助跑節奏
2. 起跳：雙腳起跳、雙臂由後往前上方擺動帶動跳躍
3. 空中姿勢：挺胸展腹、引臂（手肘抬高、手在耳後）
4. 擊球：在最高點、伸直手臂、手掌包覆球的中上部、有甩腕
5. 落地：雙腳屈膝緩衝落地，保持平衡（這點對兒童安全特別重要）""",
    "防守移位": """
1. 防守姿勢：重心低、雙手在身前準備
2. 移動步法：滑步/交叉步是否正確、移動中保持低重心
3. 是否先移動到位再做接球動作
4. 判斷與反應速度
5. 接球後是否快速回到準備姿勢""",
    "綜合訓練": """
1. 基本準備姿勢與重心
2. 動作的完整性與連貫性
3. 手型與擊球點是否正確
4. 腳步移動與身體協調
5. 動作節奏與專注度""",
}


def parse_skills(target_skill: str | None) -> list[str]:
    """把以「、」串起的技巧字串拆回清單（相容舊的單一技巧字串）"""
    if not target_skill:
        return []
    return [s for s in target_skill.split("、") if s]


def get_skill_checkpoints(target_skill: str | None) -> str:
    """依目標技巧取得檢核點，找不到（或未指定）時用綜合訓練版本"""
    if not target_skill:
        return SKILL_CHECKPOINTS["綜合訓練"]
    for key, val in SKILL_CHECKPOINTS.items():
        if key in target_skill or target_skill in key:
            return val
    return SKILL_CHECKPOINTS["綜合訓練"]


def analyze_video(video_bytes: bytes, target_skill: str, student_name: str, status_cb=None) -> dict:
    """
    將影片上傳至 Gemini Files API，依技巧分項檢核點進行多模態分析，
    回傳充滿溫度的兒童教練 JSON 回饋。
    """
    # 1. 將影片暫存到本地再上傳給 Gemini
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(video_bytes)
        tmp_path = tmp.name

    video_file = None
    try:
        video_file = gemini_client.files.upload(file=tmp_path)

        # 2. 等待 Gemini 處理完成（最多等 60 秒）
        max_wait_sec = 60
        elapsed = 0
        while video_file.state.name == "PROCESSING" and elapsed < max_wait_sec:
            time.sleep(3)
            video_file = gemini_client.files.get(name=video_file.name)
            elapsed += 3

        if video_file.state.name != "ACTIVE":
            raise RuntimeError(f"Gemini 影片處理失敗，狀態：{video_file.state.name}")

        # 3. 送出多模態分析請求（帶入該技巧的分項檢核點）
        checkpoints = get_skill_checkpoints(target_skill)
        prompt = f"""你是 {student_name} 小朋友的專屬排球應援教練！🏐🎉

請仔細觀看這段練習「{target_skill}」的短片，並依照下面的「動作檢核點」逐項觀察，
再用充滿鼓勵、溫暖的語氣給出教練回饋。
回饋對象是小朋友，請用簡單易懂的中文，讓他們看了會開心又有動力繼續練習！

【{target_skill} 動作檢核點】{checkpoints}

評分標準（滿分 100）：
- 動作完成度（40 分）：是否有嘗試完成正確動作
- 努力與專注度（30 分）：認真程度、重複次數
- 姿勢正確性（30 分）：對照上面檢核點逐項評估

【回饋要求】
- strengths 與 improvements 必須對應具體的檢核點（例如「手臂平台很穩」「擊球點可以再低一點」）
- checkpoint_results 請對每一個檢核點給出 ✅ 做得好 / 🔧 再加油 的簡短評語
- drill_suggestion 請給一個在家就能做、針對最需要加強之處的小練習（可使用沙球/彈力繩/牆壁等簡單器材）

⚠️ 請「只」回傳以下 JSON，不要加入任何說明文字：
{{
  "score": 85,
  "greeting": "哇！{student_name}，你今天練習得超認真！",
  "strengths": ["對應檢核點的具體優點1", "具體優點2"],
  "improvements": ["用鼓勵語氣提出的具體改進建議1", "建議2"],
  "checkpoint_results": [
    {{"item": "檢核點名稱", "status": "✅", "comment": "簡短評語"}},
    {{"item": "檢核點名稱", "status": "🔧", "comment": "簡短評語"}}
  ],
  "drill_suggestion": "一個針對弱點、在家可做的小練習（含次數）",
  "encouragement": "一句充滿力量、讓小朋友想繼續練習的鼓勵話語",
  "fun_fact": "一個有趣的排球小知識，讓小朋友對排球更有興趣"
}}"""

        response = gemini_generate(
            status_cb=status_cb,
            model=GEMINI_MODEL,
            contents=[video_file, prompt],
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json"
            ),
        )
        return json.loads(response.text)

    finally:
        # 4. 清理：刪除本地暫存檔 & Gemini 上的檔案
        os.unlink(tmp_path)
        if video_file is not None:
            try:
                gemini_client.files.delete(name=video_file.name)
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════
# 工具函式
# ══════════════════════════════════════════════════════════════

DAYS_PER_WEEK = 5  # 每週 5 個訓練日


def completed_sessions(logs: list[dict]) -> int:
    """
    已完成的「不同訓練日」數量（自我配速進度依據，與日曆無關）。
    以 (週, 天) 去重，避免同一天重複打卡被重算；舊資料無 day_number 則各算一次。
    """
    done = set()
    legacy = 0
    for l in logs:
        if not l.get("is_completed"):
            continue
        d = l.get("day_number")
        if d is None:
            legacy += 1
        else:
            done.add((l.get("week_number"), d))
    return len(done) + legacy


def is_session_done(logs: list[dict], week_number: int, day_number: int) -> bool:
    """指定的某一天是否已完成（給菜單卡片判斷打勾用）"""
    return any(
        l.get("is_completed")
        and l.get("week_number") == week_number
        and l.get("day_number") == day_number
        for l in logs
    )


def calculate_current_week(student: dict, logs: list[dict]) -> int:
    """
    目前進行到第幾週 —— 改用「完成次數」推算，不綁日曆。
    每做完 5 次進下一週；禮拜幾開始、中間跳過幾天都沒關係，照自己的進度走。
    """
    total_weeks = student.get("total_weeks") or 1
    week = completed_sessions(logs) // DAYS_PER_WEEK + 1
    return max(1, min(week, total_weeks))


def is_plan_finished(student: dict, logs: list[dict]) -> bool:
    """整套菜單是否已完成（做完所有週 × 5 次）"""
    total_weeks = student.get("total_weeks") or 0
    return completed_sessions(logs) >= total_weeks * DAYS_PER_WEEK


def calculate_stats(student: dict, logs: list[dict]) -> dict:
    """計算訓練統計數字"""
    total_training_days = (student.get("total_weeks") or 1) * DAYS_PER_WEEK  # 每週 5 個訓練日
    completed_n = completed_sessions(logs)  # 以 (週,天) 去重的完成天數
    videos = [l for l in logs if l.get("video_url")]
    total_score = sum(l.get("score") or 0 for l in logs)
    progress_pct = min(completed_n / total_training_days * 100, 100) if total_training_days else 0

    return {
        "completed_days": completed_n,
        "total_training_days": total_training_days,
        "progress_pct": progress_pct,
        "total_score": total_score,
        "video_count": len(videos),
    }


def parse_ai_feedback(raw: str | dict | None) -> dict | None:
    """安全地解析 AI 回饋（可能是 JSON 字串或已解析的 dict）"""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


# ══════════════════════════════════════════════════════════════
# UI 元件
# ══════════════════════════════════════════════════════════════

def render_add_student_shell():
    """教練端：只填名字建立空殼帳號（身體資料由學生家長自己填）"""
    st.markdown("## 👶 新增小選手（建立名冊）")
    st.info(
        "教練只需建立小朋友的「名字」。身高、體重、家裡器材等資料，"
        "請小朋友與家長自己登入後填寫 🙌"
    )
    with st.form("add_student_shell", clear_on_submit=True):
        name = st.text_input("👦 小朋友姓名", placeholder="例：小明")
        submitted = st.form_submit_button(
            "✨ 建立帳號", use_container_width=True, type="primary"
        )
    if submitted:
        if not name.strip():
            st.error("請輸入小朋友的姓名！")
            return
        if get_student_by_name(name.strip()):
            st.error(f"已經有「{name.strip()}」這個名字了，請換一個（避免重名）。")
            return
        student = create_student_shell(name.strip())
        st.success(f"🎉 已建立「{student['name']}」！請小朋友用這個名字登入，和家長一起填資料。")
        st.balloons()


def render_profile_form(student: dict, is_edit: bool = False):
    """
    學生（家長陪同）完善 / 教練維護 身體資料表單。
    is_edit=True 時為教練後台的編輯模式（會預填現有值）。
    """
    if not is_edit:
        st.markdown(f"## 👋 {student['name']}，先和爸爸媽媽一起填資料吧！")
        st.info("填好這些，AI 教練才能幫你量身打造訓練菜單喔 🏐")

    s = student
    with st.form(f"profile_form_{s['id']}", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            grade_options = ["中年級（三、四年級）", "高年級（五、六年級）"]
            grade_idx = grade_options.index(s["grade_level"]) if s.get("grade_level") in grade_options else 0
            grade_level = st.selectbox(
                "🏫 年級", grade_options, index=grade_idx,
                help="高年級才會安排啞鈴訓練（1.5kg / 3kg）",
            )
            age = st.number_input(
                "🎂 年齡（歲）", min_value=8, max_value=13, value=int(s.get("age") or 10)
            )
            gender = st.selectbox(
                "⚧ 性別", ["男生", "女生"],
                index=0 if (s.get("gender") or "男生") == "男生" else 1,
            )
        with col2:
            height_cm = st.number_input(
                "📏 身高（cm）", min_value=80.0, max_value=210.0,
                value=float(s.get("height_cm") or 130.0), step=0.5,
            )
            weight_kg = st.number_input(
                "⚖️ 體重（kg）", min_value=15.0, max_value=120.0,
                value=float(s.get("weight_kg") or 30.0), step=0.5,
            )

        equipment = st.multiselect(
            "🧰 家裡有的輔助器材（AI 會把器材排進菜單）",
            EQUIPMENT_OPTIONS,
            default=s.get("equipment") or ["排球", "牆壁（對牆練習）"],
        )

        btn_label = "💾 儲存修改" if is_edit else "✅ 完成，下一步選訓練模式！"
        submitted = st.form_submit_button(
            btn_label, use_container_width=True, type="primary"
        )

    if submitted:
        updated = complete_student_profile(
            s["id"], age, gender, grade_level, height_cm, weight_kg, equipment or ["排球"]
        )
        st.session_state.current_student = updated
        st.success("✅ 資料已儲存！")
        st.rerun()


def render_generate_menu(student: dict):
    """學生端（或教練重生）：選訓練模式 → 生成菜單"""
    s = student
    has_old = bool(s.get("training_mode"))
    if has_old:
        st.markdown("## 🔄 設定新一套訓練菜單")
        st.caption(f"上一套：{s.get('training_mode')}（{s.get('total_weeks')} 週）")
    else:
        st.markdown(f"## 🤖 幫 {s['name']} 規劃訓練菜單")

    # 回上一步修改身高體重 / 年級 / 器材
    if st.button("✏️ 修改身高體重 / 器材"):
        st.session_state.editing_profile = True
        st.rerun()

    training_mode = st.radio(
        "選擇訓練模式",
        TRAINING_MODES,
        captions=[
            "排球技巧為主，可上傳影片給 AI 分析動作",
            "純體能基礎（敏捷、肌力、協調），不帶球、不含影片分析",
        ],
    )

    target_skill = None
    if training_mode == TRAINING_MODE_BALL:
        picked_skills = st.multiselect(
            "🎯 想加強的排球技巧（可複選）", TARGET_SKILLS,
            default=[TARGET_SKILLS[0]],
            help="可以選多項，AI 會把這些技巧都排進菜單；之後上傳影片時再選這支是練哪一項",
        )
        target_skill = "、".join(picked_skills)  # 以「、」串成一個字串存進 target_skill 欄位

    total_weeks = st.slider(
        "📅 訓練週期（週）", min_value=2, max_value=12, value=4,
        help="一套菜單跑完後，可以再設定下一套",
    )

    if st.button("✨ 生成專屬訓練菜單！", use_container_width=True, type="primary"):
        if training_mode == TRAINING_MODE_BALL and not target_skill:
            st.error("請至少選一項想加強的排球技巧！")
            return
        try:
            with st.status(f"🤖 AI 教練正在規劃 {total_weeks} 週菜單，請稍候...", expanded=False) as status:
                def on_retry(attempt, total, wait):
                    status.update(
                        label=f"⏳ AI 教練有點忙，正在多試幾次（第 {attempt}/{total} 次）…再等我一下下 🙏"
                    )
                curriculum = generate_curriculum(
                    s, training_mode, target_skill, total_weeks, status_cb=on_retry
                )
                save_curriculum(s["id"], curriculum, training_mode, total_weeks, target_skill)
                status.update(label="✅ 菜單規劃完成！", state="complete")
            # 重新抓最新學員資料（含 training_mode / plan_started_at）
            st.session_state.current_student = get_student_by_name(s["name"])
            st.session_state.curriculum = curriculum
            st.success("🎉 菜單生成完成！準備出發！")
            st.balloons()
            st.rerun()
        except GeminiBusyError as e:
            try:
                status.update(label="😴 AI 教練太忙了", state="error")
            except Exception:
                pass
            st.warning(f"⏳ {e}")


def _format_seconds(s) -> str:
    """秒數轉成親切中文：90 -> 1 分 30 秒、120 -> 2 分鐘、45 -> 45 秒"""
    s = int(s or 0)
    if s >= 60:
        m, sec = divmod(s, 60)
        return f"{m} 分鐘" if sec == 0 else f"{m} 分 {sec} 秒"
    return f"{s} 秒"


def item_badge(it: dict) -> str:
    """單一項目的份量標籤（計時 / 計次）"""
    if it.get("mode") == "time":
        return f"⏱️ {_format_seconds(it.get('seconds'))}"
    reps = it.get("reps") or 0
    sets = it.get("sets") or 1
    return f"🔁 {reps} 下 × {sets} 組" if sets > 1 else f"🔁 {reps} 下"


# 互動式訓練播放器（純前端 JS，計時/計次都在瀏覽器跑，不佔伺服器、手機順暢）
_SESSION_HTML = r"""
<div id="vt">
  <style>
    #vt { font-family: -apple-system, "Microsoft JhengHei", sans-serif; color:#1f2937; }
    #vt button { font-size:1.05rem; padding:12px 18px; margin:6px 4px 0 0; border:none;
      border-radius:10px; cursor:pointer; background:#FF6B35; color:#fff; font-weight:700; }
    #vt button.sec { background:#e5e7eb; color:#374151; }
    #vt button:disabled { opacity:.45; cursor:default; }
    #vt .start { width:100%; font-size:1.25rem; padding:16px; }
    #vt #card { background:#fff7ed; border:2px solid #FF6B35; border-radius:14px; padding:18px; margin-top:6px; text-align:center; }
    #vt #prog { color:#6b7280; font-size:.95rem; margin-bottom:8px; }
    #vt #iname { font-size:1.4rem; font-weight:800; margin-bottom:4px; }
    #vt #inote { color:#6b7280; margin-bottom:10px; }
    #vt #timer { font-size:3.4rem; font-weight:800; color:#FF6B35; letter-spacing:2px; }
    #vt #reps { font-size:1.15rem; line-height:1.8; }
    #vt #done { display:none; background:#ecfdf5; border:2px solid #22c55e; border-radius:14px;
      padding:24px; text-align:center; font-size:1.3rem; font-weight:800; color:#15803d; margin-top:6px; }
  </style>

  <button id="startBtn" class="start">▶ 開始今天的訓練！</button>

  <div id="session" style="display:none">
    <div id="prog"></div>
    <div id="card">
      <div id="iname"></div>
      <div id="inote"></div>
      <div id="timer" style="display:none"></div>
      <div id="reps" style="display:none"></div>
    </div>
    <div id="controls"></div>
  </div>

  <div id="done">🎉 今天全部完成，你超棒的！<br><span style="font-size:1rem;font-weight:600;color:#15803d">往下捲動按「✅ 打卡」領積分喔！</span></div>
</div>

<script>
(function(){
  const ITEMS = __ITEMS__;
  const root = document.getElementById('vt');
  const $ = id => root.querySelector('#' + id);
  let idx = 0, timerId = null, remaining = 0, paused = false, setsDone = 0;
  let actx = null;  // 音效用 AudioContext，須由使用者點擊「開始」時建立才能在手機發聲

  function fmt(s){ s = Math.max(0, s|0); const m = (s/60)|0, x = s%60;
    return (m<10?'0':'')+m + ':' + (x<10?'0':'')+x; }

  // 「嗶」聲：用 Web Audio 合成，不需音檔。pattern 為 [頻率, 起始秒, 長度] 的清單
  function beep(pattern){
    if(!actx) return;
    if(actx.state === 'suspended') actx.resume();
    const t0 = actx.currentTime;
    pattern.forEach(function(p){
      const osc = actx.createOscillator(), g = actx.createGain();
      osc.type = 'sine'; osc.frequency.value = p[0];
      osc.connect(g); g.connect(actx.destination);
      const s = t0 + p[1], e = s + p[2];
      g.gain.setValueAtTime(0.0001, s);
      g.gain.exponentialRampToValueAtTime(0.4, s + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, e);
      osc.start(s); osc.stop(e + 0.02);
    });
  }
  function buzz(pattern){ if(navigator.vibrate) try { navigator.vibrate(pattern); } catch(e){} }
  function alertDone(){ beep([[880,0,0.15],[1175,0.18,0.25]]); buzz([200,80,200]); }      // 時間到
  function alertFinish(){ beep([[784,0,0.15],[988,0.16,0.15],[1319,0.32,0.35]]); buzz([120,60,120,60,300]); }  // 全部完成

  $('startBtn').onclick = function(){
    // 在使用者手勢中建立／喚醒音訊，手機才允許之後發聲
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      if(AC){ actx = actx || new AC(); if(actx.state === 'suspended') actx.resume(); }
    } catch(e){ actx = null; }
    this.style.display='none'; $('session').style.display='block'; idx=0; showItem();
  };

  function showItem(){
    clearInterval(timerId); paused=false; setsDone=0;
    if(idx >= ITEMS.length) return finish();
    const it = ITEMS[idx];
    $('prog').innerHTML = '第 <b>'+(idx+1)+'</b> / '+ITEMS.length+' 項　'
      + '●'.repeat(idx) + '○'.repeat(ITEMS.length-idx);
    $('iname').textContent = (idx+1) + '. ' + (it.name||'');
    $('inote').textContent = it.note || '';
    const timer=$('timer'), reps=$('reps'), ctr=$('controls');

    if(it.mode === 'time'){
      reps.style.display='none'; timer.style.display='block';
      remaining = it.seconds|0; timer.textContent = fmt(remaining);
      ctr.innerHTML = '<button id="pp">⏸ 暫停</button>'
        + '<button id="rs" class="sec">↺ 重來</button>'
        + '<button id="nx" class="sec">下一項 →</button>';
      $('pp').onclick = togglePause;
      $('rs').onclick = function(){ remaining = it.seconds|0; timer.textContent = fmt(remaining); startTimer(); };
      $('nx').onclick = next;
      startTimer();
    } else {
      timer.style.display='none'; reps.style.display='block';
      const sets = it.sets||1;
      drawReps(it);
      ctr.innerHTML = '<button id="ok">✓ 完成一組</button>'
        + '<button id="nx" class="sec">下一項 →</button>';
      $('nx').onclick = next;
      $('ok').onclick = function(){
        if(setsDone < sets){ setsDone++; drawReps(it); }
        if(setsDone >= sets){ this.disabled = true; $('nx').className=''; markDoneReps(); }
      };
    }
  }

  function drawReps(it){
    const sets = it.sets||1, r = it.reps||0;
    let dots=''; for(let i=0;i<sets;i++) dots += (i<setsDone ? '🟢' : '⚪');
    $('reps').innerHTML = '目標：每組 <b>'+r+'</b> 下，共 <b>'+sets+'</b> 組<br>'
      + '<span style="font-size:1.8rem">'+dots+'</span><br>'
      + '已完成 '+setsDone+' / '+sets+' 組';
  }
  function markDoneReps(){ $('reps').innerHTML += '<br>✅ 這一項完成！'; }

  function startTimer(){
    clearInterval(timerId); paused=false;
    const pp=$('pp'); if(pp) pp.textContent='⏸ 暫停';
    timerId = setInterval(function(){
      if(paused) return;
      remaining--; $('timer').textContent = fmt(remaining);
      if(remaining <= 0){
        clearInterval(timerId); $('timer').textContent = '⏰ 時間到！';
        const nx=$('nx'); if(nx) nx.className='';
        const pp=$('pp'); if(pp) pp.disabled=true;
        alertDone();
      }
    }, 1000);
  }
  function togglePause(){ paused=!paused; $('pp').textContent = paused ? '▶ 繼續' : '⏸ 暫停'; }
  function next(){ clearInterval(timerId); idx++; showItem(); }
  function finish(){ clearInterval(timerId); $('session').style.display='none'; $('done').style.display='block'; alertFinish(); }
})();
</script>
"""


def render_training_session(items: list[dict]) -> None:
    """為一個訓練日的 items 渲染互動式播放器（計時倒數 / 計次完成）。"""
    if not items:
        return
    payload = json.dumps(items, ensure_ascii=False)
    components.html(_SESSION_HTML.replace("__ITEMS__", payload), height=420)


def _to_int(v, default=0) -> int:
    """安全把表格欄位值轉成整數（空白/NaN 回預設值）"""
    try:
        return default if pd.isna(v) else int(v)
    except (TypeError, ValueError):
        return default


def render_day_editor(student: dict, curriculum: dict, week_num: int, day: dict) -> None:
    """手動微調某一天的項目（改秒數/次數/組數、增刪項目）。教練與家長皆可用。"""
    if not st.toggle("✏️ 編輯這天的份量 / 項目", key=f"edit_w{week_num}_d{day['day']}"):
        return

    items = day.get("items") or []
    rows = [{
        "名稱": it.get("name", ""),
        "類型": "計時" if it.get("mode") == "time" else "計次",
        "秒數": int(it.get("seconds") or 0),
        "次數": int(it.get("reps") or 0),
        "組數": int(it.get("sets") or 1),
        "器材": "、".join(it.get("equipment") or []),
        "提醒": it.get("note", ""),
    } for it in items]
    df = pd.DataFrame(rows, columns=["名稱", "類型", "秒數", "次數", "組數", "器材", "提醒"])

    edited = st.data_editor(
        df, num_rows="dynamic", use_container_width=True, hide_index=True,
        key=f"editor_w{week_num}_d{day['day']}",
        column_config={
            "名稱": st.column_config.TextColumn("名稱", required=True, width="medium"),
            "類型": st.column_config.SelectboxColumn("類型", options=["計時", "計次"], required=True, width="small"),
            "秒數": st.column_config.NumberColumn("秒數(計時用)", min_value=0, max_value=1800, step=5),
            "次數": st.column_config.NumberColumn("次數(計次用)", min_value=0, max_value=300, step=1),
            "組數": st.column_config.NumberColumn("組數(計次用)", min_value=1, max_value=30, step=1),
            "器材": st.column_config.TextColumn("器材(用、分隔)"),
            "提醒": st.column_config.TextColumn("小提醒", width="large"),
        },
    )
    st.caption(
        "💡 「計時」項目填**秒數**；「計次」項目填**次數**與**組數**。"
        "可在表格最底列直接新增、或勾選列首刪除。想分部位伸展，就拆成多列各自計時即可。"
    )

    if st.button("💾 儲存這天的修改", key=f"save_w{week_num}_d{day['day']}", type="primary"):
        new_items = []
        for _, r in edited.iterrows():
            name = str(r["名稱"] or "").strip()
            if not name:
                continue  # 跳過沒填名稱的空列
            if r["類型"] == "計時":
                item = {"name": name, "mode": "time", "seconds": _to_int(r["秒數"], 30)}
            else:
                item = {"name": name, "mode": "reps",
                        "reps": _to_int(r["次數"], 10), "sets": _to_int(r["組數"], 1)}
            item["equipment"] = [e.strip() for e in str(r["器材"] or "").split("、") if e.strip()]
            item["note"] = str(r["提醒"] or "").strip()
            new_items.append(item)

        if not new_items:
            st.warning("至少要保留一個項目喔！")
            return
        day["items"] = new_items  # day 是 curriculum 內的參照，直接改即同步
        update_curriculum_json(student["id"], curriculum)
        st.session_state.curriculum = curriculum
        st.success("✅ 已儲存這天的修改！")
        st.rerun()


def render_day_checkin(student: dict, week_number: int, day_num: int, logs: list[dict]) -> None:
    """每一天各自獨立的打卡按鈕（第 N 天做完就打勾，與其他天、與日曆都無關）。"""
    st.markdown("---")
    done_log = next(
        (l for l in logs if l.get("is_completed")
         and l.get("week_number") == week_number and l.get("day_number") == day_num),
        None,
    )
    if done_log:
        st.success(f"🌟 第 {day_num} 天已完成！得分 {done_log.get('score', 10)} 分，換下一天繼續加油！")
        return
    st.markdown(f"**做完「第 {day_num} 天」的訓練了嗎？按這裡打卡領積分！** 👇")
    if st.button(
        f"✅ 完成第 {day_num} 天，打卡！",
        key=f"checkin_w{week_number}_d{day_num}",
        use_container_width=True, type="primary",
    ):
        create_session_log(student["id"], week_number, day_num)
        st.balloons()
        st.success(f"🎊 第 {day_num} 天打卡成功！獲得 10 積分！")
        st.rerun()


def render_curriculum(curriculum: dict, current_week: int, student: dict | None = None,
                      logs: list[dict] | None = None):
    """顯示週訓練菜單"""
    if not curriculum or "weeks" not in curriculum:
        st.warning("菜單資料異常，請重新生成。")
        return
    logs = logs or []

    weeks = curriculum["weeks"]
    # 找到當前週資料，找不到則顯示第一週
    week_data = next((w for w in weeks if w["week"] == current_week), weeks[0])

    st.info(f"🎯 **本週主題**：{week_data.get('focus', '排球基礎訓練')}")
    if week_data.get("parent_note"):
        st.caption(f"👨‍👩‍👧 **給家長**：{week_data['parent_note']}")
    st.caption(
        "🗓️ **照自己的進度做就好，不用管今天星期幾**：每一天各自打卡（做完哪天打哪天），"
        "累積 5 天進下一週；有事跳過沒關係，週末或有空時再補做即可。"
    )

    # 訓練日改用「第 N 天」標示（不綁日曆星期，配合自我配速），各天獨立打卡
    train_no = 0
    for day in week_data.get("days", []):
        if day.get("is_rest"):
            label = "😴 休息 / 補做日"
            with st.expander(label, expanded=False):
                st.markdown(f"🌙 {day.get('task', '好好休息，或補做之前沒做到的那天！')}")
                if day.get("tip"):
                    st.info(f"💡 **小叮嚀**：{day['tip']}")
        else:
            train_no += 1
            items = day.get("items") or []
            done = is_session_done(logs, week_data["week"], train_no)
            label = f"🏐 第 {train_no} 天 ⏱️ {day.get('duration_min', 0)} 分鐘" + ("　✅ 已完成" if done else "")
            with st.expander(label, expanded=(train_no == 1 and not done)):
                if day.get("focus"):
                    st.markdown(f"**🎯 今天主題：** {day['focus']}")

                if items:
                    # 新版：條列式項目，每項標清楚次數或時間
                    st.markdown(f"**📋 今天總共 {len(items)} 項，照順序做：**")
                    for i, it in enumerate(items, 1):
                        st.markdown(f"**{i}. {it.get('name', '')}**　{item_badge(it)}")
                        meta = []
                        if it.get("equipment"):
                            meta.append("🧰 " + "、".join(it["equipment"]))
                        if it.get("note"):
                            meta.append("💡 " + it["note"])
                        if meta:
                            st.caption("　".join(meta))
                    st.markdown("---")
                    st.markdown("**🎮 跟著做：按「開始」會帶你一項一項完成，計時項目自動倒數，計次項目做完一組點一下**")
                    render_training_session(items)
                    # 每一天各自獨立打卡（第 N 天做完打第 N 天）
                    if student is not None:
                        render_day_checkin(student, week_data["week"], train_no, logs)
                    # 手動微調這天的份量/項目（教練與家長皆可）
                    if student is not None:
                        st.markdown("---")
                        render_day_editor(student, curriculum, week_data["week"], day)
                else:
                    # 舊版菜單相容：只有 task 字串
                    st.markdown(f"**任務：** {day.get('task', '')}")
                    day_equipment = day.get("equipment") or []
                    if day_equipment:
                        st.markdown("🧰 **使用器材：** " + "、".join(day_equipment))

                if day.get("tip"):
                    st.info(f"💡 **小叮嚀**：{day['tip']}")
                st.caption(f"預計訓練時間：{day.get('duration_min', 0)} 分鐘")

    # 所有週次導覽（摺疊）
    if len(weeks) > 1:
        with st.expander("📆 查看所有週次計畫"):
            for w in weeks:
                st.markdown(
                    f"**第 {w['week']} 週** — {w.get('focus', '')}",
                    help=f"共 {len(w.get('days',[]))} 天"
                )


def render_ai_feedback_card(feedback: dict):
    """顯示 AI 教練回饋卡片"""
    score = feedback.get("score", 0)

    # 分數與開場白
    col_score, col_msg = st.columns([1, 3])
    with col_score:
        color = "#22c55e" if score >= 80 else "#f59e0b" if score >= 60 else "#ef4444"
        st.markdown(
            f"""<div style='background:{color};border-radius:12px;padding:20px;
            text-align:center;color:white;'>
            <div style='font-size:2rem;font-weight:bold;'>{score}</div>
            <div>本次得分</div></div>""",
            unsafe_allow_html=True,
        )
    with col_msg:
        st.markdown(f"### 💬 {feedback.get('greeting', '')}")

    st.markdown("---")

    col_good, col_improve = st.columns(2)
    with col_good:
        st.markdown("#### 👍 做得很棒！")
        for s in feedback.get("strengths", []):
            st.markdown(f"✅ {s}")

    with col_improve:
        st.markdown("#### 💡 再加把勁！")
        for imp in feedback.get("improvements", []):
            st.markdown(f"🔧 {imp}")

    # 分項檢核點結果
    checkpoint_results = feedback.get("checkpoint_results") or []
    if checkpoint_results:
        st.markdown("#### 📋 動作檢核表")
        for cp in checkpoint_results:
            st.markdown(f"{cp.get('status', '✅')} **{cp.get('item', '')}** — {cp.get('comment', '')}")

    # 在家加強小練習
    drill = feedback.get("drill_suggestion")
    if drill:
        st.warning(f"🏠 **在家加強小練習**：{drill}")

    st.markdown("---")
    st.success(f"🌈 **{feedback.get('encouragement', '')}**")
    st.info(f"🏐 **排球小知識**：{feedback.get('fun_fact', '')}")


def render_checkin(student: dict, logs: list[dict]):
    """今日完成總覽：列出今天打卡的天數與 AI 回饋（打卡動作改在「訓練菜單」每天各自進行）"""
    today = date.today()
    today_str = today.isoformat()
    st.markdown(f"📅 今天是 **{today.strftime('%Y 年 %m 月 %d 日')}**")

    today_logs = [
        l for l in logs
        if l.get("is_completed") and l.get("training_date") == today_str
    ]

    if not today_logs:
        st.info("今天還沒完成任何一天喔！到「📋 訓練菜單」挑一天，跟著做完就打卡吧 💪")
        return

    st.success(f"🌟 今天完成了 **{len(today_logs)}** 天訓練，超棒的！")
    for l in sorted(today_logs, key=lambda x: (x.get("week_number") or 0, x.get("day_number") or 0)):
        wk = l.get("week_number", "?")
        dy = l.get("day_number")
        title = f"第 {wk} 週・第 {dy} 天" if dy else f"第 {wk} 週"
        st.markdown(f"#### ✅ {title}　⭐ {l.get('score', 10)} 分")
        feedback = parse_ai_feedback(l.get("ai_feedback"))
        if feedback:
            render_ai_feedback_card(feedback)
        else:
            st.caption("（上傳練習影片可獲得 AI 詳細評分與回饋！）")
        st.markdown("---")


def render_journal_form(student: dict, plan_key: str, week: int, readonly: bool = False) -> None:
    """單一週的訓練日誌表單（心情 + 文字 + 一張照片）。readonly=True 給教練唯讀檢視。"""
    existing = get_journal(student["id"], plan_key, week)

    if readonly:
        if not existing:
            st.caption("（這週還沒寫日誌）")
            return
        st.markdown(f"**心情：** {existing.get('mood', '')}")
        if existing.get("content"):
            st.markdown(existing["content"])
        if existing.get("photo_url"):
            st.image(existing["photo_url"], width=240)
        st.caption(f"寫於 {(existing.get('updated_at') or existing.get('created_at') or '')[:10]}")
        return

    default_mood = existing.get("mood") if existing else JOURNAL_MOODS[0]
    mood_idx = JOURNAL_MOODS.index(default_mood) if default_mood in JOURNAL_MOODS else 0
    mood = st.radio(
        "這週的心情", JOURNAL_MOODS, index=mood_idx, horizontal=True,
        key=f"jmood_{plan_key}_{week}",
    )
    content = st.text_area(
        "這週的訓練心得（過程、感覺、最棒的一刻、想跟教練說的話…）",
        value=(existing.get("content", "") if existing else ""),
        height=160, key=f"jcontent_{plan_key}_{week}",
        placeholder="例：這週低手墊球比較穩了，連續接到 10 球好開心！但跳躍還是有點累…",
    )
    existing_photo = existing.get("photo_url") if existing else None
    if existing_photo:
        st.image(existing_photo, width=200, caption="目前的照片（重新上傳會覆蓋）")
    photo = st.file_uploader(
        "放一張這週的照片（選填，jpg / png）",
        type=["jpg", "jpeg", "png"], key=f"jphoto_{plan_key}_{week}",
    )

    if st.button("💾 儲存這週日誌", key=f"jsave_{plan_key}_{week}", type="primary", use_container_width=True):
        if not content.strip():
            st.error("寫一點點心得再儲存吧！至少一兩句也好 😊")
            return
        photo_url = existing_photo
        if photo is not None:
            with st.spinner("上傳照片中..."):
                try:
                    photo_url = upload_journal_photo(student["id"], photo.read(), photo.name)
                except Exception as e:
                    print(f"[ERROR] journal photo upload failed: {e}")
                    st.warning("⚠️ 照片上傳失敗（可能還沒建 journal-photos bucket），先存文字，照片稍後再補。")
        upsert_journal(student["id"], plan_key, week, mood, content.strip(), photo_url)
        st.success("✅ 日誌已儲存！")
        st.balloons()
        st.rerun()


def render_journal_gate(student: dict, plan_key: str, week: int) -> None:
    """強制日誌關卡：完成一週後，沒寫日誌就擋住下一週的訓練。"""
    st.markdown(f"# 🎉 太棒了，第 {week} 週訓練完成！")
    st.warning(
        f"✍️ 先寫一篇「**第 {week} 週訓練日誌**」，記錄這週的過程和心情，"
        "才能解鎖下一週的訓練喔！"
    )
    render_journal_form(student, plan_key, week, readonly=False)


def render_journal_tab(student: dict, current_week: int, logs: list[dict],
                       plan_key: str, readonly: bool = False) -> None:
    """訓練日誌分頁：列出本套菜單各週日誌（可寫/可改；教練為唯讀）。"""
    st.markdown("## 📔 訓練日誌")
    st.caption("每完成一週寫一篇，記錄過程與心情；之後會累積成你的成長日記 📖")

    done_weeks = completed_sessions(logs) // DAYS_PER_WEEK
    max_week = max(done_weeks, current_week, 1)
    try:
        for w in range(max_week, 0, -1):
            exists = get_journal(student["id"], plan_key, w) is not None
            title = f"第 {w} 週 訓練日誌　" + ("✅ 已寫" if exists else "✍️ 待寫")
            with st.expander(title, expanded=(w == max_week and not readonly and not exists)):
                render_journal_form(student, plan_key, w, readonly=readonly)
    except Exception as e:
        print(f"[ERROR] 讀取日誌失敗: {e}")
        st.error(
            "📔 日誌功能需要先設定：請到 Supabase 執行 `migrate_v4.sql`，"
            "並建立 `journal-photos` 這個 public bucket（步驟見該檔註解）。"
        )


def render_body_metric_reminder(student: dict):
    """距上次紀錄滿 14 天 → 頂部溫和提示更新身高體重（非強制）"""
    days = days_since_last_metric(student["id"])
    if days is None or days < 14:
        return
    with st.container(border=True):
        st.markdown(
            f"📏 距離上次量身高體重已經 **{days} 天**了！和爸爸媽媽一起量一下，記錄成長吧 💪"
        )
        with st.form(f"metric_update_{student['id']}", clear_on_submit=True):
            mc1, mc2, mc3 = st.columns([2, 2, 1])
            h = mc1.number_input(
                "身高 (cm)", min_value=80.0, max_value=210.0,
                value=float(student.get("height_cm") or 130.0), step=0.5,
            )
            w = mc2.number_input(
                "體重 (kg)", min_value=15.0, max_value=120.0,
                value=float(student.get("weight_kg") or 30.0), step=0.5,
            )
            mc3.markdown("<br>", unsafe_allow_html=True)
            if mc3.form_submit_button("✅ 更新", use_container_width=True):
                record_body_metric(student["id"], h, w)
                st.session_state.current_student = get_student_by_name(student["name"])
                st.success("✅ 已更新！到「我的進度」看看你的成長曲線吧！")
                st.rerun()


def render_progress(student: dict, logs: list[dict]):
    """學員進度看板"""
    stats = calculate_stats(student, logs)

    # 進度條
    st.markdown("#### 🎯 整體訓練完成度")
    st.progress(stats["progress_pct"] / 100)
    st.caption(
        f"已完成 {stats['completed_days']} / {stats['total_training_days']} 個訓練日"
        f"（{stats['progress_pct']:.1f}%）"
    )

    # 三格統計
    c1, c2, c3 = st.columns(3)
    c1.metric("📅 打卡天數", stats["completed_days"])
    c2.metric("⭐ 累積積分", stats["total_score"])
    c3.metric("🎥 上傳影片", stats["video_count"])

    # 成長曲線（身高 / 體重，需 ≥2 筆紀錄）
    metrics = get_body_metrics(student["id"])
    if len(metrics) >= 2:
        st.markdown("#### 📈 我的成長曲線")
        df = pd.DataFrame(metrics)
        df["recorded_at"] = pd.to_datetime(df["recorded_at"])
        df["height_cm"] = pd.to_numeric(df["height_cm"])
        df["weight_kg"] = pd.to_numeric(df["weight_kg"])
        df = df.set_index("recorded_at")
        gc1, gc2 = st.columns(2)
        with gc1:
            st.caption("📏 身高 (cm)")
            st.line_chart(df["height_cm"])
        with gc2:
            st.caption("⚖️ 體重 (kg)")
            st.line_chart(df["weight_kg"])

    # 最近 5 筆紀錄
    if logs:
        st.markdown("#### 📝 近期訓練紀錄")
        recent = sorted(logs, key=lambda x: x["training_date"], reverse=True)[:5]
        for log in recent:
            icon = "🎥" if log.get("video_url") else "✅"
            score_text = f"⭐ {log['score']} 分" if log.get("score") else ""
            day_text = f"第 {log['day_number']} 天" if log.get("day_number") else ""
            st.markdown(
                f"{icon} **{log['training_date']}**　第 {log['week_number']} 週 {day_text}　{score_text}"
            )
    else:
        st.info("還沒有訓練紀錄，快去打卡吧！💪")


def render_video_upload(student: dict, current_week: int):
    """影片上傳與 AI 分析區"""
    st.markdown(
        "上傳一段 **10 秒以內**的練習短片，AI 教練會分析你的動作並給予專屬回饋！🤖🏐"
    )
    st.caption("建議從正面或側面拍攝，讓 AI 能清楚看到動作。")

    uploaded = st.file_uploader(
        "選擇影片（mp4 / mov，建議 10 秒以內，最大 50 MB）",
        type=["mp4", "mov", "avi"],
    )

    if not uploaded:
        return

    st.video(uploaded)

    # 這支影片是練哪一項技巧（學員可能複選了多項，分析需鎖定單一技巧的檢核點）
    skills = parse_skills(student.get("target_skill"))
    if len(skills) > 1:
        skill = st.selectbox("🎯 這支影片是在練哪一項技巧？", skills)
    else:
        skill = skills[0] if skills else "綜合訓練"

    # 這支影片要記在「第幾天」（把 AI 分數/回饋掛到那一天的紀錄，並標記完成）
    day_num = st.selectbox(
        f"📅 這是第 {current_week} 週的第幾天？",
        list(range(1, DAYS_PER_WEEK + 1)),
        format_func=lambda d: f"第 {d} 天",
    )

    if not st.button("🤖 送出給 AI 教練分析！", type="primary", use_container_width=True):
        return

    video_bytes = uploaded.read()
    public_url = None

    # Step 1:上傳到 Supabase Storage
    with st.spinner("📤 上傳影片中..."):
        try:
            public_url = upload_video_to_supabase(student["id"], video_bytes, uploaded.name)
            st.success("✅ 影片上傳成功！")
        except Exception as e:
            print(f"[ERROR] Supabase upload failed: {e}")  # 細節只留在伺服器 log
            st.warning("⚠️ 影片雲端備份失敗，將直接送 AI 分析。")

    # Step 2:Gemini 多模態分析
    with st.status("🧠 AI 教練正在仔細分析你的動作，請稍候（約 15–30 秒）...", expanded=False) as status:
        def on_retry(attempt, total, wait):
            status.update(
                label=f"⏳ AI 教練有點忙，正在多試幾次（第 {attempt}/{total} 次）…再等我一下下 🙏"
            )
        try:
            feedback = analyze_video(video_bytes, skill, student["name"], status_cb=on_retry)
            status.update(label="✅ 分析完成！", state="complete")
        except GeminiBusyError as e:
            status.update(label="😴 AI 教練太忙了", state="error")
            st.warning(f"⏳ {e}")
            return
        except Exception as e:
            print(f"[ERROR] Gemini analysis failed: {e}")  # 細節只留在伺服器 log
            status.update(label="❌ 分析失敗", state="error")
            st.error("❌ AI 分析失敗，請稍後再試（影片建議 10 秒內、50MB 以下）。")
            return

    # Step 3:儲存到 training_logs（掛到「第 current_week 週第 day_num 天」那筆，沒有就建立）
    session_log = get_session_log(student["id"], current_week, day_num)
    feedback_json = json.dumps(feedback, ensure_ascii=False)
    score = feedback.get("score", 80)

    try:
        if session_log:
            update_training_log(session_log["id"], public_url, feedback_json, score)
        else:
            new_log = create_session_log(student["id"], current_week, day_num)
            update_training_log(new_log["id"], public_url, feedback_json, score)
    except Exception as e:
        print(f"[ERROR] Saving training log failed: {e}")  # 細節只留在伺服器 log
        st.warning("⚠️ 紀錄儲存失敗，但回饋仍顯示如下。")

    # Step 4:顯示回饋
    st.markdown("---")
    st.markdown("## 🎊 AI 教練回饋出爐！")
    render_ai_feedback_card(feedback)
    st.balloons()


# ══════════════════════════════════════════════════════════════
# 主程式
# ══════════════════════════════════════════════════════════════

def main():
    # ── 通行碼檢查（部署上線後使用） ─────────────────────────
    if not check_password():
        return

    # ── Session State 初始化 ────────────────────────────────
    if "current_student" not in st.session_state:
        st.session_state.current_student = None
    if "curriculum" not in st.session_state:
        st.session_state.curriculum = None
    if "role" not in st.session_state:
        st.session_state.role = None
    if "editing_profile" not in st.session_state:
        st.session_state.editing_profile = False  # 是否正在編輯身體資料（教練或學員皆可）
    if "confirm_delete" not in st.session_state:
        st.session_state.confirm_delete = False       # 刪除學員的二次確認狀態
    if "adding_student" not in st.session_state:
        st.session_state.adding_student = False        # 教練後台是否正在新增學員

    # ── 身分登入（學員 / 教練後台） ──────────────────────────
    if st.session_state.role is None:
        render_login()
        return

    is_admin = st.session_state.role == "admin"

    # ── Sidebar ─────────────────────────────────────────────
    with st.sidebar:
        st.markdown("# 🏐 排球訓練小幫手")
        st.caption("🎓 教練後台" if is_admin else "👦 小選手模式")
        st.markdown("---")

        # 學員清單與管理功能：僅教練後台可見
        all_students = get_all_students() if is_admin else []

        if is_admin and all_students:
            st.markdown("### 選擇小選手")
            student_names = [s["name"] for s in all_students]
            student_map = {s["name"]: s for s in all_students}

            # 預設選中目前學員
            default_idx = 0
            if st.session_state.current_student:
                try:
                    default_idx = student_names.index(
                        st.session_state.current_student["name"]
                    )
                except ValueError:
                    default_idx = 0

            def _on_select_student():
                # 教練主動切換下拉選單 → 離開「新增學員」模式
                st.session_state.adding_student = False

            selected_name = st.selectbox(
                "學員", student_names, index=default_idx,
                label_visibility="collapsed",
                key="student_selector", on_change=_on_select_student,
            )

            selected = student_map[selected_name]

            # 切換學員時更新 session（新增模式中先不自動選回，否則會蓋掉新增畫面）
            if not st.session_state.adding_student and (
                st.session_state.current_student is None
                or st.session_state.current_student["id"] != selected["id"]
            ):
                _set_current_student(selected)
                st.session_state.editing_profile = False
                st.session_state.confirm_delete = False

            st.markdown("---")

        if is_admin and st.button("➕ 新增學員", use_container_width=True):
            st.session_state.adding_student = True
            st.session_state.editing_profile = False
            st.session_state.confirm_delete = False
            st.rerun()

        # 學員小名片
        if st.session_state.current_student:
            s = st.session_state.current_student
            st.markdown("### 學員資訊")
            if not s.get("profile_completed"):
                st.markdown(f"**{s['name']}**")
                st.caption("（尚未完善資料，待學生家長填寫）")
            else:
                st.markdown(f"**{s['name']}**　{s.get('age','?')} 歲 {s.get('gender','')}")
                if s.get("grade_level"):
                    st.markdown(f"🏫 {s['grade_level']}")
                if s.get("training_mode"):
                    st.markdown(f"🏋️ {s['training_mode']}")
                if s.get("training_mode") == TRAINING_MODE_BALL and s.get("target_skill"):
                    st.markdown(f"🎯 {s['target_skill']}")
                st.markdown(f"📏 {s.get('height_cm')} cm　⚖️ {s.get('weight_kg')} kg")
                if s.get("total_weeks"):
                    st.markdown(f"📅 {s['total_weeks']} 週計畫")
                if s.get("equipment"):
                    st.markdown("🧰 " + "、".join(s["equipment"]))

            # 教練後台：編輯 / 刪除學員
            if is_admin:
                st.markdown("")
                ec1, ec2 = st.columns(2)
                if ec1.button("✏️ 編輯資料", use_container_width=True):
                    st.session_state.editing_profile = True
                    st.session_state.confirm_delete = False
                    st.rerun()
                if ec2.button("🗑️ 刪除學員", use_container_width=True):
                    st.session_state.confirm_delete = True
                    st.rerun()

                # 刪除二次確認
                if st.session_state.confirm_delete:
                    st.warning(
                        f"確定要刪除「{s['name']}」嗎？\n\n"
                        "會一併刪除他的所有打卡、影片與成長紀錄，**無法復原**！"
                    )
                    dc1, dc2 = st.columns(2)
                    if dc1.button("✅ 確定刪除", use_container_width=True, type="primary"):
                        delete_student(s["id"])
                        st.session_state.current_student = None
                        st.session_state.curriculum = None
                        st.session_state.confirm_delete = False
                        st.session_state.editing_profile = False
                        # 清掉下拉選單記住的舊選擇，避免它指向已刪除的學員而報錯
                        st.session_state.pop("student_selector", None)
                        st.toast(f"已刪除「{s['name']}」")
                        st.rerun()
                    if dc2.button("取消", use_container_width=True):
                        st.session_state.confirm_delete = False
                        st.rerun()

        st.markdown("---")
        if st.button("🚪 登出", use_container_width=True):
            st.session_state.role = None
            st.session_state.current_student = None
            st.session_state.curriculum = None
            st.session_state.editing_profile = False
            st.session_state.confirm_delete = False
            st.rerun()

    # ── 主內容區 ────────────────────────────────────────────
    # 教練後台：新增學員模式（按了「➕ 新增學員」，或名冊還是空的）
    if is_admin and (st.session_state.adding_student or not all_students):
        if not all_students:
            st.markdown("""
            # 🏐 歡迎使用排球訓練小幫手！（教練後台）

            這是一個專為小朋友設計的 AI 排球訓練夥伴。教練在這裡**建立名冊**，
            小朋友與家長登入後**自己填資料、生成菜單、上傳影片**。

            👇 先用下方表單建立第一位小選手的名字吧！
            """)
        elif st.button("← 返回學員"):
            st.session_state.adding_student = False
            st.rerun()
        render_add_student_shell()
        return

    if st.session_state.current_student is None:
        # 學員模式不應沒有學員資料，安全起見退回登入頁
        if not is_admin:
            st.session_state.role = None
            st.rerun()
            return
        # 教練後台理論上會被上面的選單自動選回學員；保險起見導向新增
        render_add_student_shell()
        return

    student = st.session_state.current_student
    curriculum = st.session_state.curriculum

    # 0) 按了「✏️ 編輯資料」→ 直接顯示編輯表單（教練或學員皆可，優先於其他畫面）
    if st.session_state.editing_profile:
        who = f"「{student['name']}」的" if is_admin else "我的"
        st.markdown(f"## ✏️ 編輯{who}資料")
        if st.button("← 返回"):
            st.session_state.editing_profile = False
            st.rerun()
        render_profile_form(student, is_edit=True)
        return

    # 1) 尚未完善資料 → 完善資料表單（學生家長填；教練可代填）
    if not student.get("profile_completed"):
        if is_admin:
            st.warning("⚠️ 此學生尚未完善資料，通常由學生與家長登入後自己填寫。")
            st.caption("如需代填，可使用以下表單：")
            render_profile_form(student, is_edit=True)
        else:
            render_profile_form(student, is_edit=False)
        return

    # 2) 資料已完善但還沒有菜單 → 選模式生成
    if curriculum is None:
        render_generate_menu(student)
        return

    logs = get_training_logs(student["id"])
    plan_key = student.get("plan_started_at") or student["created_at"]

    # 2.5) 強制日誌關卡：完成的週若還沒寫日誌，學員必須先寫才能繼續（教練不擋）
    if not is_admin:
        done_weeks = completed_sessions(logs) // DAYS_PER_WEEK
        try:
            for w in range(1, done_weeks + 1):
                if get_journal(student["id"], plan_key, w) is None:
                    render_journal_gate(student, plan_key, w)
                    return
        except Exception as e:
            # 日誌資料表還沒建好時，不要把學員卡死在訓練之外
            print(f"[WARN] 日誌關卡略過（weekly_journals 可能尚未建立）: {e}")

    # 3) 當前菜單已跑完 → 引導設定下一套（用「完成次數」判斷，不綁日曆）
    if is_plan_finished(student, logs):
        st.markdown(f"# 🎉 {student['name']}，這套 {student['total_weeks']} 週菜單完成囉！")
        st.success("太棒了！先和爸媽更新一下身高體重，再來設計下一套訓練吧 💪")
        render_body_metric_reminder(student)
        st.markdown("---")
        render_generate_menu(student)
        return

    # 4) 正常訓練 dashboard
    current_week = calculate_current_week(student, logs)
    is_ball_mode = student.get("training_mode") == TRAINING_MODE_BALL

    # 頁面標題
    st.markdown(f"# 🏐 {student['name']} 的訓練日記")
    goal_text = student["target_skill"] if is_ball_mode else (student.get("training_mode") or "")
    st.caption(
        f"{goal_text}　｜　第 {current_week} / {student['total_weeks']} 週"
        f"（做完 {completed_sessions(logs)} 次）　｜　累積 {sum(l.get('score',0) for l in logs)} 分"
    )

    # 兩週身高體重提醒（滿 14 天才出現）
    render_body_metric_reminder(student)

    # 教練工具：重新生成菜單（編輯/刪除學員已移到左側欄）
    if is_admin:
        with st.expander("🛠️ 教練工具：重新生成菜單"):
            render_generate_menu(student)

    # 功能頁籤（影片分析僅在「綜合含球」模式提供）
    tab_labels = ["📋 訓練菜單", "✅ 今日完成", "📊 我的進度", "📔 訓練日誌"]
    if is_ball_mode:
        tab_labels.append("🎥 影片 AI 分析")
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        render_curriculum(curriculum, current_week, student, logs)
    with tabs[1]:
        render_checkin(student, logs)
    with tabs[2]:
        render_progress(student, logs)
    with tabs[3]:
        render_journal_tab(student, current_week, logs, plan_key, readonly=is_admin)
    if is_ball_mode:
        with tabs[4]:
            render_video_upload(student, current_week)


if __name__ == "__main__":
    main()
