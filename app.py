# ============================================================
# 🏐 小朋友排球訓練小幫手 — MVP v1.0
# Tech Stack: Streamlit + Gemini API + Supabase
# ============================================================

import os
import json
import time
import random
import tempfile
import base64
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
TRAINING_MODE_BALL = "綜合訓練（含排球）"      # 排球技巧為主
TRAINING_MODE_FITNESS = "身體素質強化（不帶球）"  # 純體能基礎，不含持球/排球技術
TRAINING_MODES = [TRAINING_MODE_BALL, TRAINING_MODE_FITNESS]
TARGET_SKILLS = ["低手墊球（接球）", "高手傳球", "扣球步法", "發球練習", "防守移位", "綜合訓練"]

APP_DIR = os.path.dirname(os.path.abspath(__file__))

AVATAR_TEMPLATE_SEED = [
    {
        "id": "beginner",
        "display_name": "活力新手",
        "english_name": "Energetic Beginner",
        "role_name": "新手入門 / 全能練習生",
        "description": "第一次加入排球隊，雖然技巧還在練習中，但總是第一個舉手挑戰。",
        "catchphrase": "再試一次，我一定可以！",
        "asset_path": "assets/sprites/characters/templates/beginner.png",
        "active": True,
        "asset_ready": True,
        "sort_order": 1,
    },
    {
        "id": "ace",
        "display_name": "隊長王牌",
        "english_name": "Captain Ace",
        "role_name": "隊長 / 王牌攻擊手",
        "description": "球隊裡可靠的小隊長，會提醒大家站位，也會鼓勵隊友不要緊張。",
        "catchphrase": "大家一起來，這球我們接得起來！",
        "asset_path": "assets/sprites/characters/templates/ace.png",
        "active": True,
        "asset_ready": True,
        "sort_order": 2,
    },
    {
        "id": "libero",
        "display_name": "冷酷自由人",
        "english_name": "Cool Libero",
        "role_name": "自由球員 / 防守專家",
        "description": "話不多，但總能出現在球快落地的位置。",
        "catchphrase": "我看到了，這球交給我。",
        "asset_path": "assets/sprites/characters/templates/libero.png",
        "active": True,
        "asset_ready": True,
        "sort_order": 3,
    },
    {
        "id": "supporter",
        "display_name": "陽光應援",
        "english_name": "Sunny Supporter",
        "role_name": "團隊應援 / 氣氛帶動",
        "description": "總是把隊伍氣氛變好，失誤時會第一個說「沒關係」。",
        "catchphrase": "沒關係，我們下一球會更好！",
        "asset_path": "assets/sprites/characters/templates/supporter.png",
        "active": True,
        "asset_ready": True,
        "sort_order": 4,
    },
    {
        "id": "tech",
        "display_name": "未來科技",
        "english_name": "Futuristic Tech",
        "role_name": "科技分析 / 技巧型",
        "description": "會用自己的小工具記錄發球、接球和訓練進度。",
        "catchphrase": "資料顯示，我們正在變強！",
        "asset_path": "assets/sprites/characters/templates/tech.png",
        "active": True,
        "asset_ready": True,
        "sort_order": 5,
    },
    {
        "id": "setter",
        "display_name": "速度舉球手",
        "english_name": "Speed Setter",
        "role_name": "舉球員 / 節奏控制",
        "description": "動作很快，總能把球送到隊友最舒服的位置。",
        "catchphrase": "準備好，我把球送過去！",
        "asset_path": "",
        "active": False,
        "asset_ready": False,
        "sort_order": 6,
    },
    {
        "id": "blocker",
        "display_name": "強力攔網手",
        "english_name": "Power Blocker",
        "role_name": "攔網 / 前排防守",
        "description": "看起來很有氣勢，但其實很照顧隊友。",
        "catchphrase": "這球我來擋住！",
        "asset_path": "",
        "active": False,
        "asset_ready": False,
        "sort_order": 7,
    },
    {
        "id": "rainbow",
        "display_name": "彩虹扣球手",
        "english_name": "Rainbow Smash",
        "role_name": "扣球 / 明星型攻擊",
        "description": "一登場就很吸睛，喜歡用漂亮的動作完成扣球。",
        "catchphrase": "看我的彩虹扣殺！",
        "asset_path": "",
        "active": False,
        "asset_ready": False,
        "sort_order": 8,
    },
]

PET_CATALOG_SEED = [
    {"id": "pet_n_01", "display_name": "球球汪", "rarity": "N", "species_note": "排球項圈小狗", "asset_path": "assets/sprites/pets/pet_n_01.png", "active": True, "asset_ready": True, "sort_order": 1},
    {"id": "pet_n_02", "display_name": "啾啾雞", "rarity": "N", "species_note": "穿訓練背心的小雞", "asset_path": "assets/sprites/pets/pet_n_02.png", "active": True, "asset_ready": True, "sort_order": 2},
    {"id": "pet_n_03", "display_name": "芽芽黏", "rarity": "N", "species_note": "頭上長芽的黏黏球", "asset_path": "assets/sprites/pets/pet_n_03.png", "active": True, "asset_ready": True, "sort_order": 3},
    {"id": "pet_n_04", "display_name": "躍躍兔", "rarity": "N", "species_note": "綁頭帶的彈跳兔", "asset_path": "assets/sprites/pets/pet_n_04.png", "active": True, "asset_ready": True, "sort_order": 4},
    {"id": "pet_n_05", "display_name": "竹團熊", "rarity": "N", "species_note": "拿竹子的圓滾滾熊", "asset_path": "assets/sprites/pets/pet_n_05.png", "active": True, "asset_ready": True, "sort_order": 5},
    {"id": "pet_n_06", "display_name": "旋風狐", "rarity": "N", "species_note": "帶哨子的敏捷小狐", "asset_path": "assets/sprites/pets/pet_n_06.png", "active": True, "asset_ready": True, "sort_order": 6},
    {"id": "pet_r_01", "display_name": "鋼衛熊", "rarity": "R", "species_note": "守備型機械熊", "asset_path": "assets/sprites/pets/pet_r_01.png", "active": True, "asset_ready": True, "sort_order": 7},
    {"id": "pet_r_02", "display_name": "音凍凍", "rarity": "R", "species_note": "耳機水母凍", "asset_path": "assets/sprites/pets/pet_r_02.png", "active": True, "asset_ready": True, "sort_order": 8},
    {"id": "pet_r_03", "display_name": "飛躍豬", "rarity": "R", "species_note": "有翅膀的助跑小豬", "asset_path": "assets/sprites/pets/pet_r_03.png", "active": True, "asset_ready": True, "sort_order": 9},
    {"id": "pet_sr_01", "display_name": "扣球幼龍", "rarity": "SR", "species_note": "夕陽球場幼龍", "asset_path": "assets/sprites/pets/pet_sr_01.png", "active": True, "asset_ready": True, "sort_order": 10},
    {"id": "pet_sr_02", "display_name": "星紋絨駝", "rarity": "SR", "species_note": "星紋魔法絨駝", "asset_path": "assets/sprites/pets/pet_sr_02.png", "active": True, "asset_ready": True, "sort_order": 11},
    {"id": "pet_ssr_01", "display_name": "烈羽凰", "rarity": "SSR", "species_note": "火焰傳說鳳凰", "asset_path": "assets/sprites/pets/pet_ssr_01.png", "active": True, "asset_ready": True, "sort_order": 12},
    {"id": "pet_ssr_02", "display_name": "極光機狼", "rarity": "SSR", "species_note": "極光科技機械狼", "asset_path": "assets/sprites/pets/pet_ssr_02.png", "active": True, "asset_ready": True, "sort_order": 13},
]

GACHA_MACHINE_ASSETS = {
    "preview": "assets/sprites/gacha_machine/preview_composited.png",
    "base": "assets/sprites/gacha_machine/gacha_machine_base.png",
    "globe_idle": "assets/sprites/gacha_machine/capsule_globe_idle.png",
    "knob_idle": "assets/sprites/gacha_machine/knob_idle.png",
    "capsule_drop": "assets/sprites/gacha_machine/capsule_drop.png",
    "sparkle_fx": "assets/sprites/gacha_machine/sparkle_fx.png",
    "rarity_flash_ssr": "assets/sprites/gacha_machine/rarity_flash_ssr.png",
}

GACHA_RARITY_WEIGHTS = {
    "N": 70,
    "R": 22,
    "SR": 7,
    "SSR": 1,
}

GACHA_COST = 20
EVOLUTION_RULES = {
    "N": {"to": "R", "cost": 0, "label": "N → R"},
    "R": {"to": "SR", "cost": 20, "label": "R → SR"},
    "SR": {"to": "SSR", "cost": 50, "label": "SR → SSR"},
}

PET_CARD_ASSETS = {
    "pet_n_01": "assets/pets/cards/pet_n_01_card.png",
    "pet_n_02": "assets/pets/cards/pet_n_02_card.png",
    "pet_n_03": "assets/pets/cards/pet_n_03_card.png",
    "pet_n_04": "assets/pets/cards/pet_n_04_card.png",
    "pet_n_05": "assets/pets/cards/pet_n_05_card.png",
    "pet_n_06": "assets/pets/cards/pet_n_06_card.png",
    "pet_r_01": "assets/pets/cards/pet_r_01_card.png",
    "pet_r_02": "assets/pets/cards/pet_r_02_card.png",
    "pet_r_03": "assets/pets/cards/pet_r_03_card.png",
    "pet_sr_01": "assets/pets/cards/pet_sr_01_card.png",
    "pet_sr_02": "assets/pets/cards/pet_sr_02_card.png",
    "pet_ssr_01": "assets/pets/cards/pet_ssr_01_card.png",
    "pet_ssr_02": "assets/pets/cards/pet_ssr_02_card.png",
}

EVOLUTION_ICON_ASSETS = {
    "combine": "assets/evolution/icons/icon_combine.png",
    "training": "assets/evolution/icons/icon_training.png",
    "upgrade_arrow": "assets/evolution/icons/icon_upgrade_arrow.png",
    "score_cost": "assets/evolution/icons/icon_score_cost.png",
    "final_star": "assets/evolution/icons/icon_final_star.png",
}

# ── 功能 A：生成菜單時可勾選的「重點加強」身體素質項目（依類別排序，可複選） ──
# ⚠️ 這些字串會被功能 D 的階段建議用來「預選」，兩邊務必一致
EMPHASIS_OPTIONS = [
    # 肌力類
    "手部/握力", "腿部肌力", "旋轉力（核心轉體）", "肩部肌力與穩定", "核心穩定", "手腕/前臂力量",
    # 爆發 / 速度類
    "彈跳力", "爆發力", "移動速度", "敏捷性",
    # 控制 / 協調類
    "協調性", "反應速度", "平衡感", "節奏感/步法",
    # 健康 / 防護類
    "柔軟度/伸展", "心肺耐力/肌耐力",
]

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
    # 登入頁專用樣式：置中、限制寬度、放大欄位/按鈕/字級（手機友善）。
    # 只在登入頁注入，登入後其他頁不受影響。
    st.markdown(
        """
        <style>
        section.main > div.block-container {
            max-width: 540px; margin: 0 auto; padding-top: 2.2rem;
        }
        /* 放大輸入框 */
        .stTextInput input {
            font-size: 1.15rem !important; padding: 0.85rem 0.9rem !important;
            height: 3.2rem !important;
        }
        .stTextInput label p { font-size: 1.05rem !important; }
        /* 放大按鈕、加大點擊區 */
        .stButton > button {
            font-size: 1.2rem !important; padding: 0.85rem 1rem !important;
            min-height: 3.2rem; border-radius: 12px;
        }
        /* 分頁標籤放大好點 */
        .stTabs [data-baseweb="tab"] { font-size: 1.1rem; padding: 0.6rem 1rem; }
        /* 手機再加大一點 */
        @media (max-width: 640px) {
            section.main > div.block-container { padding-left: 1rem; padding-right: 1rem; }
            h1 { font-size: 1.8rem !important; text-align: center; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("# 🏐 排球訓練小幫手")
    st.markdown("")

    with st.expander("📖 第一次使用？點我看使用說明", expanded=False):
        st.markdown(
            """
#### 👦 小選手 / 家長看這裡

1. **登入**：在「👦 我是小選手」輸入你的名字 → 按「🏐 開始訓練！」
   （名字要請教練先幫你建立，找不到名字代表還沒建好喔）
2. **第一次登入**：填年級、年齡、性別、身高體重、還有家裡有哪些器材
3. **生成菜單**：選訓練模式
   - 🏐 **綜合訓練（含排球）**：可勾選想加強的技巧，AI 會安排排球訓練菜單
   - 💪 **身體素質強化（不帶球）**：純體能，不安排持球或排球技術
4. **跟著練**：在「📋 訓練菜單」每天有條列清單，按「▶ 開始訓練」用互動播放器——
   計時項目會一組一組自動倒數、計次項目做完一組點一下，有「嗶」聲和震動提醒 🔔
5. **打卡**：整天做完 → 按「✅ 完成第 N 天」。每個人照自己進度走，禮拜幾開始都沒關係，
   跳過的日子可以週末再補做 😊
6. **影片助理教練**：在「🎥 影片助理教練」上傳動作影片，AI 教練會給回饋和分數。
   這是獨立功能，不會影響訓練打卡。
7. **寫日誌**：每完成一週，要到「📔 訓練日誌」寫一篇（選心情 + 寫幾句話，照片可加可不加）。
   **寫完才能解鎖下一週的訓練** ✍️
8. **看成長**：在「📊 我的進度」看完成天數和身高體重成長曲線 📈

---

#### 🎓 教練看這裡

1. **登入**：在「🎓 教練後台」輸入後台密碼進入
2. **建名冊**：左側欄「➕ 新增學員」只要先建名字即可（小選手登入後自己完善資料）
3. **管理學員**：選好學員後，可「✏️ 編輯資料」或「🗑️ 刪除學員」（會二次確認）
4. **菜單**：可幫學員「🔄 重新生成菜單」
5. **看狀況**：檢視每位學員的進度、成長曲線，以及他們寫的訓練日誌（唯讀）
            """
        )

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
                # 把身分寫進網址，手機斷線/鎖屏/重整時自動還原，不必重新登入
                st.query_params["role"] = "student"
                st.query_params["name"] = student["name"]
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
        "target_skill": target_skill,  # 體能模式為 None；含球模式存所選技巧
        "total_weeks": total_weeks,
        "plan_started_at": datetime.now().astimezone().isoformat(),
    }).eq("id", student_id).execute()


def clear_curriculum(student_id: int) -> None:
    """清除目前菜單與菜單設定；不刪除打卡、日誌、影片分析等歷史紀錄。"""
    supabase.table("students").update({
        "curriculum": None,
        "training_mode": None,
        "target_skill": None,
        "plan_started_at": None,
        "total_weeks": 1,
    }).eq("id", student_id).execute()


def update_curriculum_json(student_id: int, curriculum: dict) -> None:
    """只更新菜單內容（手動微調用），不動模式/週數/起算日。"""
    supabase.table("students").update(
        {"curriculum": curriculum}
    ).eq("id", student_id).execute()


# ── 功能 D：賽事行事曆（全隊共用，教練維護）─────────────────────
def get_competitions() -> list[dict]:
    """取得全隊共用的賽事清單（依日期排序）。表未建好時回空清單，不影響其他功能。"""
    try:
        result = (
            supabase.table("competitions").select("*").order("event_date").execute()
        )
        return result.data or []
    except Exception as e:
        print(f"[WARN] 讀取 competitions 失敗（可能尚未建表）: {e}")
        return []


def add_competition(name: str, event_date: str, level: str) -> None:
    """新增一場比賽（event_date 為 ISO 日期字串 YYYY-MM-DD）。"""
    supabase.table("competitions").insert(
        {"name": name, "event_date": event_date, "level": level}
    ).execute()


def delete_competition(comp_id: int) -> None:
    supabase.table("competitions").delete().eq("id", comp_id).execute()


# 各「訓練階段」建議的重點加強（字串需與 EMPHASIS_OPTIONS 完全一致，才能自動預選）
_PHASE_EMPHASIS = {
    "準備期 / 休賽季": ["腿部肌力", "核心穩定", "旋轉力（核心轉體）", "肩部肌力與穩定", "爆發力", "心肺耐力/肌耐力"],
    "專項強化期": ["爆發力", "彈跳力", "敏捷性", "移動速度", "協調性"],
    "賽前調整期": ["柔軟度/伸展", "協調性", "平衡感", "反應速度"],
    "賽後過渡期": ["柔軟度/伸展", "平衡感", "協調性"],
    "一般準備期": ["核心穩定", "協調性", "敏捷性", "柔軟度/伸展"],
}
_PHASE_NOTE = {
    "準備期 / 休賽季": "離比賽還久，打基礎的好時機：加重大部位肌力、核心與基礎體能，訓練量可較大。",
    "專項強化期": "比賽接近了，把力量轉成場上能用的爆發與速度，並加強專項技術。",
    "賽前調整期": "賽前兩週請『減量』：降低訓練量與痠痛風險，以技術穩定、柔軟度、協調平衡與恢復為主，讓身體在比賽日達到最佳狀態。",
    "賽後過渡期": "比賽剛結束，安排緩和與恢復、低強度活動，讓身心充電。",
    "一般準備期": "目前沒有設定即將到來的比賽，以均衡發展、打好基礎為主。",
}


def compute_training_phase(competitions: list[dict], today=None) -> dict:
    """
    依賽事行事曆與今天日期，判定目前的訓練階段。
    回傳 dict：phase（階段名）、competition（最近的未來賽事 or None）、
              weeks_until / days_until（距該賽事）、emphasis（建議重點清單）、note（建議說明）。
    與「自我配速」不衝突：這裡只看真實日期距比賽多近，不影響打卡進度計算。
    """
    today = today or date.today()
    future, past = [], []
    for c in competitions:
        raw = c.get("event_date")
        if not raw:
            continue
        try:
            d = date.fromisoformat(str(raw)[:10])
        except ValueError:
            continue
        (future if d >= today else past).append((d, c))
    future.sort(key=lambda x: x[0])
    past.sort(key=lambda x: x[0], reverse=True)

    comp, days_until = None, None
    if future:
        d, comp = future[0]
        days_until = (d - today).days

    if days_until is not None and days_until <= 14:
        phase = "賽前調整期"
    elif days_until is not None and days_until <= 42:
        phase = "專項強化期"
    elif past and (today - past[0][0]).days <= 7:
        phase = "賽後過渡期"
    elif comp is not None:
        phase = "準備期 / 休賽季"
    else:
        phase = "一般準備期"

    return {
        "phase": phase,
        "competition": comp,
        "days_until": days_until,
        "weeks_until": (days_until // 7) if days_until is not None else None,
        "emphasis": _PHASE_EMPHASIS.get(phase, []),
        "note": _PHASE_NOTE.get(phase, ""),
    }


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


def get_point_events(student_id: int) -> list[dict]:
    """取得額外積分紀錄；point_events 未建好時回空清單，避免影響訓練。"""
    try:
        result = (
            supabase.table("point_events")
            .select("*")
            .eq("student_id", student_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        print(f"[WARN] 讀取 point_events 失敗（可能尚未執行 migrate_v7.sql）: {e}")
        return []


def add_point_event(
    student_id: int,
    points: int,
    reason: str,
    note: str = "",
    event_type: str = "manual",
    event_key: str | None = None,
    created_by: str = "coach",
) -> bool:
    """新增一筆額外積分；自動獎勵用 event_key 防重複。"""
    data = {
        "student_id": student_id,
        "points": points,
        "reason": reason,
        "note": note,
        "event_type": event_type,
        "event_key": event_key,
        "created_by": created_by,
    }
    try:
        supabase.table("point_events").insert(data).execute()
        return True
    except Exception as e:
        # unique event_key 衝突代表已發過，不視為錯誤
        print(f"[WARN] 新增積分紀錄失敗或已存在: {e}")
        return False


def point_events_total(events: list[dict]) -> int:
    return sum(e.get("points") or 0 for e in events)


def training_score_total(logs: list[dict]) -> int:
    return sum(l.get("score") or 0 for l in logs)


def total_score(logs: list[dict], point_events: list[dict]) -> int:
    return training_score_total(logs) + point_events_total(point_events)


def ensure_auto_point_rewards(student: dict, logs: list[dict]) -> None:
    """依目前完成進度補發自動里程碑獎勵；每套菜單每種獎勵只發一次。"""
    plan_key = str(student.get("plan_started_at") or student.get("created_at") or "no_plan")
    done = completed_sessions(logs)
    if done >= 5:
        add_point_event(
            student["id"], 15,
            "連續完成 5 天獎勵",
            "同一套菜單累積完成 5 個訓練日",
            event_type="auto_reward",
            event_key=f"{plan_key}:complete_5_days",
            created_by="system",
        )
    if done >= 15:
        add_point_event(
            student["id"], 20,
            "連續完成 3 週獎勵",
            "同一套菜單累積完成 15 個訓練日",
            event_type="auto_reward",
            event_key=f"{plan_key}:complete_3_weeks",
            created_by="system",
        )


def _asset_file(asset_path: str | None) -> str | None:
    """把資料庫內的素材相對路徑轉成 Streamlit 可讀的本機檔案路徑。"""
    if not asset_path:
        return None
    clean_path = asset_path.lstrip("/").replace("/", os.sep)
    local_path = os.path.join(APP_DIR, clean_path)
    return local_path if os.path.exists(local_path) else None


@st.cache_data(show_spinner=False)
def _image_data_uri(local_path: str) -> str | None:
    """把本機圖片轉成 HTML 可用的 data URI，方便置中與加背景。"""
    try:
        with open(local_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception as e:
        print(f"[WARN] 圖片轉換失敗: {e}")
        return None


def _pet_card_style(rarity: str) -> dict:
    styles = {
        "N": {
            "background": (
                "radial-gradient(circle at 50% 34%, rgba(255,255,255,.95) 0 18%, transparent 36%),"
                "linear-gradient(180deg, #bdebd1 0%, #e9fff4 48%, #9fd28a 49%, #6dbb71 100%)"
            ),
            "overlay": (
                "linear-gradient(90deg, transparent 0 23%, rgba(255,255,255,.32) 24% 25%, transparent 26% 49%, "
                "rgba(255,255,255,.28) 50% 51%, transparent 52% 75%, rgba(255,255,255,.24) 76% 77%, transparent 78%),"
                "linear-gradient(0deg, transparent 0 78%, rgba(255,255,255,.45) 79% 80%, transparent 81%)"
            ),
            "border": "#79c267",
            "shadow": "0 10px 22px rgba(50, 136, 81, .20)",
            "badge": "#2f8f57",
        },
        "R": {
            "background": (
                "radial-gradient(circle at 18% 18%, rgba(255,255,255,.9) 0 6%, transparent 17%),"
                "radial-gradient(circle at 80% 24%, rgba(129,230,217,.8) 0 8%, transparent 18%),"
                "linear-gradient(180deg, #dbeafe 0%, #a7f3d0 48%, #64748b 49%, #334155 100%)"
            ),
            "overlay": (
                "linear-gradient(90deg, rgba(255,255,255,.18) 0 10%, transparent 10% 20%),"
                "linear-gradient(0deg, transparent 0 73%, rgba(255,255,255,.35) 74% 75%, transparent 76%),"
                "repeating-linear-gradient(90deg, transparent 0 30px, rgba(255,255,255,.2) 31px 32px)"
            ),
            "border": "#22c7a9",
            "shadow": "0 12px 26px rgba(20, 184, 166, .26)",
            "badge": "#0f766e",
        },
        "SR": {
            "background": (
                "radial-gradient(circle at 20% 22%, rgba(255,255,255,.95) 0 4%, transparent 10%),"
                "radial-gradient(circle at 78% 18%, rgba(255,255,255,.9) 0 3%, transparent 9%),"
                "radial-gradient(circle at 58% 30%, rgba(251,191,36,.8) 0 8%, transparent 20%),"
                "linear-gradient(180deg, #fef3c7 0%, #f9a8d4 42%, #7c3aed 43%, #312e81 100%)"
            ),
            "overlay": (
                "linear-gradient(0deg, transparent 0 70%, rgba(255,255,255,.28) 71% 72%, transparent 73%),"
                "repeating-linear-gradient(115deg, transparent 0 28px, rgba(255,255,255,.20) 29px 30px)"
            ),
            "border": "#f59e0b",
            "shadow": "0 14px 30px rgba(245, 158, 11, .30)",
            "badge": "#b45309",
        },
        "SSR": {
            "background": (
                "radial-gradient(circle at 50% 28%, rgba(255,255,255,.98) 0 10%, rgba(253,224,71,.45) 18%, transparent 34%),"
                "radial-gradient(circle at 20% 22%, rgba(236,72,153,.75) 0 7%, transparent 18%),"
                "radial-gradient(circle at 82% 20%, rgba(34,211,238,.8) 0 8%, transparent 20%),"
                "linear-gradient(180deg, #f5d0fe 0%, #a78bfa 40%, #4338ca 41%, #111827 100%)"
            ),
            "overlay": (
                "linear-gradient(125deg, transparent 0 18%, rgba(255,255,255,.42) 19% 20%, transparent 21% 43%, "
                "rgba(255,255,255,.28) 44% 45%, transparent 46% 75%),"
                "repeating-radial-gradient(circle at 50% 35%, rgba(255,255,255,.22) 0 2px, transparent 3px 18px)"
            ),
            "border": "#a855f7",
            "shadow": "0 16px 34px rgba(168, 85, 247, .38)",
            "badge": "#7e22ce",
        },
    }
    return styles.get(rarity, styles["N"])


def render_centered_pet_art(pet: dict, width: int = 150, height: int = 150) -> None:
    """用稀有度背景顯示寵物，解決透明圖偏左與白底太空的問題。"""
    pet_file = _asset_file(pet.get("asset_path"))
    if not pet_file:
        st.info("寵物素材尚未找到。")
        return
    data_uri = _image_data_uri(pet_file)
    if not data_uri:
        st.image(pet_file, width=width)
        return
    rarity = pet.get("rarity") or "N"
    style = _pet_card_style(rarity)
    st.markdown(
        f"""
        <div style="
            width:100%;
            min-height:{height + 28}px;
            position:relative;
            display:flex;
            align-items:center;
            justify-content:center;
            overflow:hidden;
            background:{style['background']};
            border:1px solid {style['border']};
            border-radius:14px;
            padding:14px;
            box-sizing:border-box;
            box-shadow:{style['shadow']};
        ">
            <div style="
                position:absolute;
                inset:0;
                background:{style['overlay']};
                opacity:.95;
                pointer-events:none;
            "></div>
            <div style="
                position:absolute;
                top:8px;
                right:9px;
                padding:2px 8px;
                border-radius:999px;
                background:{style['badge']};
                color:white;
                font-size:11px;
                font-weight:700;
                letter-spacing:0;
            ">{rarity}</div>
            <img src="{data_uri}" style="
                width:{width}px;
                height:{height}px;
                object-fit:contain;
                display:block;
                margin:0 auto;
                position:relative;
                z-index:1;
                filter:drop-shadow(0 8px 10px rgba(15,23,42,.22));
            " />
        </div>
        """,
        unsafe_allow_html=True,
    )


def _pet_card_path(pet_id: str | None) -> str | None:
    if not pet_id:
        return None
    return _asset_file(PET_CARD_ASSETS.get(pet_id))


def render_pet_card_image(pet: dict, width: int = 210) -> None:
    """顯示 handoff v1.1 的完整寵物卡圖；不是前端重畫卡框。"""
    card_path = _pet_card_path(pet.get("id"))
    if card_path:
        st.image(card_path, width=width)
    else:
        render_centered_pet_art(pet, width=min(width, 160), height=min(width, 160))


def render_icon_asset(icon_key: str, width: int = 44) -> None:
    icon_path = _asset_file(EVOLUTION_ICON_ASSETS.get(icon_key))
    if icon_path:
        st.image(icon_path, width=width)


def _seed_lookup(seed_rows: list[dict]) -> dict[str, dict]:
    return {row["id"]: row for row in seed_rows}


def get_avatar_templates(active_only: bool = False) -> list[dict]:
    """取得角色模板；若尚未建立 Supabase 表，使用本機 seed 保護頁面。"""
    try:
        query = supabase.table("avatar_templates").select("*").order("sort_order")
        if active_only:
            query = query.eq("active", True).eq("asset_ready", True)
        result = query.execute()
        rows = result.data or []
    except Exception as e:
        print(f"[WARN] 讀取 avatar_templates 失敗（可能尚未執行 migrate_v8.sql）: {e}")
        rows = AVATAR_TEMPLATE_SEED

    if active_only:
        rows = [r for r in rows if r.get("active") and r.get("asset_ready")]
    return sorted(rows, key=lambda r: r.get("sort_order") or 999)


def get_pet_catalog(active_only: bool = False) -> list[dict]:
    """取得寵物圖鑑；若尚未建立 Supabase 表，使用本機 seed 保護頁面。"""
    try:
        query = supabase.table("pet_catalog").select("*").order("sort_order")
        if active_only:
            query = query.eq("active", True).eq("asset_ready", True)
        result = query.execute()
        rows = result.data or []
    except Exception as e:
        print(f"[WARN] 讀取 pet_catalog 失敗（可能尚未執行 migrate_v8.sql）: {e}")
        rows = PET_CATALOG_SEED

    if active_only:
        rows = [r for r in rows if r.get("active") and r.get("asset_ready")]
    return sorted(rows, key=lambda r: r.get("sort_order") or 999)


def get_avatar_profile(student: dict) -> dict:
    """取得學生角色設定，沒有設定時給不寫入資料庫的預設值。"""
    default_profile = {
        "student_id": student["id"],
        "nickname": student.get("name") or "",
        "avatar_template_id": "beginner",
        "companion_pet_id": "pet_n_01",
    }
    try:
        result = (
            supabase.table("avatar_profiles")
            .select("*")
            .eq("student_id", student["id"])
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else default_profile
    except Exception as e:
        print(f"[WARN] 讀取 avatar_profiles 失敗（可能尚未執行 migrate_v8.sql）: {e}")
        return default_profile


def save_avatar_profile(
    student_id: int,
    nickname: str,
    avatar_template_id: str,
    companion_pet_id: str | None,
) -> bool:
    data = {
        "student_id": student_id,
        "nickname": nickname,
        "avatar_template_id": avatar_template_id,
        "companion_pet_id": companion_pet_id,
        "updated_at": datetime.now().isoformat(),
    }
    try:
        supabase.table("avatar_profiles").upsert(data, on_conflict="student_id").execute()
        return True
    except Exception as e:
        print(f"[WARN] 儲存 avatar_profiles 失敗（可能尚未執行 migrate_v8.sql）: {e}")
        return False


def ensure_starter_pet(student_id: int) -> None:
    """第一版尚未接扭蛋，先確保每位學生至少有一隻起始寵物可攜帶。"""
    try:
        existing = (
            supabase.table("student_pets")
            .select("id")
            .eq("student_id", student_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            return
        supabase.table("student_pets").insert({
            "student_id": student_id,
            "pet_id": "pet_n_01",
            "quantity": 1,
            "source": "starter",
        }).execute()
    except Exception as e:
        print(f"[WARN] 補發起始寵物失敗（可能尚未執行 migrate_v8.sql）: {e}")


def get_student_pets(student_id: int) -> list[dict]:
    """取得學生已擁有的寵物，合併 pet_catalog 顯示資料。"""
    ensure_starter_pet(student_id)
    pet_lookup = _seed_lookup(get_pet_catalog(active_only=True))
    try:
        result = (
            supabase.table("student_pets")
            .select("*")
            .eq("student_id", student_id)
            .order("acquired_at", desc=True)
            .execute()
        )
        rows = result.data or []
    except Exception as e:
        print(f"[WARN] 讀取 student_pets 失敗（可能尚未執行 migrate_v8.sql）: {e}")
        rows = [{"pet_id": "pet_n_01", "quantity": 1, "source": "starter"}]

    owned = []
    for row in rows:
        pet = pet_lookup.get(row.get("pet_id"))
        if not pet:
            continue
        owned.append({**pet, "quantity": row.get("quantity") or 1, "source": row.get("source")})

    if not owned and "pet_n_01" in pet_lookup:
        owned.append({**pet_lookup["pet_n_01"], "quantity": 1, "source": "starter"})
    return sorted(owned, key=lambda r: r.get("sort_order") or 999)


def grant_student_pet(student_id: int, pet_id: str, source: str = "gacha") -> bool:
    """把抽到的寵物加入學生背包；重複抽到同一隻就增加數量。"""
    try:
        existing = (
            supabase.table("student_pets")
            .select("*")
            .eq("student_id", student_id)
            .eq("pet_id", pet_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            current = existing.data[0]
            supabase.table("student_pets").update({
                "quantity": (current.get("quantity") or 1) + 1,
                "source": source,
            }).eq("id", current["id"]).execute()
        else:
            supabase.table("student_pets").insert({
                "student_id": student_id,
                "pet_id": pet_id,
                "quantity": 1,
                "source": source,
            }).execute()
        return True
    except Exception as e:
        print(f"[WARN] 寵物寫入失敗（可能尚未執行 migrate_v8.sql）: {e}")
        return False


def change_student_pet_quantity(
    student_id: int,
    pet_id: str,
    delta: int,
    source: str = "evolution",
) -> bool:
    """調整寵物持有數量；數量歸零時移除該列。"""
    try:
        existing = (
            supabase.table("student_pets")
            .select("*")
            .eq("student_id", student_id)
            .eq("pet_id", pet_id)
            .limit(1)
            .execute()
        )
        if not existing.data:
            return False
        current = existing.data[0]
        new_quantity = (current.get("quantity") or 0) + delta
        if new_quantity <= 0:
            supabase.table("student_pets").delete().eq("id", current["id"]).execute()
        else:
            supabase.table("student_pets").update({
                "quantity": new_quantity,
                "source": source,
            }).eq("id", current["id"]).execute()
        return True
    except Exception as e:
        print(f"[WARN] 寵物數量調整失敗: {e}")
        return False


def draw_gacha_pet(pets: list[dict]) -> dict | None:
    """依稀有度權重抽一隻寵物。"""
    if not pets:
        return None
    rarity_pool = {}
    for pet in pets:
        rarity_pool.setdefault(pet.get("rarity") or "N", []).append(pet)
    rarities = [r for r in GACHA_RARITY_WEIGHTS if rarity_pool.get(r)]
    weights = [GACHA_RARITY_WEIGHTS[r] for r in rarities]
    picked_rarity = random.choices(rarities, weights=weights, k=1)[0]
    return random.choice(rarity_pool[picked_rarity])


def draw_pet_by_rarity(pets: list[dict], rarity: str) -> dict | None:
    candidates = [p for p in pets if p.get("rarity") == rarity]
    return random.choice(candidates) if candidates else None


def available_evolution_count(owned_pets: list[dict], rarity: str) -> int:
    return sum(p.get("quantity") or 0 for p in owned_pets if p.get("rarity") == rarity) // 3


def consume_three_pets_by_rarity(student_id: int, owned_pets: list[dict], rarity: str) -> bool:
    """消耗任意 3 隻同稀有度寵物，優先消耗持有數較多的寵物。"""
    candidates = sorted(
        [p for p in owned_pets if p.get("rarity") == rarity and (p.get("quantity") or 0) > 0],
        key=lambda p: (-(p.get("quantity") or 0), p.get("sort_order") or 999),
    )
    if sum(p.get("quantity") or 0 for p in candidates) < 3:
        return False

    remaining = 3
    for pet in candidates:
        if remaining <= 0:
            break
        consume = min(remaining, pet.get("quantity") or 0)
        if consume > 0 and not change_student_pet_quantity(student_id, pet["id"], -consume):
            return False
        remaining -= consume
    return remaining == 0


def upload_video_to_supabase(student_id: int, video_bytes: bytes, filename: str) -> str:
    """上傳影片至 Supabase Storage，回傳公開網址"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"{student_id}/{timestamp}_{filename}"
    supabase.storage.from_(BUCKET_NAME).upload(
        path, video_bytes, file_options={"content-type": "video/mp4"}
    )
    return supabase.storage.from_(BUCKET_NAME).get_public_url(path)


def save_video_analysis(
    student_id: int,
    target_skill: str,
    video_url: str | None,
    feedback: dict,
) -> dict | None:
    """儲存獨立影片助理教練分析紀錄（不綁訓練日打卡）。"""
    data = {
        "student_id": student_id,
        "target_skill": target_skill,
        "video_url": video_url,
        "ai_feedback": json.dumps(feedback, ensure_ascii=False),
        "score": feedback.get("score"),
    }
    result = supabase.table("video_analyses").insert(data).execute()
    return result.data[0] if result.data else None


def get_video_analyses(student_id: int) -> list[dict]:
    """取得獨立影片助理教練分析紀錄；未建表時友善回空清單。"""
    try:
        result = (
            supabase.table("video_analyses")
            .select("*")
            .eq("student_id", student_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        print(f"[WARN] 讀取影片分析紀錄失敗（可能尚未執行 migrate_v6.sql）: {e}")
        return []


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
  - 計時型 mode="time"：填 seconds（每組秒數）與 sets（組數，未指定則 1 組），例如棒式 30 秒 × 3 組、熱身 90 秒 × 1 組
- 每個訓練日的 items 必須依序包含三段：①第 1 項熱身（計時 60–120 秒）②中間 1–4 項主練習（圍繞當日主題，計次或計時）③最後 1 項收操伸展（計時 60–120 秒）
- 每個項目要有：name（簡短任務名）、mode、對應的 reps+sets 或 seconds+sets、equipment（用到的器材陣列，沒有就空陣列）、note（一句國小生看得懂的動作提醒）
- 每個訓練日填 focus（今天主題一句話）與 duration_min（預估總分鐘，約等於所有項目時間總和）
- 數量與強度依年級與體型調整，難度逐週提升，每週主題明確
- 每週安排 5 個訓練日（週一至週五），第 6、7 天為休息日（is_rest=true，items 給空陣列，改用 task 寫一句休息建議）
- 每天附一句 tip「小叮嚀」：訓練日輪流給「訓練安全、休息恢復、飲食營養」三類叮嚀（例：練完 30 分鐘內喝牛奶或吃點蛋白質、睡滿 9 小時、訓練前 1 小時不要吃太飽、多喝水少含糖飲料）；休息日的 tip 以恢復與飲食為主。語氣親切、講給小朋友和家長聽
- 每週額外附一句 parent_note「家長小提醒」：用親切口吻提醒家長這週可以怎麼陪伴、觀察孩子的哪個重點、或如何鼓勵"""

_CURRICULUM_JSON_SCHEMA = """⚠️ 請「只」回傳以下 JSON，不要加入任何說明文字（計次 items 填 reps+sets；計時 items 填 seconds+sets）：
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
            {"name": "開合跳熱身", "mode": "time", "seconds": 60, "sets": 1, "equipment": [], "note": "輕鬆跳，把身體活動開"},
            {"name": "對牆低手墊球", "mode": "reps", "reps": 15, "sets": 3, "equipment": ["排球", "牆壁（對牆練習）"], "note": "手臂打直夾緊，用前臂接球"},
            {"name": "棒式挑戰", "mode": "time", "seconds": 30, "sets": 3, "equipment": [], "note": "肚子收緊，身體像一條直線"}
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
    status_cb=None, emphasis: list[str] | None = None,
    phase_info: dict | None = None,
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

    # 功能 A：重點加強（特別加重某些身體素質）
    emphasis_clause = ""
    if emphasis:
        emphasis_clause = (
            "【重點加強】在維持整體均衡與循序漸進的前提下，請特別「加重」以下身體素質的比重，"
            "並優先挑選能訓練到這些面向的動作：" + "、".join(emphasis) + "。\n"
            "⚠️ 學員是國小生，凡肌力/爆發類一律以自體重與輕負荷、動作品質與安全為主，"
            "不可安排大重量負重訓練。"
        )

    # 功能 D：賽事週期化（依距離比賽遠近調整量與強度）
    phase_clause = ""
    if phase_info and phase_info.get("competition"):
        comp = phase_info["competition"]
        wk = phase_info.get("weeks_until")
        phase_clause = (
            f"【賽事週期】距離比賽「{comp.get('name','')}」（{comp.get('event_date','')}）"
            f"約 {wk} 週，目前處於「{phase_info.get('phase')}」。{phase_info.get('note','')}\n"
            "請讓整套菜單的訓練量與強度安排符合此階段；若為賽前調整期，務必明顯減量、"
            "避免造成痠痛與疲勞累積。"
        )

    extras = "\n\n".join(c for c in [emphasis_clause, phase_clause] if c)
    extras = ("\n\n" + extras) if extras else ""

    prompt = (
        intro + "\n\n" + profile + "\n\n" + _GRADE_RULES + "\n\n"
        + _EQUIPMENT_RULES + "\n\n" + focus_rules + extras + "\n\n" + _STRUCTURE_RULES
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


def calculate_stats(student: dict, logs: list[dict], point_events: list[dict] | None = None) -> dict:
    """計算訓練統計數字"""
    point_events = point_events or []
    total_training_days = (student.get("total_weeks") or 1) * DAYS_PER_WEEK  # 每週 5 個訓練日
    completed_n = completed_sessions(logs)  # 以 (週,天) 去重的完成天數
    training_score = training_score_total(logs)
    bonus_score = point_events_total(point_events)
    progress_pct = min(completed_n / total_training_days * 100, 100) if total_training_days else 0

    return {
        "completed_days": completed_n,
        "total_training_days": total_training_days,
        "progress_pct": progress_pct,
        "training_score": training_score,
        "bonus_score": bonus_score,
        "total_score": training_score + bonus_score,
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


def render_competition_manager():
    """功能 D：教練維護全隊共用的賽事行事曆（新增 / 刪除）。"""
    with st.expander("🗓️ 賽事行事曆（教練設定，全隊共用）", expanded=False):
        comps = get_competitions()
        if comps:
            st.caption("目前已排定的比賽：")
            for c in comps:
                col1, col2 = st.columns([5, 1])
                lv = f"（{c['level']}）" if c.get("level") else ""
                col1.markdown(f"📅 **{c.get('event_date','')}**　{c.get('name','')}{lv}")
                if col2.button("刪除", key=f"delcomp_{c['id']}"):
                    delete_competition(c["id"])
                    st.rerun()
            st.markdown("---")
        st.caption("新增一場比賽：")
        with st.form("add_competition_form", clear_on_submit=True):
            name = st.text_input("比賽名稱", placeholder="例：XX盃少年排球賽")
            cdate = st.date_input("比賽日期")
            level = st.selectbox("重要程度", ["A級（重點賽）", "B級（一般賽）"], index=1)
            if st.form_submit_button("➕ 新增比賽", use_container_width=True):
                if name.strip():
                    add_competition(name.strip(), cdate.isoformat(), level)
                    st.toast("已新增比賽")
                    st.rerun()
                else:
                    st.warning("請填比賽名稱。")


def render_upcoming_competitions():
    """功能 D：學生側欄唯讀顯示近期比賽（只看得到，不能改）。"""
    comps = get_competitions()
    today = date.today()
    upcoming = []
    for c in comps:
        raw = c.get("event_date")
        if not raw:
            continue
        try:
            d = date.fromisoformat(str(raw)[:10])
        except ValueError:
            continue
        if d >= today:
            upcoming.append((d, c))
    if not upcoming:
        return
    upcoming.sort(key=lambda x: x[0])
    st.markdown("### 🗓️ 近期比賽")
    for d, c in upcoming[:5]:
        days = (d - today).days
        when = "🔥 就是今天！" if days == 0 else f"還有 {days} 天"
        st.markdown(f"📅 **{c.get('event_date','')}**　{c.get('name','')}")
        st.caption(when)


def render_phase_reminder(phase_info: dict):
    """功能 D：生成菜單前的階段提醒橫幅（所有人可見）。"""
    comp = phase_info.get("competition")
    emph = "、".join(phase_info["emphasis"]) if phase_info.get("emphasis") else "均衡發展"
    if comp:
        wk = phase_info.get("weeks_until")
        days = phase_info.get("days_until")
        when = f"還有 **{wk} 週**（約 {days} 天）" if wk and wk >= 1 else f"剩 **{days} 天**"
        st.info(
            f"🏐 距離【{comp.get('name','')}】{when}（{comp.get('event_date','')}）\n\n"
            f"→ 目前屬「**{phase_info.get('phase')}**」。{phase_info.get('note','')}\n\n"
            f"💡 建議重點：**{emph}**（已幫你預選在下方，可自行增減）"
        )
    else:
        st.info(
            f"🗓️ 目前沒有設定即將到來的比賽（屬「{phase_info.get('phase')}」）。"
            f"{phase_info.get('note','')}　建議重點：{emph}。"
        )


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

    # 功能 D：賽事階段提醒（賽事行事曆改在教練側欄維護，避免重複表單；此處只顯示提醒）
    phase_info = compute_training_phase(get_competitions())
    render_phase_reminder(phase_info)

    training_mode = st.radio(
        "選擇訓練模式",
        TRAINING_MODES,
        captions=[
            "排球技巧為主，AI 會安排含球訓練",
            "純體能基礎（敏捷、肌力、協調），不帶球、不安排排球技術",
        ],
    )

    target_skill = None
    if training_mode == TRAINING_MODE_BALL:
        picked_skills = st.multiselect(
            "🎯 想加強的排球技巧（可複選）", TARGET_SKILLS,
            default=[TARGET_SKILLS[0]],
            help="可以選多項，AI 會把這些技巧都排進菜單。影片分析請到獨立的「影片助理教練」。",
        )
        target_skill = "、".join(picked_skills)  # 以「、」串成一個字串存進 target_skill 欄位

    # 功能 A：想重點加強的身體素質（預設帶入賽事階段建議，可自行增減）
    emphasis = st.multiselect(
        "💪 想重點加強的地方（可複選，依比賽階段已預選建議項目）",
        EMPHASIS_OPTIONS,
        default=[e for e in phase_info.get("emphasis", []) if e in EMPHASIS_OPTIONS],
        help="AI 會在維持均衡的前提下加重這些面向；國小生的肌力/爆發一律以自體重、輕負荷為主",
    )

    total_weeks = st.slider(
        "📅 訓練週期（週）", min_value=1, max_value=12, value=4,
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
                    s, training_mode, target_skill, total_weeks, status_cb=on_retry,
                    emphasis=emphasis, phase_info=phase_info,
                )
                # 把這次的重點加強與階段一併存進菜單 JSON（免 migration，方便日後回顧）
                if emphasis:
                    curriculum["emphasis"] = emphasis
                if phase_info.get("competition"):
                    curriculum["phase"] = phase_info.get("phase")
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
        sets = it.get("sets") or 1
        base = f"⏱️ {_format_seconds(it.get('seconds'))}"
        return f"{base} × {sets} 組" if sets > 1 else base
    reps = it.get("reps") or 0
    sets = it.get("sets") or 1
    return f"🔁 {reps} 下 × {sets} 組" if sets > 1 else f"🔁 {reps} 下"


# 互動式訓練播放器（純前端 JS，計時/計次都在瀏覽器跑，不佔伺服器、手機順暢）
_SESSION_HTML = r"""
<div id="vt">
  <style>
    html, body { margin:0; padding:0; overflow:auto; -webkit-overflow-scrolling:touch; }
    #vt { font-family: -apple-system, "Microsoft JhengHei", sans-serif; color:#1f2937; padding:0 0 92px; }
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
    #vt #controls {
      position:sticky; bottom:0; z-index:10; margin-top:10px; padding:10px 0 12px;
      background:linear-gradient(180deg, rgba(255,255,255,.78), #fff 24%);
      display:flex; flex-wrap:wrap; gap:6px;
    }
    #vt #done { display:none; background:#ecfdf5; border:2px solid #22c55e; border-radius:14px;
      padding:24px; text-align:center; font-size:1.3rem; font-weight:800; color:#15803d; margin-top:6px; }
    @media (max-width: 520px) {
      #vt { padding-bottom:118px; }
      #vt button { width:100%; min-height:48px; margin:0; font-size:1.02rem; }
      #vt #controls { gap:8px; }
      #vt #timer { font-size:3rem; }
      #vt #card { padding:14px; }
      #vt #iname { font-size:1.22rem; }
    }
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
      reps.style.display='block'; timer.style.display='block';
      remaining = it.seconds|0; timer.textContent = fmt(remaining);
      drawTime(it);
      ctr.innerHTML = '<button id="pp">⏸ 暫停</button>'
        + '<button id="rs" class="sec">↺ 本組重來</button>'
        + '<button id="ns" class="sec" disabled>下一組 →</button>'
        + '<button id="prev" class="sec">← 上一項</button>'
        + '<button id="nx" class="sec">下一項 →</button>';
      $('pp').onclick = togglePause;
      $('rs').onclick = function(){ remaining = it.seconds|0; timer.textContent = fmt(remaining); startTimer(); };
      $('ns').onclick = function(){ remaining = it.seconds|0; timer.textContent = fmt(remaining); startTimer(); this.disabled = true; };
      $('prev').onclick = prev;
      $('nx').onclick = next;
      startTimer();
    } else {
      timer.style.display='none'; reps.style.display='block';
      const sets = it.sets||1;
      drawReps(it);
      ctr.innerHTML = '<button id="ok">✓ 完成一組</button>'
        + '<button id="prev" class="sec">← 上一項</button>'
        + '<button id="nx" class="sec">下一項 →</button>';
      $('prev').onclick = prev;
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

  function drawTime(it){
    const sets = it.sets||1, sec = it.seconds||0;
    let dots=''; for(let i=0;i<sets;i++) dots += (i<setsDone ? '🟢' : '⚪');
    $('reps').innerHTML = '目標：每組 <b>'+fmt(sec)+'</b>，共 <b>'+sets+'</b> 組<br>'
      + '<span style="font-size:1.8rem">'+dots+'</span><br>'
      + '已完成 '+setsDone+' / '+sets+' 組';
  }
  function markDoneTime(){
    $('reps').innerHTML += '<br>✅ 這一項完成！';
  }

  function startTimer(){
    clearInterval(timerId); paused=false;
    const pp=$('pp'); if(pp) pp.textContent='⏸ 暫停';
    if(pp) pp.disabled=false;
    const ns=$('ns'); if(ns) ns.disabled=true;
    timerId = setInterval(function(){
      if(paused) return;
      remaining--; $('timer').textContent = fmt(remaining);
      if(remaining <= 0){
        clearInterval(timerId); $('timer').textContent = '⏰ 時間到！';
        const it = ITEMS[idx];
        if(it && it.mode === 'time'){
          const sets = it.sets||1;
          if(setsDone < sets) setsDone++;
          drawTime(it);
          if(setsDone >= sets){
            const nx=$('nx'); if(nx) nx.className='';
            const ns=$('ns'); if(ns) ns.disabled=true;
            markDoneTime();
          } else {
            const ns=$('ns'); if(ns) ns.disabled=false;
          }
        } else {
          const nx=$('nx'); if(nx) nx.className='';
        }
        const pp=$('pp'); if(pp) pp.disabled=true;
        alertDone();
      }
    }, 1000);
  }
  function togglePause(){ paused=!paused; $('pp').textContent = paused ? '▶ 繼續' : '⏸ 暫停'; }
  function prev(){ clearInterval(timerId); idx = Math.max(0, idx-1); showItem(); }
  function next(){
    clearInterval(timerId);
    if(!confirm('確定要前往下一項嗎？如果這一項還沒做完，請按「取消」回來繼續。')) return;
    idx++; showItem();
  }
  function finish(){
    clearInterval(timerId);
    if(!confirm('今天全部項目都做完了嗎？確認後再去打卡領積分。')){
      idx = Math.max(0, ITEMS.length-1); showItem(); return;
    }
    $('session').style.display='none'; $('done').style.display='block'; alertFinish();
  }
})();
</script>
"""


def render_training_session(items: list[dict]) -> None:
    """為一個訓練日的 items 渲染互動式播放器（計時倒數 / 計次完成）。"""
    if not items:
        return
    payload = json.dumps(items, ensure_ascii=False)
    components.html(_SESSION_HTML.replace("__ITEMS__", payload), height=680, scrolling=True)


def _to_int(v, default=0) -> int:
    """安全把表格欄位值轉成整數（空白/NaN 回預設值）"""
    try:
        return default if pd.isna(v) else int(v)
    except (TypeError, ValueError):
        return default


def _editor_key(week_num: int, day_id: int, idx: int | str, field: str) -> str:
    return f"panel_editor_w{week_num}_d{day_id}_{idx}_{field}"


def _ensure_editor_value(key: str, value):
    if key not in st.session_state:
        st.session_state[key] = value


def _bump_editor_number(key: str, delta: int, min_value: int, max_value: int) -> None:
    current = _to_int(st.session_state.get(key), min_value)
    st.session_state[key] = max(min_value, min(max_value, current + delta))


def _clear_day_editor_state(week_num: int, day_id: int) -> None:
    prefix = f"panel_editor_w{week_num}_d{day_id}_"
    for key in list(st.session_state.keys()):
        if str(key).startswith(prefix):
            st.session_state.pop(key, None)


def _save_day_items(student: dict, curriculum: dict, week_num: int, day: dict, new_items: list[dict]) -> None:
    if not new_items:
        st.warning("至少要保留一個項目喔！")
        return
    day["items"] = new_items
    update_curriculum_json(student["id"], curriculum)
    st.session_state.curriculum = curriculum
    _clear_day_editor_state(week_num, day["day"])
    st.success("✅ 已儲存這天的修改！")
    st.rerun()


def _read_panel_items(week_num: int, day_id: int, item_count: int) -> list[dict]:
    new_items = []
    for idx in range(item_count):
        name = str(st.session_state.get(_editor_key(week_num, day_id, idx, "name"), "")).strip()
        if not name:
            continue
        mode_label = st.session_state.get(_editor_key(week_num, day_id, idx, "mode"), "計次")
        if mode_label == "計時":
            item = {
                "name": name,
                "mode": "time",
                "seconds": _to_int(st.session_state.get(_editor_key(week_num, day_id, idx, "seconds")), 30),
                "sets": _to_int(st.session_state.get(_editor_key(week_num, day_id, idx, "sets")), 1),
            }
        else:
            item = {
                "name": name,
                "mode": "reps",
                "reps": _to_int(st.session_state.get(_editor_key(week_num, day_id, idx, "reps")), 10),
                "sets": _to_int(st.session_state.get(_editor_key(week_num, day_id, idx, "sets")), 1),
            }
        item["equipment"] = st.session_state.get(_editor_key(week_num, day_id, idx, "equipment"), [])
        item["note"] = str(st.session_state.get(_editor_key(week_num, day_id, idx, "note"), "")).strip()
        new_items.append(item)
    return new_items


def _move_item(items: list[dict], from_idx: int, to_idx: int) -> list[dict]:
    new_items = list(items)
    if from_idx < 0 or from_idx >= len(new_items) or to_idx < 0 or to_idx >= len(new_items):
        return new_items
    item = new_items.pop(from_idx)
    new_items.insert(to_idx, item)
    return new_items


def render_day_editor(student: dict, curriculum: dict, week_num: int, day: dict) -> None:
    """用面板微調某一天的項目（改秒數/次數/組數、增刪項目）。教練與家長皆可用。"""
    if not st.toggle("✏️ 編輯這天的份量 / 項目", key=f"edit_w{week_num}_d{day['day']}"):
        return

    items = day.get("items") or []
    st.caption(
        "用下方小面板調整就好：計時看秒數和組數，計次看次數和組數。"
        "調整完記得按最下面的「儲存這天」。"
    )

    for idx, it in enumerate(items):
        day_id = day["day"]
        name_key = _editor_key(week_num, day_id, idx, "name")
        mode_key = _editor_key(week_num, day_id, idx, "mode")
        seconds_key = _editor_key(week_num, day_id, idx, "seconds")
        reps_key = _editor_key(week_num, day_id, idx, "reps")
        sets_key = _editor_key(week_num, day_id, idx, "sets")
        equipment_key = _editor_key(week_num, day_id, idx, "equipment")
        note_key = _editor_key(week_num, day_id, idx, "note")

        _ensure_editor_value(name_key, it.get("name", ""))
        _ensure_editor_value(mode_key, "計時" if it.get("mode") == "time" else "計次")
        _ensure_editor_value(seconds_key, int(it.get("seconds") or 60))
        _ensure_editor_value(reps_key, int(it.get("reps") or 10))
        _ensure_editor_value(sets_key, int(it.get("sets") or 1))
        _ensure_editor_value(equipment_key, it.get("equipment") or [])
        _ensure_editor_value(note_key, it.get("note", ""))

        with st.container(border=True):
            top_a, top_up, top_down, top_del = st.columns([3, 1, 1, 1])
            top_a.text_input("動作名稱", key=name_key, placeholder="例：對牆低手墊球")
            if top_up.button("↑ 上移", key=_editor_key(week_num, day_id, idx, "move_up"), use_container_width=True, disabled=(idx == 0)):
                current_items = _read_panel_items(week_num, day_id, len(items))
                _save_day_items(student, curriculum, week_num, day, _move_item(current_items, idx, idx - 1))
                return
            if top_down.button("↓ 下移", key=_editor_key(week_num, day_id, idx, "move_down"), use_container_width=True, disabled=(idx == len(items) - 1)):
                current_items = _read_panel_items(week_num, day_id, len(items))
                _save_day_items(student, curriculum, week_num, day, _move_item(current_items, idx, idx + 1))
                return
            if top_del.button("🗑️ 刪除", key=_editor_key(week_num, day_id, idx, "delete"), use_container_width=True):
                new_items = _read_panel_items(week_num, day_id, len(items))
                if idx < len(new_items):
                    new_items.pop(idx)
                _save_day_items(student, curriculum, week_num, day, new_items)
                return

            st.radio("類型", ["計次", "計時"], key=mode_key, horizontal=True)

            if st.session_state[mode_key] == "計時":
                minus, value, plus = st.columns([1, 2, 1])
                if minus.button("-10 秒", key=_editor_key(week_num, day_id, idx, "seconds_minus"), use_container_width=True):
                    _bump_editor_number(seconds_key, -10, 10, 1800)
                if plus.button("+10 秒", key=_editor_key(week_num, day_id, idx, "seconds_plus"), use_container_width=True):
                    _bump_editor_number(seconds_key, 10, 10, 1800)
                value.number_input("每組幾秒", min_value=10, max_value=1800, step=10, key=seconds_key)

                s_minus, s_value, s_plus = st.columns([1, 2, 1])
                if s_minus.button("-1 組", key=_editor_key(week_num, day_id, idx, "time_sets_minus"), use_container_width=True):
                    _bump_editor_number(sets_key, -1, 1, 30)
                if s_plus.button("+1 組", key=_editor_key(week_num, day_id, idx, "time_sets_plus"), use_container_width=True):
                    _bump_editor_number(sets_key, 1, 1, 30)
                s_value.number_input("做幾組", min_value=1, max_value=30, step=1, key=sets_key)
            else:
                r_minus, r_value, r_plus = st.columns([1, 2, 1])
                if r_minus.button("-1 下", key=_editor_key(week_num, day_id, idx, "reps_minus"), use_container_width=True):
                    _bump_editor_number(reps_key, -1, 1, 300)
                if r_plus.button("+1 下", key=_editor_key(week_num, day_id, idx, "reps_plus"), use_container_width=True):
                    _bump_editor_number(reps_key, 1, 1, 300)
                r_value.number_input("每組幾下", min_value=1, max_value=300, step=1, key=reps_key)

                s_minus, s_value, s_plus = st.columns([1, 2, 1])
                if s_minus.button("-1 組", key=_editor_key(week_num, day_id, idx, "sets_minus"), use_container_width=True):
                    _bump_editor_number(sets_key, -1, 1, 30)
                if s_plus.button("+1 組", key=_editor_key(week_num, day_id, idx, "sets_plus"), use_container_width=True):
                    _bump_editor_number(sets_key, 1, 1, 30)
                s_value.number_input("做幾組", min_value=1, max_value=30, step=1, key=sets_key)

            equipment_options = list(dict.fromkeys(EQUIPMENT_OPTIONS + (it.get("equipment") or [])))
            st.multiselect("器材", equipment_options, key=equipment_key)
            st.text_area("小提醒", key=note_key, height=80, placeholder="例：手臂打直夾緊，眼睛看球")

    with st.expander("➕ 新增一個動作", expanded=False):
        add_name = st.text_input("新動作名稱", key=f"add_name_w{week_num}_d{day['day']}", placeholder="例：收操伸展")
        add_mode = st.radio("新動作類型", ["計次", "計時"], key=f"add_mode_w{week_num}_d{day['day']}", horizontal=True)
        if add_mode == "計時":
            add_seconds = st.number_input("每組幾秒", min_value=10, max_value=1800, value=30, step=10, key=f"add_seconds_w{week_num}_d{day['day']}")
            add_sets = st.number_input("做幾組", min_value=1, max_value=30, value=3, step=1, key=f"add_time_sets_w{week_num}_d{day['day']}")
            add_reps = 10
        else:
            add_reps = st.number_input("每組幾下", min_value=1, max_value=300, value=10, step=1, key=f"add_reps_w{week_num}_d{day['day']}")
            add_sets = st.number_input("做幾組", min_value=1, max_value=30, value=2, step=1, key=f"add_sets_w{week_num}_d{day['day']}")
            add_seconds = 60
        add_equipment = st.multiselect("器材", EQUIPMENT_OPTIONS, key=f"add_equipment_w{week_num}_d{day['day']}")
        add_note = st.text_area("小提醒", key=f"add_note_w{week_num}_d{day['day']}", height=80)
        if st.button("加入這個動作", key=f"add_item_w{week_num}_d{day['day']}", use_container_width=True):
            if not add_name.strip():
                st.warning("請先輸入動作名稱。")
                return
            new_items = _read_panel_items(week_num, day["day"], len(items))
            if add_mode == "計時":
                new_item = {"name": add_name.strip(), "mode": "time", "seconds": int(add_seconds), "sets": int(add_sets)}
            else:
                new_item = {"name": add_name.strip(), "mode": "reps", "reps": int(add_reps), "sets": int(add_sets)}
            new_item["equipment"] = add_equipment
            new_item["note"] = add_note.strip()
            new_items.append(new_item)
            _save_day_items(student, curriculum, week_num, day, new_items)
            return

    if st.button("💾 儲存這天的修改", key=f"save_w{week_num}_d{day['day']}", type="primary", use_container_width=True):
        _save_day_items(student, curriculum, week_num, day, _read_panel_items(week_num, day["day"], len(items)))


def render_day_checkin(student: dict, week_number: int, day_num: int, logs: list[dict]) -> None:
    """每一天各自獨立的打卡按鈕（第 N 天做完就打勾，與其他天、與日曆都無關）。"""
    done_log = next(
        (l for l in logs if l.get("is_completed")
         and l.get("week_number") == week_number and l.get("day_number") == day_num),
        None,
    )
    if done_log:
        st.markdown("---")
        st.success(f"🌟 第 {day_num} 天已完成！得分 {done_log.get('score', 10)} 分，換下一天繼續加油！")
        return

    with st.expander(f"✅ 全部項目做完後，再打卡第 {day_num} 天", expanded=False):
        st.caption("先把上方播放器的每個項目都完成；全部做完後再按這裡領積分。")
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
                    st.markdown("**🎮 跟著做：按「開始」會帶你一項一項完成，計時項目會一組一組倒數，計次項目做完一組點一下**")
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


def render_checkin(student: dict, logs: list[dict], point_events: list[dict] | None = None):
    """今日完成總覽：列出今天打卡的天數與獎勵積分制度。"""
    point_events = point_events or []
    today = date.today()
    today_str = today.isoformat()
    st.markdown(f"📅 今天是 **{today.strftime('%Y 年 %m 月 %d 日')}**")

    today_logs = [
        l for l in logs
        if l.get("is_completed") and l.get("training_date") == today_str
    ]
    today_training_points = sum(l.get("score") or 0 for l in today_logs)
    today_events = [
        e for e in point_events
        if str(e.get("created_at") or "")[:10] == today_str
    ]
    today_bonus_points = sum(e.get("points") or 0 for e in today_events)
    training_points = training_score_total(logs)
    bonus_points = point_events_total(point_events)
    current_total = training_points + bonus_points

    with st.container(border=True):
        st.markdown("#### ⭐ 目前積分")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("總積分", current_total)
        c2.metric("訓練分", training_points)
        c3.metric("獎勵 / 消耗", bonus_points)
        c4.metric("今日獲得", today_training_points + today_bonus_points)
        st.caption("總積分可用來抽寵物扭蛋與寵物進化；訓練打卡、連續完成、比賽獎勵都會累積在這裡。")

    if not today_logs:
        st.info("今天還沒完成任何一天喔！到「📋 訓練菜單」挑一天，跟著做完就打卡吧 💪")
    else:
        st.success(f"🌟 今天完成了 **{len(today_logs)}** 天訓練，超棒的！")
        for l in sorted(today_logs, key=lambda x: (x.get("week_number") or 0, x.get("day_number") or 0)):
            wk = l.get("week_number", "?")
            dy = l.get("day_number")
            title = f"第 {wk} 週・第 {dy} 天" if dy else f"第 {wk} 週"
            st.markdown(f"#### ✅ {title}　⭐ {l.get('score', 10)} 分")
            st.caption("訓練完成紀錄。想請 AI 看動作時，請到「🎥 影片助理教練」。")
            st.markdown("---")

    if today_events:
        st.markdown("#### 🎉 今日獎勵積分")
        for e in today_events:
            pts = e.get("points") or 0
            sign = "+" if pts >= 0 else ""
            st.success(f"{sign}{pts} 分｜{e.get('reason', '')}")
            if e.get("note"):
                st.caption(e["note"])

    if point_events:
        with st.expander("📜 查看近期獎勵紀錄", expanded=False):
            for e in point_events[:8]:
                pts = e.get("points") or 0
                sign = "+" if pts >= 0 else ""
                st.markdown(f"**{(e.get('created_at') or '')[:10]}**　{sign}{pts} 分　{e.get('reason','')}")
                if e.get("note"):
                    st.caption(e["note"])

    with st.expander("🎁 獎勵積分制度", expanded=False):
        r1, r2, r3 = st.columns(3)
        r1.metric("完成 5 天", "+15")
        r2.metric("完成 3 週", "+20")
        r3.metric("比賽完畢", "+30")
        st.caption("前兩項由系統依同一套菜單完成進度自動發放；比賽完畢由教練在後台加分。抽扭蛋與寵物進化會扣除積分。")


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


def render_point_manager(student: dict, logs: list[dict], point_events: list[dict]) -> None:
    """教練後台：手動管理額外積分與查看積分紀錄。"""
    training_points = training_score_total(logs)
    bonus_points = point_events_total(point_events)
    st.markdown("#### ⭐ 積分管理")
    p1, p2, p3 = st.columns(3)
    p1.metric("訓練分", training_points)
    p2.metric("獎勵分", bonus_points)
    p3.metric("目前總分", training_points + bonus_points)

    st.markdown("##### 快速加分")
    q1, q2, q3 = st.columns(3)
    if q1.button("+30 比賽完畢", use_container_width=True):
        if add_point_event(student["id"], 30, "比賽完畢獎勵", "教練確認已完成比賽", event_type="competition"):
            st.success("已加 30 分")
            st.rerun()
    if q2.button("+10 教練鼓勵", use_container_width=True):
        if add_point_event(student["id"], 10, "教練鼓勵", "訓練態度良好", event_type="coach_bonus"):
            st.success("已加 10 分")
            st.rerun()
    if q3.button("+5 小幫手", use_container_width=True):
        if add_point_event(student["id"], 5, "小幫手獎勵", "主動協助收拾或幫助隊友", event_type="coach_bonus"):
            st.success("已加 5 分")
            st.rerun()

    with st.form(f"manual_points_{student['id']}", clear_on_submit=True):
        st.markdown("##### 自訂加分 / 扣分")
        c1, c2 = st.columns([1, 2])
        points = c1.number_input("分數", min_value=-100, max_value=100, value=10, step=1)
        reason = c2.selectbox(
            "理由",
            ["認真完成訓練", "寫日誌很用心", "影片動作有進步", "比賽完畢獎勵", "團隊精神", "教練特別獎勵", "其他"],
        )
        note = st.text_input("備註（選填）", placeholder="例：今天主動幫忙收球，也很認真完成棒式")
        if st.form_submit_button("儲存積分紀錄", type="primary", use_container_width=True):
            if points == 0:
                st.warning("分數不能是 0。")
            else:
                if add_point_event(student["id"], int(points), reason, note, event_type="manual"):
                    st.success("已儲存積分紀錄")
                    st.rerun()

    if point_events:
        st.markdown("##### 近期積分紀錄")
        for e in point_events[:10]:
            pts = e.get("points") or 0
            sign = "+" if pts >= 0 else ""
            st.markdown(f"**{(e.get('created_at') or '')[:10]}**　{sign}{pts} 分　{e.get('reason','')}")
            if e.get("note"):
                st.caption(e["note"])
    else:
        st.caption("目前還沒有額外積分紀錄。")


def render_avatar_card(student: dict) -> None:
    """角色卡：暱稱、人物模板、攜帶寵物，選擇時即時預覽。"""
    st.markdown("## 🎮 我的角色卡")
    st.caption("選擇人物或寵物時會先即時預覽，按儲存後才會寫入角色卡。")

    profile = get_avatar_profile(student)
    templates = get_avatar_templates(active_only=True)
    owned_pets = get_student_pets(student["id"])

    if not templates:
        st.warning("目前沒有可用人物模板。請先確認 `migrate_v8.sql` 已執行，且 avatar_templates 有 active=true 的角色。")
        return

    template_lookup = _seed_lookup(templates)
    pet_lookup = _seed_lookup(owned_pets)

    selected_template_id = profile.get("avatar_template_id") or "beginner"
    if selected_template_id not in template_lookup:
        selected_template_id = templates[0]["id"]

    selected_pet_id = profile.get("companion_pet_id") or (owned_pets[0]["id"] if owned_pets else None)
    if selected_pet_id not in pet_lookup:
        selected_pet_id = owned_pets[0]["id"] if owned_pets else None

    card_col, form_col = st.columns([1, 1])
    with form_col:
        nickname_key = f"avatar_nickname_{student['id']}"
        template_key = f"avatar_template_select_{student['id']}"
        pet_key = f"avatar_pet_select_{student['id']}"

        if nickname_key not in st.session_state:
            st.session_state[nickname_key] = profile.get("nickname") or student.get("name") or ""
        if template_key not in st.session_state or st.session_state[template_key] not in template_lookup:
            st.session_state[template_key] = selected_template_id
        if owned_pets and (pet_key not in st.session_state or st.session_state[pet_key] not in pet_lookup):
            st.session_state[pet_key] = selected_pet_id

        new_nickname = st.text_input("角色暱稱", max_chars=20, key=nickname_key)
        template_ids = [t["id"] for t in templates]
        template_id = st.selectbox(
            "選擇人物",
            template_ids,
            format_func=lambda tid: template_lookup[tid].get("display_name", tid),
            key=template_key,
        )

        pet_id = None
        pet_ids = [p["id"] for p in owned_pets]
        if pet_ids:
            pet_id = st.selectbox(
                "攜帶寵物",
                pet_ids,
                format_func=lambda pid: (
                    f"{pet_lookup[pid].get('display_name', pid)}"
                    f"（{pet_lookup[pid].get('rarity', '')}｜持有 {pet_lookup[pid].get('quantity', 1)}）"
                ),
                key=pet_key,
            )
        else:
            st.info("還沒有寵物。請先到寵物扭蛋抽一隻，或確認 `student_pets` 表已建立。")

        if st.button("💾 儲存角色卡", type="primary", use_container_width=True):
            clean_nickname = new_nickname.strip() or student.get("name") or "小選手"
            if save_avatar_profile(student["id"], clean_nickname, template_id, pet_id):
                st.success("角色卡已更新！")
                st.rerun()
            else:
                st.error("角色卡儲存失敗，請先確認 Supabase 已執行 `migrate_v8.sql`。")

    selected_template = template_lookup.get(st.session_state.get(f"avatar_template_select_{student['id']}")) or template_lookup[selected_template_id]
    selected_pet = pet_lookup.get(st.session_state.get(f"avatar_pet_select_{student['id']}")) if owned_pets else None
    nickname = st.session_state.get(f"avatar_nickname_{student['id']}", profile.get("nickname") or student.get("name") or "")

    with card_col:
        with st.container(border=True):
            img_col, info_col = st.columns([1, 1])
            with img_col:
                avatar_file = _asset_file(selected_template.get("asset_path"))
                if avatar_file:
                    st.image(avatar_file, width=210)
                else:
                    st.info("人物素材尚未準備")
            with info_col:
                st.markdown(f"### {nickname}")
                st.markdown(f"**人物：** {selected_template.get('display_name', selected_template_id)}")
                st.caption(selected_template.get("role_name", ""))
                if selected_template.get("catchphrase"):
                    st.info(f"「{selected_template['catchphrase']}」")

                if selected_pet:
                    st.markdown("#### 攜帶寵物")
                    render_pet_card_image(selected_pet, width=155)
                    st.markdown(
                        f"**{selected_pet.get('display_name', selected_pet['id'])}**"
                        f"　{selected_pet.get('rarity', '')}"
                    )
                    st.caption(selected_pet.get("species_note", ""))
                else:
                    st.caption("尚未擁有可攜帶的寵物。")


def render_pet_inventory_and_evolution(student: dict, logs: list[dict], point_events: list[dict]) -> None:
    """寵物背包與進化，放在角色卡同一頁下方。"""
    st.markdown("---")
    st.markdown("## 🐣 已收集寵物")

    owned_pets = get_student_pets(student["id"])
    pet_catalog = get_pet_catalog(active_only=True)
    score = total_score(logs, point_events)

    total_pets = sum(p.get("quantity") or 0 for p in owned_pets)
    m1, m2, m3 = st.columns(3)
    m1.metric("持有寵物", total_pets)
    m2.metric("可進化次數", sum(available_evolution_count(owned_pets, r) for r in EVOLUTION_RULES))
    m3.metric("目前積分", score)

    if not owned_pets:
        st.info("目前還沒有寵物。去寵物扭蛋抽第一隻吧！")
        return

    bag_tab, evo_tab = st.tabs(["已收集圖鑑", "寵物進化"])
    with bag_tab:
        st.caption("只顯示已收集的寵物，未發現的寵物先保留驚喜感。")
        cols = st.columns(4)
        for idx, pet in enumerate(owned_pets):
            with cols[idx % 4]:
                with st.container(border=True):
                    render_pet_card_image(pet, width=210)
                    st.markdown(f"**{pet.get('display_name', pet['id'])}**")
                    st.caption(f"{pet.get('rarity', '')}｜持有 {pet.get('quantity', 1)}")
                    if pet.get("species_note"):
                        st.caption(pet["species_note"])

    with evo_tab:
        st.caption("消耗任意 3 隻同等級寵物，隨機進化成下一階。")
        render_pet_evolution_rules(student, owned_pets, pet_catalog, logs, score)


def render_pet_evolution_rules(
    student: dict,
    owned_pets: list[dict],
    pet_catalog: list[dict],
    logs: list[dict],
    score: int,
) -> None:
    evo_cols = st.columns(3)
    for idx, (from_rarity, rule) in enumerate(EVOLUTION_RULES.items()):
        can_evolve = available_evolution_count(owned_pets, from_rarity)
        cost = rule["cost"]
        disabled = can_evolve <= 0 or score < cost
        with evo_cols[idx]:
            with st.container(border=True):
                icon_key = "combine" if from_rarity == "N" else "training" if from_rarity == "R" else "final_star"
                icon_col, title_col = st.columns([1, 4])
                with icon_col:
                    render_icon_asset(icon_key, width=42)
                with title_col:
                    st.markdown(f"#### {rule['label']}")
                    st.caption(f"進化成隨機 {rule['to']} 寵物")
                render_icon_asset("upgrade_arrow", width=38)
                st.caption(f"消耗：任意 3 隻 {from_rarity}" + (f" + {cost} 積分" if cost else ""))
                st.caption(f"目前可進化：{can_evolve} 次")
                if score < cost:
                    st.warning(f"積分不足，還差 {cost - score} 分。")
                elif can_evolve <= 0:
                    st.info(f"再收集一些 {from_rarity} 寵物就能進化。")
                if st.button(
                    "進化一次",
                    key=f"evolve_{student['id']}_{from_rarity}",
                    disabled=disabled,
                    use_container_width=True,
                ):
                    result = draw_pet_by_rarity(pet_catalog, rule["to"])
                    if not result:
                        st.error("找不到下一階寵物資料。")
                        return
                    if cost > 0 and total_score(logs, get_point_events(student["id"])) < cost:
                        st.error("積分不足，無法進化。")
                        return
                    if not consume_three_pets_by_rarity(student["id"], owned_pets, from_rarity):
                        st.error("寵物數量不足，無法進化。")
                        return
                    if not grant_student_pet(student["id"], result["id"], source="evolution"):
                        st.error("進化結果寫入失敗。")
                        return
                    if cost > 0:
                        add_point_event(
                            student["id"],
                            -cost,
                            f"{rule['label']} 寵物進化",
                            f"消耗 3 隻 {from_rarity} 寵物，進化為 {result.get('display_name', result['id'])}",
                            event_type="pet_evolution",
                            created_by="system",
                        )
                    st.success(f"進化成功！獲得 {result.get('display_name', result['id'])}")
                    st.balloons()
                    st.rerun()


def render_pet_gacha_machine(student: dict, logs: list[dict], point_events: list[dict]) -> None:
    """寵物扭蛋機：花積分抽寵物，結果寫入背包。"""
    st.markdown("## 🥚 寵物扭蛋機")
    st.caption("花積分抽寵物，重複抽到會增加持有數量。")

    pet_catalog = get_pet_catalog(active_only=True)
    if not pet_catalog:
        st.warning("目前沒有可抽的寵物資料，請確認 `pet_catalog` seed 已建立。")
        return

    score = total_score(logs, point_events)
    machine_col, result_col = st.columns([1, 1])
    with machine_col:
        machine_file = _asset_file(GACHA_MACHINE_ASSETS["preview"])
        if machine_file:
            st.image(machine_file, width=320)
        else:
            st.info("扭蛋機素材尚未找到。")

        st.metric("目前積分", score)
        st.caption(f"普通蛋：{GACHA_COST} 分 / 次")
        st.caption("目前機率：N 70%｜R 22%｜SR 7%｜SSR 1%")
        if score < GACHA_COST:
            st.warning(f"積分不足，還差 {GACHA_COST - score} 分。")
        if st.button("🎰 花 20 分轉一次", type="primary", use_container_width=True, disabled=score < GACHA_COST):
            latest_events = get_point_events(student["id"])
            latest_score = total_score(get_training_logs(student["id"]), latest_events)
            if latest_score < GACHA_COST:
                st.error("積分不足，無法抽扭蛋。")
                return
            result = draw_gacha_pet(pet_catalog)
            if not result:
                st.error("沒有可抽取的寵物。")
                return
            if grant_student_pet(student["id"], result["id"], source="gacha"):
                add_point_event(
                    student["id"],
                    -GACHA_COST,
                    "寵物扭蛋",
                    f"抽到 {result.get('display_name', result['id'])}",
                    event_type="pet_gacha",
                    created_by="system",
                )
                st.session_state[f"last_gacha_result_{student['id']}"] = result
                st.success(f"抽到 {result.get('display_name', result['id'])}！")
                st.balloons()
                st.rerun()
            else:
                st.error("抽獎結果無法寫入，請確認 `migrate_v8.sql` 已執行。")

    with result_col:
        result = st.session_state.get(f"last_gacha_result_{student['id']}")
        if result:
            with st.container(border=True):
                rarity = result.get("rarity", "N")
                if rarity == "SSR":
                    flash_file = _asset_file(GACHA_MACHINE_ASSETS["rarity_flash_ssr"])
                    if flash_file:
                        st.image(flash_file, width=180)
                render_pet_card_image(result, width=260)
                st.markdown(
                    f"<div style='text-align:center;'><h3>{result.get('display_name', result['id'])}</h3></div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div style='text-align:center;'>稀有度：<b>{rarity}</b></div>",
                    unsafe_allow_html=True,
                )
                st.caption(result.get("species_note", ""))
        else:
            st.info("按下轉一次後，抽到的寵物會出現在這裡。")


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


def render_progress(student: dict, logs: list[dict], point_events: list[dict] | None = None):
    """學員進度看板"""
    point_events = point_events or []
    stats = calculate_stats(student, logs, point_events)
    analyses = get_video_analyses(student["id"])

    # 進度條
    st.markdown("#### 🎯 整體訓練完成度")
    st.progress(stats["progress_pct"] / 100)
    st.caption(
        f"已完成 {stats['completed_days']} / {stats['total_training_days']} 個訓練日"
        f"（{stats['progress_pct']:.1f}%）"
    )

    # 三格統計
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📅 打卡天數", stats["completed_days"])
    c2.metric("🏐 訓練分", stats["training_score"])
    c3.metric("🎁 獎勵分", stats["bonus_score"])
    c4.metric("⭐ 總積分", stats["total_score"])
    st.caption(f"🎥 AI 分析：{len(analyses)} 次")

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
            score_text = f"⭐ {log['score']} 分" if log.get("score") else ""
            day_text = f"第 {log['day_number']} 天" if log.get("day_number") else ""
            st.markdown(
                f"✅ **{log['training_date']}**　第 {log['week_number']} 週 {day_text}　{score_text}"
            )
    else:
        st.info("還沒有訓練紀錄，快去打卡吧！💪")

    if analyses:
        st.markdown("#### 🎥 近期影片助理教練紀錄")
        for a in analyses[:5]:
            created = (a.get("created_at") or "")[:10]
            skill = a.get("target_skill") or "綜合訓練"
            score = a.get("score")
            st.markdown(f"🎥 **{created}**　{skill}　⭐ {score if score is not None else '-'} 分")


def render_video_coach(student: dict):
    """獨立影片助理教練：不綁訓練菜單、不影響打卡進度。"""
    st.markdown("## 🎥 影片助理教練")
    st.markdown(
        "上傳一段 **10 秒以內**的練習短片，AI 教練會專門分析動作並給予回饋。"
    )
    st.caption("這是獨立功能，不會自動完成任何訓練日，也不會把影片掛到訓練菜單。")

    analyses = get_video_analyses(student["id"])
    if analyses:
        with st.expander("📚 查看最近的影片分析紀錄", expanded=False):
            for a in analyses[:5]:
                feedback = parse_ai_feedback(a.get("ai_feedback"))
                title = (
                    f"{(a.get('created_at') or '')[:10]}｜"
                    f"{a.get('target_skill') or '綜合訓練'}｜"
                    f"⭐ {a.get('score') if a.get('score') is not None else '-'} 分"
                )
                with st.container(border=True):
                    st.markdown(f"**{title}**")
                    if feedback:
                        greeting = feedback.get("greeting")
                        if greeting:
                            st.caption(greeting)
                    if a.get("video_url"):
                        st.link_button("開啟影片備份", a["video_url"])

    uploaded = st.file_uploader(
        "選擇影片（mp4 / mov，建議 10 秒以內，最大 50 MB）",
        type=["mp4", "mov", "avi"],
        key=f"video_coach_upload_{student['id']}",
    )

    if not uploaded:
        return

    st.video(uploaded)

    suggested_skills = parse_skills(student.get("target_skill"))
    skill_options = TARGET_SKILLS
    default_skill = suggested_skills[0] if suggested_skills else "綜合訓練"
    default_idx = skill_options.index(default_skill) if default_skill in skill_options else len(skill_options) - 1
    skill = st.selectbox(
        "🎯 這支影片想分析哪一項動作？",
        skill_options,
        index=default_idx,
        help="影片助理教練是獨立功能，可以分析目前菜單以外的技巧。",
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

    # Step 3:儲存到獨立 video_analyses，不影響訓練打卡與訓練分數
    try:
        save_video_analysis(student["id"], skill, public_url, feedback)
    except Exception as e:
        print(f"[ERROR] Saving video analysis failed: {e}")  # 細節只留在伺服器 log
        st.warning("⚠️ 分析完成但未儲存紀錄；請確認已在 Supabase 執行 `migrate_v6.sql`。")

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

    # ── 斷線還原：手機鎖屏/切App/網路切換導致 session 清空時，從網址參數還原學生身分 ──
    # （只還原學生，不還原教練：教練屬敏感權限，重連時請重新輸入密碼）
    if st.session_state.role is None and st.query_params.get("role") == "student":
        nm = st.query_params.get("name")
        if nm:
            stu = get_student_by_name(nm)
            if stu:
                st.session_state.role = "student"
                _set_current_student(stu)

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

        # 功能 D：賽事行事曆（全隊共用，教練隨時可在側欄維護）
        if is_admin:
            render_competition_manager()

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
                # 一鍵切換成「這位學生的畫面」（把裝置交給小朋友，或檢視他看到的樣子）
                if st.button("👦 切換成這位學生的畫面", use_container_width=True, type="primary"):
                    st.session_state.role = "student"
                    st.session_state.editing_profile = False
                    st.session_state.confirm_delete = False
                    st.session_state.adding_student = False
                    # 一併寫入網址身分，交給小朋友後斷線也能自動還原
                    st.query_params["role"] = "student"
                    st.query_params["name"] = s["name"]
                    st.rerun()
                st.caption("切過去後，左下角「登出」再用教練密碼即可回後台。")
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

        # 學生端：唯讀顯示近期比賽（賽事由教練維護）
        if not is_admin:
            render_upcoming_competitions()

        st.markdown("---")
        if st.button("🚪 登出", use_container_width=True):
            st.session_state.role = None
            st.session_state.current_student = None
            st.session_state.curriculum = None
            st.session_state.editing_profile = False
            st.session_state.confirm_delete = False
            st.query_params.clear()  # 清掉網址身分，登出後不會被自動還原
            st.rerun()

    # ── 主內容區 ────────────────────────────────────────────
    # 教練後台：新增學員模式（按了「➕ 新增學員」，或名冊還是空的）
    if is_admin and (st.session_state.adding_student or not all_students):
        if not all_students:
            st.markdown("""
            # 🏐 歡迎使用排球訓練小幫手！（教練後台）

            這是一個專為小朋友設計的 AI 排球訓練夥伴。教練在這裡**建立名冊**，
            小朋友與家長登入後**自己填資料、生成菜單**，也可以用獨立的影片助理教練看動作。

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

    # 2) 資料已完善但還沒有菜單 → 可先生成菜單，也可直接使用獨立影片助理教練
    if curriculum is None:
        logs = get_training_logs(student["id"])
        point_events = get_point_events(student["id"])
        tab_generate, tab_avatar, tab_gacha, tab_video = st.tabs(["🗓️ 生成訓練菜單", "🎮 角色卡", "🥚 寵物扭蛋", "🎥 影片助理教練"])
        with tab_generate:
            render_generate_menu(student)
        with tab_avatar:
            render_avatar_card(student)
            render_pet_inventory_and_evolution(student, logs, point_events)
        with tab_gacha:
            render_pet_gacha_machine(student, logs, point_events)
        with tab_video:
            render_video_coach(student)
        return

    logs = get_training_logs(student["id"])
    ensure_auto_point_rewards(student, logs)
    point_events = get_point_events(student["id"])
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
        f"（做完 {completed_sessions(logs)} 次）　｜　累積 {total_score(logs, point_events)} 分"
    )

    # 兩週身高體重提醒（滿 14 天才出現）
    render_body_metric_reminder(student)

    # 教練工具：菜單管理（編輯/刪除學員已移到左側欄）
    if is_admin:
        with st.expander("🛠️ 教練工具：菜單管理"):
            st.markdown("#### 清除目前菜單")
            st.caption("只清除這位小朋友目前這份菜單與菜單設定，不會刪除打卡、日誌、影片分析或身高體重紀錄。")
            if logs:
                st.warning(
                    f"這位小朋友目前已有 {completed_sessions(logs)} 天打卡紀錄。"
                    "如果已經正式開始訓練，清菜單後重新生成仍會保留這些進度紀錄。"
                )
            confirm_clear = st.checkbox(
                "我確認要清除目前菜單",
                key=f"confirm_clear_curriculum_{student['id']}",
            )
            if st.button(
                "🧹 清除目前菜單",
                key=f"clear_curriculum_{student['id']}",
                use_container_width=True,
                disabled=not confirm_clear,
            ):
                clear_curriculum(student["id"])
                st.session_state.current_student = get_student_by_name(student["name"])
                st.session_state.curriculum = None
                st.success("已清除目前菜單，可以重新生成。")
                st.rerun()

            st.markdown("---")
            st.markdown("#### 重新生成菜單")
            render_generate_menu(student)

        with st.expander("⭐ 教練工具：積分管理"):
            render_point_manager(student, logs, point_events)

    # 功能頁籤：影片助理教練為獨立功能，不綁訓練菜單或打卡
    tab_labels = ["📋 訓練菜單", "✅ 今日完成", "🎮 角色卡", "🥚 寵物扭蛋", "🎥 影片助理教練", "📊 我的進度", "📔 訓練日誌"]
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        render_curriculum(curriculum, current_week, student, logs)
    with tabs[1]:
        render_checkin(student, logs, point_events)
    with tabs[2]:
        render_avatar_card(student)
        render_pet_inventory_and_evolution(student, logs, point_events)
    with tabs[3]:
        render_pet_gacha_machine(student, logs, point_events)
    with tabs[4]:
        render_video_coach(student)
    with tabs[5]:
        render_progress(student, logs, point_events)
    with tabs[6]:
        render_journal_tab(student, current_week, logs, plan_key, readonly=is_admin)


if __name__ == "__main__":
    main()
