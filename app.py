import html
import json
import random
import sqlite3
import hashlib
import secrets
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    HAS_REPORTLAB = True
except ModuleNotFoundError:
    HAS_REPORTLAB = False

try:
    from data_seed import SEED_QUESTIONS
except ModuleNotFoundError:
    # data_seed.py が同じフォルダに無い環境でも app.py 単体で起動できるようにします。
    SEED_QUESTIONS = []


APP_DIR = Path(__file__).resolve().parent

# 通常は eiken_vocab.db を使います。
# ただし、英検1級を追加したDB名が eiken_vocab_with_passitan.db の場合は、
# そのDBを優先して読み込みます。
DEFAULT_DB_PATH = APP_DIR / "eiken_vocab.db"
PASSITAN_DB_PATH = APP_DIR / "eiken_vocab_with_passitan.db"
DB_PATH = PASSITAN_DB_PATH if PASSITAN_DB_PATH.exists() else DEFAULT_DB_PATH
# special-lesson 用DB。現在のファイル名 special_lesson.db を優先し、
# 以前の english_exercises_answers_jp.db も互換のため読み込みます。
SPECIAL_LESSON_DB_CANDIDATES = [
    APP_DIR / "special_lesson.db",
    APP_DIR / "english_exercises_answers_jp.db",
    Path("/mnt/data/special_lesson.db"),
    Path("/mnt/data/english_exercises_answers_jp.db"),
]
SPECIAL_LESSON_DB_PATH = next((p for p in SPECIAL_LESSON_DB_CANDIDATES if p.exists()), SPECIAL_LESSON_DB_CANDIDATES[0])
EXPORT_DIR = APP_DIR / "exports"

st.set_page_config(
    page_title="Learning Engish Dashbord",
    page_icon="📘",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', 'Noto Sans JP', sans-serif; }
.stApp { background: linear-gradient(135deg, #08111f 0%, #101827 42%, #182235 100%); color: #eef4ff; }
[data-testid="stSidebar"] { background: rgba(8, 17, 31, 0.96); border-right: 1px solid rgba(255,255,255,0.08); }
[data-testid="stMetricValue"] { color: #ffffff; }
.hero {
  padding: 30px 34px; border-radius: 28px;
  background: radial-gradient(circle at top left, rgba(79, 172, 254, .33), transparent 36%),
              linear-gradient(135deg, rgba(27, 38, 64, .95), rgba(11, 18, 32, .95));
  border: 1px solid rgba(255,255,255,.10);
  box-shadow: 0 24px 70px rgba(0,0,0,.35);
  margin-bottom: 22px;
}
.hero h1 { font-size: 42px; line-height: 1.05; margin: 0 0 10px 0; color: #fff; letter-spacing: -0.04em; }
.hero p { color: #b9c6da; font-size: 16px; margin: 0; }
.pill { display:inline-block; padding: 7px 12px; border-radius: 999px; background: rgba(79,172,254,.16); border:1px solid rgba(79,172,254,.25); color:#cfe8ff; font-size: 13px; margin-right: 8px; margin-bottom: 10px; }
.card {
  padding: 22px; border-radius: 24px;
  background: rgba(255,255,255,.055);
  border: 1px solid rgba(255,255,255,.11);
  box-shadow: 0 18px 45px rgba(0,0,0,.22);
  margin-bottom: 16px;
}
.qnum { color:#78c7ff; font-weight:800; letter-spacing:.02em; }
.question { color:#ffffff; font-size: 22px; line-height: 1.85; font-weight: 700; }
.translation { color:#d3dceb; line-height: 1.75; background: rgba(255,255,255,.055); padding: 14px 16px; border-radius: 16px; margin: 12px 0; }
.answer { color:#b7ffcf; font-weight:800; }
.small { color:#aebbd0; font-size: 14px; line-height: 1.65; }
.badge { padding: 4px 9px; border-radius: 999px; background:rgba(255,255,255,.10); color:#dce8fb; font-size:12px; margin-right:6px; }
hr { border-color: rgba(255,255,255,.10); }
.stButton>button { border-radius: 14px; border: 1px solid rgba(255,255,255,.14); background: linear-gradient(135deg, #3378ff, #7d4dff); color: white; font-weight: 700; }
.stDownloadButton>button { border-radius: 14px; }
.vocab-box { padding: 14px 16px; border-radius: 18px; background: rgba(183,255,207,.08); border: 1px solid rgba(183,255,207,.16); margin: 10px 0; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def today_iso():
    return date.today().isoformat()


def normalize_email(email):
    return str(email or "").strip().lower()


def make_password_hash(password, salt=None):
    """パスワードはDBへ平文保存せず、salt付きSHA-256で保存します。"""
    salt = salt or secrets.token_hex(16)
    password = str(password or "")
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return digest, salt


def create_user(email, password):
    email = normalize_email(email)
    password = str(password or "")

    if not email or "@" not in email:
        return False, "正しいメールアドレスを入力してください。"
    if len(password) < 6:
        return False, "パスワードは6文字以上にしてください。"

    password_hash, salt = make_password_hash(password)
    con = connect()
    try:
        con.execute(
            "INSERT INTO users (email, password_hash, salt) VALUES (?, ?, ?)",
            (email, password_hash, salt),
        )
        con.commit()
        return True, "登録しました。ログインしてください。"
    except sqlite3.IntegrityError:
        return False, "このメールアドレスはすでに登録されています。ログインしてください。"
    finally:
        con.close()


def authenticate_user(email, password):
    email = normalize_email(email)
    con = connect()
    try:
        cur = con.cursor()
        cur.execute("SELECT id, email, password_hash, salt FROM users WHERE email=?", (email,))
        row = cur.fetchone()
        if not row:
            return False, "メールアドレスまたはパスワードが違います。"

        user_id, user_email, stored_hash, salt = row
        password_hash, _ = make_password_hash(password, salt=salt)
        if not secrets.compare_digest(password_hash, stored_hash):
            return False, "メールアドレスまたはパスワードが違います。"

        con.execute("UPDATE users SET last_login_at=CURRENT_TIMESTAMP WHERE id=?", (int(user_id),))
        con.commit()
        st.session_state["auth_user_id"] = int(user_id)
        st.session_state["auth_email"] = user_email
        return True, "ログインしました。"
    finally:
        con.close()


def logout_user():
    for key in ["auth_user_id", "auth_email"]:
        st.session_state.pop(key, None)


def current_user_id():
    """現在ログイン中のユーザーIDを返します。"""
    try:
        return int(st.session_state.get("auth_user_id") or 0)
    except Exception:
        return 0


def load_user_progress(area, default=None):
    """ユーザーごとの前回学習位置を読み込みます。"""
    user_id = current_user_id()
    if not user_id:
        return default if default is not None else {}
    con = connect()
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT payload_json FROM user_progress WHERE user_id=? AND area=?",
            (user_id, str(area)),
        )
        row = cur.fetchone()
        if not row:
            return default if default is not None else {}
        data = json.loads(row[0] or "{}")
        return data if isinstance(data, dict) else (default if default is not None else {})
    except Exception:
        return default if default is not None else {}
    finally:
        con.close()


def save_user_progress(area, payload):
    """ユーザーごとの前回学習位置を保存します。"""
    user_id = current_user_id()
    if not user_id:
        return
    try:
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        con = connect()
        con.execute(
            """
            INSERT INTO user_progress (user_id, area, payload_json)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, area) DO UPDATE SET
                payload_json=excluded.payload_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, str(area), payload_json),
        )
        con.commit()
    except Exception:
        pass
    finally:
        try:
            con.close()
        except Exception:
            pass


def set_session_default_from_progress(key, value, valid_values=None):
    """Streamlit widget作成前に、保存済みの値を初期値として復元します。"""
    if key in st.session_state or value is None:
        return
    if valid_values is not None and value not in valid_values:
        return
    st.session_state[key] = value

def percent_value(completed, total):
    """進捗率を0〜100で返します。"""
    try:
        total = int(total or 0)
        completed = int(completed or 0)
        if total <= 0:
            return 0.0
        return max(0.0, min(100.0, completed / total * 100))
    except Exception:
        return 0.0


def save_study_progress(area, item_key, title, total_count=0, completed_count=0, unit="", section_no="", score_rate=None, status="学習中", payload=None):
    """ユーザー別に、どこまで学習したかの最新状態を保存します。"""
    user_id = current_user_id()
    if not user_id:
        return
    try:
        total_count = int(total_count or 0)
        completed_count = int(completed_count or 0)
        if score_rate is None:
            score_rate = percent_value(completed_count, total_count)
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        con = connect()
        con.execute(
            """
            INSERT INTO user_study_progress
            (user_id, area, item_key, title, unit, section_no, total_count, completed_count, score_rate, status, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, area, item_key) DO UPDATE SET
                title=excluded.title,
                unit=excluded.unit,
                section_no=excluded.section_no,
                total_count=excluded.total_count,
                completed_count=excluded.completed_count,
                score_rate=excluded.score_rate,
                status=excluded.status,
                payload_json=excluded.payload_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, str(area), str(item_key), str(title), str(unit), str(section_no), total_count, completed_count, float(score_rate or 0), str(status), payload_json),
        )
        con.commit()
    except Exception:
        pass
    finally:
        try:
            con.close()
        except Exception:
            pass


def add_study_event(area, event_type, title, total_count=0, completed_count=0, score_rate=None, payload=None):
    """テスト完了・Confirmなどの学習履歴を時系列で保存します。"""
    user_id = current_user_id()
    if not user_id:
        return
    try:
        total_count = int(total_count or 0)
        completed_count = int(completed_count or 0)
        if score_rate is None:
            score_rate = percent_value(completed_count, total_count)
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        con = connect()
        con.execute(
            """
            INSERT INTO user_study_events
            (user_id, area, event_type, title, total_count, completed_count, score_rate, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, str(area), str(event_type), str(title), total_count, completed_count, float(score_rate or 0), payload_json),
        )
        con.commit()
    except Exception:
        pass
    finally:
        try:
            con.close()
        except Exception:
            pass


def load_study_progress():
    user_id = current_user_id()
    if not user_id:
        return pd.DataFrame()
    con = connect()
    try:
        return pd.read_sql_query(
            """
            SELECT area, item_key, title, unit, section_no, total_count, completed_count, score_rate, status, updated_at
            FROM user_study_progress
            WHERE user_id=?
            ORDER BY updated_at DESC
            """,
            con,
            params=(user_id,),
        )
    finally:
        con.close()


def load_study_events(limit=200):
    user_id = current_user_id()
    if not user_id:
        return pd.DataFrame()
    con = connect()
    try:
        return pd.read_sql_query(
            """
            SELECT area, event_type, title, total_count, completed_count, score_rate, created_at
            FROM user_study_events
            WHERE user_id=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            con,
            params=(user_id, int(limit)),
        )
    finally:
        con.close()

def mask_email_for_ranking(email):
    """ランキング表示用にメールアドレスを短く表示します。"""
    email = str(email or "").strip()
    if not email or "@" not in email:
        return email or "unknown"
    name, domain = email.split("@", 1)
    if len(name) <= 2:
        shown = name[:1] + "*"
    else:
        shown = name[:2] + "***"
    return f"{shown}@{domain}"


def load_all_user_progress_ranking():
    """Overview用：全ユーザーの学習進捗ランキングを取得します。"""
    con = connect()
    try:
        progress = pd.read_sql_query(
            """
            SELECT
                u.id AS user_id,
                u.email AS email,
                COUNT(p.id) AS records,
                COALESCE(SUM(p.total_count), 0) AS total_count,
                COALESCE(SUM(p.completed_count), 0) AS completed_count,
                COALESCE(AVG(p.score_rate), 0) AS avg_progress_rate,
                MAX(p.updated_at) AS last_study_at
            FROM users u
            LEFT JOIN user_study_progress p ON p.user_id = u.id
            GROUP BY u.id, u.email
            """,
            con,
        )
        events = pd.read_sql_query(
            """
            SELECT
                user_id,
                COUNT(id) AS test_count,
                COALESCE(AVG(score_rate), 0) AS avg_test_rate,
                COALESCE(MAX(score_rate), 0) AS best_test_rate,
                MAX(created_at) AS last_test_at
            FROM user_study_events
            WHERE area IN ('passitan_test', 'special_lesson')
            GROUP BY user_id
            """,
            con,
        )
    except Exception:
        return pd.DataFrame()
    finally:
        con.close()

    if progress.empty:
        return progress

    merged = progress.merge(events, on="user_id", how="left")
    for col in ["records", "total_count", "completed_count", "test_count"]:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0).astype(int)
    for col in ["avg_progress_rate", "avg_test_rate", "best_test_rate"]:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0.0)

    merged["overall_rate"] = merged.apply(lambda r: percent_value(r["completed_count"], r["total_count"]), axis=1)
    # 進捗率だけだと少数の学習でも上位になるため、完了数も少し加点します。
    merged["rank_score"] = merged["overall_rate"] + (merged["completed_count"].clip(upper=500) / 500 * 10) + (merged["avg_test_rate"].fillna(0) * 0.05)
    merged = merged.sort_values(["rank_score", "completed_count", "records"], ascending=[False, False, False]).reset_index(drop=True)
    merged["rank"] = merged.index + 1
    merged["display_user"] = merged["email"].apply(mask_email_for_ranking)
    return merged


def load_all_user_area_progress(area):
    """Overview用：特定分野の全ユーザー進捗を取得します。"""
    con = connect()
    try:
        df = pd.read_sql_query(
            """
            SELECT
                u.id AS user_id,
                u.email AS email,
                COUNT(p.id) AS records,
                COALESCE(SUM(p.total_count), 0) AS total_count,
                COALESCE(SUM(p.completed_count), 0) AS completed_count,
                COALESCE(AVG(p.score_rate), 0) AS avg_rate,
                MAX(p.updated_at) AS last_study_at
            FROM users u
            JOIN user_study_progress p ON p.user_id = u.id
            WHERE p.area=?
            GROUP BY u.id, u.email
            """,
            con,
            params=(str(area),),
        )
    except Exception:
        return pd.DataFrame()
    finally:
        con.close()

    if df.empty:
        return df
    for col in ["records", "total_count", "completed_count"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["progress_rate"] = df.apply(lambda r: percent_value(r["completed_count"], r["total_count"]), axis=1)
    df["display_user"] = df["email"].apply(mask_email_for_ranking)
    df = df.sort_values(["progress_rate", "completed_count"], ascending=[False, False]).reset_index(drop=True)
    df["rank"] = df.index + 1
    return df


def load_recent_all_user_study_events(limit=20):
    """Overview用：全ユーザーの最近のテスト履歴を取得します。"""
    con = connect()
    try:
        df = pd.read_sql_query(
            """
            SELECT
                u.email AS email,
                e.area,
                e.event_type,
                e.title,
                e.total_count,
                e.completed_count,
                e.score_rate,
                e.created_at
            FROM user_study_events e
            JOIN users u ON u.id = e.user_id
            ORDER BY e.created_at DESC
            LIMIT ?
            """,
            con,
            params=(int(limit),),
        )
    except Exception:
        return pd.DataFrame()
    finally:
        con.close()
    if not df.empty:
        df["display_user"] = df["email"].apply(mask_email_for_ranking)
    return df


def render_all_user_ranking_overview():
    """Overviewに、全ユーザーの進捗・ランキングを表示します。"""
    ranking_df = load_all_user_progress_ranking()

    st.subheader("🏆 全ユーザーの勉強進捗・ランキング")
    if ranking_df.empty:
        st.info("まだ全ユーザーの学習記録がありません。パス単・パス単テスト・special-lessonを使うと自動で記録されます。")
        return

    active_df = ranking_df[ranking_df["records"] > 0].copy()
    active_users = len(active_df)
    total_users = len(ranking_df)
    total_completed = int(ranking_df["completed_count"].sum())
    avg_rate = float(active_df["overall_rate"].mean()) if active_users else 0.0

    my_rank_text = "-"
    uid = current_user_id()
    if uid and uid in ranking_df["user_id"].tolist():
        my_row = ranking_df[ranking_df["user_id"] == uid].iloc[0]
        my_rank_text = f"{int(my_row['rank'])}位 / {total_users}人"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("登録ユーザー", total_users)
    c2.metric("学習記録あり", active_users)
    c3.metric("全員の完了/正解数", total_completed)
    c4.metric("自分の順位", my_rank_text)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### 総合ランキング")
    show = ranking_df.copy()
    show["overall_rate"] = show["overall_rate"].round(1)
    show["avg_test_rate"] = show["avg_test_rate"].round(1)
    show["best_test_rate"] = show["best_test_rate"].round(1)
    show["last_study_at"] = show["last_study_at"].fillna("").astype(str)
    ranking_view = show.rename(columns={
        "rank": "順位",
        "display_user": "ユーザー",
        "overall_rate": "全体進捗%",
        "records": "記録項目",
        "completed_count": "完了/正解",
        "total_count": "合計",
        "test_count": "テスト回数",
        "avg_test_rate": "平均テスト%",
        "best_test_rate": "最高テスト%",
        "last_study_at": "最終学習",
    })
    cols = ["順位", "ユーザー", "全体進捗%", "記録項目", "完了/正解", "合計", "テスト回数", "平均テスト%", "最高テスト%", "最終学習"]
    st.dataframe(ranking_view[cols].head(20), use_container_width=True, hide_index=True)
    st.caption(f"アクティブユーザー平均進捗: {avg_rate:.1f}%")
    st.markdown('</div>', unsafe_allow_html=True)

    passitan_rank = load_all_user_area_progress("passitan")
    if not passitan_rank.empty:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### パス単 学習進捗ランキング")
        pv = passitan_rank.copy()
        pv["progress_rate"] = pv["progress_rate"].round(1)
        pv = pv.rename(columns={
            "rank": "順位",
            "display_user": "ユーザー",
            "progress_rate": "進捗%",
            "completed_count": "Known/完了",
            "total_count": "表示/学習数",
            "records": "記録項目",
            "last_study_at": "最終学習",
        })
        st.dataframe(pv[["順位", "ユーザー", "進捗%", "Known/完了", "表示/学習数", "記録項目", "最終学習"]].head(20), use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

    recent_events = load_recent_all_user_study_events(limit=20)
    if not recent_events.empty:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 最近のテスト・学習履歴")
        ev = recent_events.copy()
        ev["score_rate"] = pd.to_numeric(ev["score_rate"], errors="coerce").fillna(0).round(1)
        ev = ev.rename(columns={
            "display_user": "ユーザー",
            "area": "分野",
            "event_type": "種類",
            "title": "内容",
            "total_count": "問題数",
            "completed_count": "正解/完了",
            "score_rate": "正解率%",
            "created_at": "日時",
        })
        st.dataframe(ev[["ユーザー", "分野", "種類", "内容", "問題数", "正解/完了", "正解率%", "日時"]], use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)


def render_my_study_overview():
    """Overviewの一番上に、ログイン中ユーザー本人の進捗を表示します。"""
    user_email = st.session_state.get("auth_email", "")
    st.subheader("👤 自分の学習状況")

    progress_df = load_study_progress()
    events_df = load_study_events(limit=50)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(f"### ログイン中: {html.escape(str(user_email))}", unsafe_allow_html=True)

    if progress_df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("全体進捗", "0.0%")
        c2.metric("記録項目", 0)
        c3.metric("完了/正解", 0)
        c4.metric("最終学習", "-")
        st.info("まだ自分の学習記録がありません。パス単・パス単テスト・special-lessonを使うと、ここに自動で表示されます。")
    else:
        progress_df = progress_df.copy()
        progress_df["score_rate"] = pd.to_numeric(progress_df["score_rate"], errors="coerce").fillna(0.0)
        progress_df["total_count"] = pd.to_numeric(progress_df["total_count"], errors="coerce").fillna(0).astype(int)
        progress_df["completed_count"] = pd.to_numeric(progress_df["completed_count"], errors="coerce").fillna(0).astype(int)

        total_items = int(progress_df["total_count"].sum())
        completed_items = int(progress_df["completed_count"].sum())
        overall_rate = percent_value(completed_items, total_items)
        latest_updated = str(progress_df["updated_at"].max()) if "updated_at" in progress_df.columns else ""

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("自分の全体進捗", f"{overall_rate:.1f}%")
        c2.metric("記録項目", len(progress_df))
        c3.metric("完了/正解", f"{completed_items} / {total_items}")
        c4.metric("最終学習", latest_updated[:10] if latest_updated else "-")

        st.markdown("#### 最近勉強した場所")
        latest = progress_df.sort_values("updated_at", ascending=False).head(4)
        for _, row in latest.iterrows():
            rate = float(row.get("score_rate") or 0)
            st.progress(min(1.0, max(0.0, rate / 100)))
            st.write(
                f"**{row.get('title','')}**  —  "
                f"{int(row.get('completed_count') or 0)} / {int(row.get('total_count') or 0)} "
                f"（{rate:.1f}%） / {row.get('status','')} / 更新: {str(row.get('updated_at',''))[:19]}"
            )

        area_summary = progress_df.groupby("area", as_index=False).agg(
            total_count=("total_count", "sum"),
            completed_count=("completed_count", "sum"),
            records=("item_key", "count"),
        )
        area_summary["進捗率%"] = area_summary.apply(lambda r: percent_value(r["completed_count"], r["total_count"]), axis=1).round(1)
        area_summary = area_summary.rename(columns={
            "area": "分野",
            "total_count": "合計",
            "completed_count": "完了/正解",
            "records": "記録数",
        })
        st.markdown("#### 分野別の自分の進捗")
        st.dataframe(area_summary[["分野", "進捗率%", "完了/正解", "合計", "記録数"]], use_container_width=True, hide_index=True)

    # 前回の場所は、学習記録がまだ無い場合でも表示します。
    app_progress = load_user_progress("app", {})
    passitan_progress = load_user_progress("passitan", {})
    passitan_test_progress = load_user_progress("passitan_test", {})
    special_progress = load_user_progress("special_lesson", {})

    st.markdown("#### 前回の学習場所")
    last_rows = []
    if app_progress.get("last_page"):
        last_rows.append({"項目": "前回開いた画面", "内容": app_progress.get("last_page", "")})
    if passitan_progress:
        last_rows.append({
            "項目": "パス単",
            "内容": f"{passitan_progress.get('selected_grade','')} / {passitan_progress.get('section_label') or passitan_progress.get('start_no','')} / {passitan_progress.get('view_mode','')}",
        })
    if passitan_test_progress:
        last_rows.append({
            "項目": "パス単テスト",
            "内容": f"{passitan_test_progress.get('selected_grade','')} / {passitan_test_progress.get('scope_label','')} / {passitan_test_progress.get('selected_count','')}",
        })
    if special_progress:
        last_rows.append({
            "項目": "special-lesson",
            "内容": f"Unit: {special_progress.get('selected_unit','')} / Type: {special_progress.get('selected_qtype','')} / {special_progress.get('count_label','')}",
        })

    if last_rows:
        st.dataframe(pd.DataFrame(last_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("前回の場所はまだ保存されていません。")

    if not events_df.empty:
        ev = events_df.copy()
        ev["score_rate"] = pd.to_numeric(ev["score_rate"], errors="coerce").fillna(0).round(1)
        ev = ev.rename(columns={
            "area": "分野",
            "event_type": "種類",
            "title": "内容",
            "total_count": "問題数",
            "completed_count": "正解/完了",
            "score_rate": "正解率%",
            "created_at": "日時",
        })
        st.markdown("#### 自分の最近のテスト履歴")
        st.dataframe(ev[["分野", "種類", "内容", "問題数", "正解/完了", "正解率%", "日時"]].head(10), use_container_width=True, hide_index=True)

    st.markdown('</div>', unsafe_allow_html=True)


def auth_page():
    """ログイン前だけ表示する登録 / ログイン画面。"""
    st.markdown(
        """
        <div class="hero">
          <span class="pill">Login Required</span><span class="pill">Email Account</span>
          <h1>英検語彙ダッシュボード</h1>
          <p>メールアドレスで登録またはログインしてから、サービスを使用できます。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    login_tab, register_tab = st.tabs(["ログイン", "新規登録"])

    with login_tab:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        with st.form("login_form"):
            email = st.text_input("メールアドレス", key="login_email")
            password = st.text_input("パスワード", type="password", key="login_password")
            submitted = st.form_submit_button("ログイン", type="primary")
            if submitted:
                ok, msg = authenticate_user(email, password)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        st.markdown('</div>', unsafe_allow_html=True)

    with register_tab:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        with st.form("register_form"):
            email = st.text_input("登録メールアドレス", key="register_email")
            password = st.text_input("登録パスワード（6文字以上）", type="password", key="register_password")
            password2 = st.text_input("登録パスワード（確認）", type="password", key="register_password2")
            submitted = st.form_submit_button("登録する", type="primary")
            if submitted:
                if password != password2:
                    st.error("確認用パスワードが一致しません。")
                else:
                    ok, msg = create_user(email, password)
                    st.success(msg) if ok else st.error(msg)
        st.markdown('</div>', unsafe_allow_html=True)


def ensure_user_vocab_columns(cur):
    """既存DBにも忘却曲線用の列を安全に追加します。"""
    cur.execute("PRAGMA table_info(user_vocab)")
    existing = {row[1] for row in cur.fetchall()}
    columns = {
        "japanese_translation": "TEXT DEFAULT ''",
        "explanation": "TEXT DEFAULT ''",
        "difficulty_level": "INTEGER DEFAULT 0",
        "ease_factor": "REAL DEFAULT 2.5",
        "interval_days": "INTEGER DEFAULT 0",
        "repetitions": "INTEGER DEFAULT 0",
        "lapses": "INTEGER DEFAULT 0",
        "last_reviewed_at": "TEXT DEFAULT ''",
        "next_review_date": "TEXT DEFAULT ''",
    }
    for col, ddl in columns.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE user_vocab ADD COLUMN {col} {ddl}")

    cur.execute(
        """
        UPDATE user_vocab
        SET next_review_date = DATE('now')
        WHERE next_review_date IS NULL OR next_review_date = ''
        """
    )


def init_db():
    con = connect()
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year TEXT NOT NULL,
            session TEXT NOT NULL,
            grade TEXT NOT NULL,
            qno INTEGER NOT NULL,
            question TEXT NOT NULL,
            translation TEXT,
            choices_json TEXT NOT NULL,
            answer INTEGER NOT NULL,
            explanation TEXT,
            choice_notes_json TEXT,
            synonyms TEXT,
            difficulty TEXT DEFAULT '標準',
            tags TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(year, session, grade, qno)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_vocab (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL UNIQUE,
            meaning TEXT DEFAULT '',
            japanese_translation TEXT DEFAULT '',
            explanation TEXT DEFAULT '',
            source_exam TEXT DEFAULT '',
            source_qno INTEGER,
            example_sentence TEXT DEFAULT '',
            synonyms TEXT DEFAULT '',
            note TEXT DEFAULT '',
            status TEXT DEFAULT '未学習',
            review_count INTEGER DEFAULT 0,
            ease_factor REAL DEFAULT 2.5,
            interval_days INTEGER DEFAULT 0,
            repetitions INTEGER DEFAULT 0,
            lapses INTEGER DEFAULT 0,
            last_reviewed_at TEXT DEFAULT '',
            next_review_date TEXT DEFAULT '',
            difficulty_level INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS passitan_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            no INTEGER NOT NULL UNIQUE,
            word TEXT NOT NULL,
            meaning TEXT DEFAULT '',
            example_sentence TEXT DEFAULT '',
            source TEXT DEFAULT '英検準1級 でる順パス単',
            known INTEGER DEFAULT 0,
            note TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login_at TEXT DEFAULT ''
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            area TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, area)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_study_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            area TEXT NOT NULL,
            item_key TEXT NOT NULL,
            title TEXT NOT NULL,
            unit TEXT DEFAULT '',
            section_no TEXT DEFAULT '',
            total_count INTEGER DEFAULT 0,
            completed_count INTEGER DEFAULT 0,
            score_rate REAL DEFAULT 0,
            status TEXT DEFAULT '学習中',
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, area, item_key)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_study_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            area TEXT NOT NULL,
            event_type TEXT NOT NULL,
            title TEXT NOT NULL,
            total_count INTEGER DEFAULT 0,
            completed_count INTEGER DEFAULT 0,
            score_rate REAL DEFAULT 0,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # app.py と同じフォルダに CSV がある場合、パス単データを自動取り込みします。
    csv_path = APP_DIR / "eiken_jun1_passitan_wordlist_enriched.csv"
    if csv_path.exists():
        try:
            passitan_df = pd.read_csv(csv_path, encoding="utf-8-sig")
            needed = {"no", "word", "meaning", "example_sentence"}
            if needed.issubset(set(passitan_df.columns)):
                for _, r in passitan_df.iterrows():
                    cur.execute(
                        """
                        INSERT INTO passitan_words (no, word, meaning, example_sentence, source)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(no) DO UPDATE SET
                            word=excluded.word,
                            meaning=excluded.meaning,
                            example_sentence=excluded.example_sentence,
                            source=excluded.source,
                            updated_at=CURRENT_TIMESTAMP
                        """,
                        (
                            int(r["no"]),
                            str(r["word"]),
                            str(r.get("meaning", "")),
                            str(r.get("example_sentence", "")),
                            str(r.get("source", "英検準1級 でる順パス単")),
                        ),
                    )
        except Exception:
            pass

    ensure_user_vocab_columns(cur)

    cur.execute("SELECT COUNT(*) FROM questions")
    count = cur.fetchone()[0]
    if count == 0:
        for item in SEED_QUESTIONS:
            cur.execute(
                """
                INSERT OR IGNORE INTO questions
                (year, session, grade, qno, question, translation, choices_json, answer, explanation, choice_notes_json, synonyms, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["year"], item["session"], item["grade"], item["qno"], item["question"],
                    item.get("translation", ""), json.dumps(item["choices"], ensure_ascii=False), item["answer"],
                    item.get("explanation", ""), json.dumps(item.get("choice_notes", []), ensure_ascii=False),
                    item.get("synonyms", ""), f"2025-{item['session']},語彙,英検準1級"
                ),
            )
    con.commit()
    con.close()


def load_questions():
    con = connect()
    df = pd.read_sql_query("SELECT * FROM questions ORDER BY year, CAST(session AS INTEGER), qno", con)
    con.close()
    if df.empty:
        return df
    df["choices"] = df["choices_json"].apply(lambda x: json.loads(x) if x else [])
    df["choice_notes"] = df["choice_notes_json"].apply(lambda x: json.loads(x) if x else [])
    df["correct_word"] = df.apply(lambda r: r["choices"][int(r["answer"])-1] if r["choices"] else "", axis=1)
    df["year"] = df["year"].astype(str).str.strip()
    df["session"] = df["session"].astype(str).str.strip()
    df["exam"] = df["year"] + "-" + df["session"]
    return df



def load_special_lesson_questions():
    """special_lesson.db から special-lesson 用の問題を読み込みます。"""
    db_path = next((p for p in SPECIAL_LESSON_DB_CANDIDATES if p.exists()), None)
    if db_path is None:
        names = " / ".join(p.name for p in SPECIAL_LESSON_DB_CANDIDATES[:2])
        return pd.DataFrame(), f"DBが見つかりません: {names} のどちらかを app.py と同じフォルダに置いてください。"

    try:
        con = sqlite3.connect(db_path, check_same_thread=False)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='questions'")
        if cur.fetchone() is None:
            con.close()
            return pd.DataFrame(), f"special-lesson DBに questions テーブルがありません: {db_path.name}"

        cur.execute("PRAGMA table_info(questions)")
        existing_cols = {row[1] for row in cur.fetchall()}
        required_cols = ["unit", "qtype", "no", "question", "options", "answer", "jp_translation", "explanation"]
        missing = [c for c in required_cols if c not in existing_cols]
        if missing:
            con.close()
            return pd.DataFrame(), f"special-lesson DBのquestionsテーブルに必要な列がありません: {', '.join(missing)}"

        df = pd.read_sql_query(
            """
            SELECT unit, qtype, no, question, options, answer, jp_translation, explanation
            FROM questions
            ORDER BY unit, qtype, no
            """,
            con,
        )
        con.close()
    except Exception as e:
        return pd.DataFrame(), f"special-lesson DBの読み込みに失敗しました: {e}"

    if df.empty:
        return df, "問題データがありません。"

    for col in ["unit", "qtype", "question", "options", "answer", "jp_translation", "explanation"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)
    df["no"] = pd.to_numeric(df["no"], errors="coerce").fillna(0).astype(int)
    return df, ""


def parse_special_options(options_text):
    """DBのoptions列(JSON文字列)を選択肢リストへ変換します。"""
    options_text = str(options_text or "").strip()
    if not options_text:
        return []
    try:
        parsed = json.loads(options_text)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except Exception:
        pass
    return [x.strip() for x in options_text.split("|") if x.strip()]


def normalize_special_answer(value):
    return " ".join(str(value or "").strip().lower().split())





def load_passitan_words():
    con = connect()
    try:
        df = pd.read_sql_query(
            """
            SELECT id, no, word, meaning, example_sentence, source, known, note, created_at, updated_at
            FROM passitan_words
            ORDER BY no
            """,
            con,
        )
    except Exception:
        df = pd.DataFrame()
    con.close()
    return df


def passitan_grade_label(source):
    """source文字列から、パス単画面で使う教材名を作ります。"""
    src = str(source or "").replace("１", "1")
    if "準1級" in src or "準1" in src or "Pre-1" in src:
        return "英検準1級"
    if "英検1級" in src or "Grade 1" in src or "EJQuotes" in src:
        return "英検1級"
    return src or "その他"


def passitan_display_no(row):
    """英検1級の取り込み時にnoteへ保存された元No.を表示用No.として使います。"""
    note = str(row.get("note", "") or "")
    m = None
    try:
        import re
        m = re.search(r"source_no=(\d+)", note)
    except Exception:
        m = None
    if m:
        return int(m.group(1))
    try:
        return int(row.get("no", 0))
    except Exception:
        return 0


def passitan_key_slug(label):
    return (
        str(label)
        .replace("英検", "eiken")
        .replace("準", "pre")
        .replace("級", "")
        .replace(" ", "_")
    )

def build_passitan_sections(max_no, section_size=100, fixed_count=None):
    """パス単を section_size 語ごとのSectionに分けます。例: Section 1 = 1〜100。"""
    try:
        max_no = int(max_no)
    except Exception:
        max_no = 0

    if fixed_count is None:
        section_count = max(1, (max_no + section_size - 1) // section_size)
    else:
        section_count = int(fixed_count)

    sections = []
    for i in range(1, section_count + 1):
        start = (i - 1) * section_size + 1
        end = i * section_size
        if fixed_count is None:
            end = min(end, max_no)
        sections.append({
            "section": i,
            "start": start,
            "end": end,
            "label": f"Section {i}: {start}〜{end}",
        })
    return sections



def update_passitan_known(row_id, known):
    con = connect()
    con.execute(
        "UPDATE passitan_words SET known=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (1 if known else 0, int(row_id)),
    )
    con.commit()
    con.close()


def import_passitan_csv_to_db(csv_file):
    try:
        df = pd.read_csv(csv_file, encoding="utf-8-sig")
    except Exception:
        csv_file.seek(0)
        df = pd.read_csv(csv_file)

    # 元CSV: No, 英単語, 意味 / 生成済CSV: no, word, meaning, example_sentence
    rename_map = {
        "No": "no",
        "英単語": "word",
        "意味": "meaning",
        "例文": "example_sentence",
    }
    df = df.rename(columns=rename_map)
    required = {"no", "word", "meaning"}
    if not required.issubset(set(df.columns)):
        return False, "CSVの列名は No, 英単語, 意味 が必要です。"
    if "example_sentence" not in df.columns:
        df["example_sentence"] = df.apply(lambda r: simple_example_sentence(str(r["word"]), str(r["meaning"])), axis=1)
    con = connect()
    cur = con.cursor()
    count = 0
    for _, r in df.iterrows():
        cur.execute(
            """
            INSERT INTO passitan_words (no, word, meaning, example_sentence, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(no) DO UPDATE SET
                word=excluded.word,
                meaning=excluded.meaning,
                example_sentence=excluded.example_sentence,
                source=excluded.source,
                updated_at=CURRENT_TIMESTAMP
            """,
            (int(r["no"]), str(r["word"]), str(r["meaning"]), str(r["example_sentence"]), "英検準1級 でる順パス単 CSV"),
        )
        count += 1
    con.commit()
    con.close()
    return True, f"{count}語を取り込みました。"


def simple_example_sentence(word, meaning=""):
    word = str(word).strip()
    meaning = str(meaning).strip()
    if " " in word or "～" in word:
        phrase = word.replace("～", "the problem").replace("(～)", "the issue")
        if phrase.startswith("be ") or phrase.startswith("(be)"):
            phrase = phrase.replace("(be)", "be")
            return f"Students should {phrase} during group projects."
        return f"The team decided to {phrase} before the deadline."
    exceptions = {
        "last": "The meeting will last for about two hours.",
        "affect": "The new rule may affect many students.",
        "claim": "He claimed that the plan would save money.",
        "ship": "The company will ship the products tomorrow.",
        "issue": "The team discussed the issue for a long time.",
        "purchase": "She decided to purchase a new laptop.",
        "occur": "Serious accidents can occur in bad weather.",
        "deal": "The manager had to deal with several complaints.",
        "consume": "Large factories consume a lot of energy.",
        "present": "The scientist will present her research tomorrow.",
    }
    if word.lower() in exceptions:
        return exceptions[word.lower()]
    if word.lower().endswith("ly"):
        return f"She responded {word} during the meeting."
    if meaning.startswith(("を", "に")):
        return f"The new policy may {word} the whole community."
    return f"The article explained the meaning of {word} clearly."


def add_question(data):
    con = connect()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO questions
        (year, session, grade, qno, question, translation, choices_json, answer, explanation, choice_notes_json, synonyms, difficulty, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        data,
    )
    con.commit()
    con.close()


def delete_question(qid):
    con = connect()
    con.execute("DELETE FROM questions WHERE id=?", (int(qid),))
    con.commit()
    con.close()


def update_question(qid, fields):
    con = connect()
    keys = list(fields.keys())
    sql = ", ".join([f"{k}=?" for k in keys]) + ", updated_at=CURRENT_TIMESTAMP"
    vals = [fields[k] for k in keys] + [int(qid)]
    con.execute(f"UPDATE questions SET {sql} WHERE id=?", vals)
    con.commit()
    con.close()


def extract_choice_note(row, choice_index):
    """選択肢解析から、指定選択肢の説明を取り出します。"""
    notes = row.get("choice_notes", [])
    if not isinstance(notes, list) or not notes:
        return ""

    choices = row.get("choices", [])
    if isinstance(choices, list) and 1 <= choice_index <= len(choices):
        word = str(choices[choice_index - 1]).strip().lower()
        for note in notes:
            note_text = str(note).strip()
            if note_text.lower().startswith(word):
                return note_text

    if 1 <= choice_index <= len(notes):
        return str(notes[choice_index - 1]).strip()
    return ""


def add_vocab_word(word, meaning="", source_exam="", source_qno=None, example_sentence="", synonyms="", note="", japanese_translation="", explanation=""):
    """自分用単語帳に単語を登録します。既存単語なら空でない項目だけ更新します。"""
    word = str(word).strip()
    if not word:
        return False, "単語が空です。"

    meaning = str(meaning or "").strip()
    japanese_translation = str(japanese_translation or "").strip()
    explanation = str(explanation or "").strip()
    example_sentence = str(example_sentence or "").strip()
    synonyms = str(synonyms or "").strip()
    note = str(note or "").strip()
    source_exam = str(source_exam or "").strip()

    con = connect()
    try:
        con.execute(
            """
            INSERT INTO user_vocab
            (word, meaning, japanese_translation, explanation, source_exam, source_qno,
             example_sentence, synonyms, note, status, next_review_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '未学習', DATE('now'))
            ON CONFLICT(word) DO UPDATE SET
                meaning = CASE WHEN excluded.meaning != '' THEN excluded.meaning ELSE user_vocab.meaning END,
                japanese_translation = CASE WHEN excluded.japanese_translation != '' THEN excluded.japanese_translation ELSE user_vocab.japanese_translation END,
                explanation = CASE WHEN excluded.explanation != '' THEN excluded.explanation ELSE user_vocab.explanation END,
                source_exam = CASE WHEN excluded.source_exam != '' THEN excluded.source_exam ELSE user_vocab.source_exam END,
                source_qno = CASE WHEN excluded.source_qno IS NOT NULL THEN excluded.source_qno ELSE user_vocab.source_qno END,
                example_sentence = CASE WHEN excluded.example_sentence != '' THEN excluded.example_sentence ELSE user_vocab.example_sentence END,
                synonyms = CASE WHEN excluded.synonyms != '' THEN excluded.synonyms ELSE user_vocab.synonyms END,
                note = CASE WHEN excluded.note != '' THEN excluded.note ELSE user_vocab.note END,
                next_review_date = CASE
                    WHEN user_vocab.next_review_date IS NULL OR user_vocab.next_review_date = '' THEN DATE('now')
                    ELSE user_vocab.next_review_date
                END,
                updated_at = CURRENT_TIMESTAMP
            """,
            (word, meaning, japanese_translation, explanation, source_exam, source_qno, example_sentence, synonyms, note),
        )
        con.commit()
        return True, f"{word} を単語帳に登録しました。"
    except Exception as e:
        return False, str(e)
    finally:
        con.close()


def load_vocab():
    con = connect()
    try:
        df = pd.read_sql_query(
            """
            SELECT id, word, meaning, japanese_translation, explanation, source_exam, source_qno,
                   example_sentence, synonyms, note, status, review_count, ease_factor,
                   interval_days, repetitions, lapses, last_reviewed_at, next_review_date,
                   difficulty_level, created_at, updated_at
            FROM user_vocab
            ORDER BY
                CASE WHEN next_review_date IS NULL OR next_review_date = '' THEN '1900-01-01' ELSE next_review_date END ASC,
                updated_at DESC,
                word
            """,
            con,
        )
    finally:
        con.close()

    if not df.empty:
        df["next_review_date"] = df["next_review_date"].fillna("").replace("", today_iso())
        df["is_due"] = df["next_review_date"] <= today_iso()
    return df


def delete_vocab_word(vocab_id):
    con = connect()
    con.execute("DELETE FROM user_vocab WHERE id=?", (int(vocab_id),))
    con.commit()
    con.close()


def update_vocab_status(vocab_id, status):
    con = connect()
    con.execute(
        "UPDATE user_vocab SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (status, int(vocab_id)),
    )
    con.commit()
    con.close()

def review_vocab_word(vocab_id, result):
    """忘却曲線を考慮した簡易SM-2方式で次回復習日を更新します。"""
    con = connect()
    cur = con.cursor()
    cur.execute(
        "SELECT ease_factor, interval_days, repetitions, lapses FROM user_vocab WHERE id=?",
        (int(vocab_id),),
    )
    row = cur.fetchone()
    if not row:
        con.close()
        return False, "単語が見つかりません。"

    ease = float(row[0] or 2.5)
    interval = int(row[1] or 0)
    reps = int(row[2] or 0)
    lapses = int(row[3] or 0)

    if result == "again":
        reps = 0
        interval = 1
        ease = max(1.3, ease - 0.25)
        lapses += 1
        status = "復習中"
    elif result == "hard":
        reps += 1
        interval = max(1, int(round(max(interval, 1) * 1.2)))
        ease = max(1.3, ease - 0.15)
        status = "復習中"
    elif result == "easy":
        reps += 1
        if reps <= 1:
            interval = 3
        elif reps == 2:
            interval = 7
        else:
            interval = max(interval + 1, int(round(interval * (ease + 0.35))))
        ease = min(3.2, ease + 0.15)
        status = "覚えた" if interval >= 14 else "復習中"
    else:  # good
        reps += 1
        if reps <= 1:
            interval = 1
        elif reps == 2:
            interval = 3
        else:
            interval = max(interval + 1, int(round(interval * ease)))
        status = "覚えた" if interval >= 14 else "復習中"

    next_date = (date.today() + timedelta(days=interval)).isoformat()
    cur.execute(
        """
        UPDATE user_vocab
        SET status=?, review_count=review_count+1, ease_factor=?, interval_days=?,
            repetitions=?, lapses=?, last_reviewed_at=DATE('now'), next_review_date=?,
            updated_at=CURRENT_TIMESTAMP
        WHERE id=?
        """,
        (status, ease, interval, reps, lapses, next_date, int(vocab_id)),
    )
    con.commit()
    con.close()
    return True, f"次回復習日を {next_date} に設定しました。"


def register_pdf_fonts():
    """PDF用フォントを登録します。日本語を入れても文字化けしにくいようにします。"""
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    bold_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]

    font_name = "Helvetica"
    bold_name = "Helvetica-Bold"

    for fp in font_candidates:
        if Path(fp).exists():
            try:
                pdfmetrics.registerFont(TTFont("AppFont", fp))
                font_name = "AppFont"
                break
            except Exception:
                pass

    for fp in bold_candidates:
        if Path(fp).exists():
            try:
                pdfmetrics.registerFont(TTFont("AppFontBold", fp))
                bold_name = "AppFontBold"
                break
            except Exception:
                pass

    return font_name, bold_name


def make_question_pdf(exam_df, exam_name):
    """年度回ごとの問題一覧PDFを作成します。答え・解説・日本語訳は入れません。"""
    if not HAS_REPORTLAB:
        raise RuntimeError("reportlab がインストールされていません。コマンドプロンプトで python -m pip install reportlab を実行してください。")
    EXPORT_DIR.mkdir(exist_ok=True)
    output_path = EXPORT_DIR / f"eiken_pre1_{exam_name}_questions.pdf"

    font_name, bold_name = register_pdf_fonts()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCustom",
        parent=styles["Title"],
        fontName=bold_name,
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    subtitle_style = ParagraphStyle(
        "SubtitleCustom",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"),
        spaceAfter=12,
    )
    q_style = ParagraphStyle(
        "QuestionCustom",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=10.5,
        leading=15,
        spaceAfter=5,
    )
    choice_style = ParagraphStyle(
        "ChoiceCustom",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=9.5,
        leading=13,
    )

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    story = []
    story.append(Paragraph(f"Eiken Grade Pre-1 Vocabulary Questions - {exam_name}", title_style))
    story.append(Paragraph("Questions only: answers, explanations, translations, and analysis are not included.", subtitle_style))

    pdf_df = exam_df.sort_values("qno")
    for _, row in pdf_df.iterrows():
        qno = int(row["qno"])
        question = str(row["question"]).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(f"<b>({qno})</b> {question}", q_style))

        choices = row["choices"] if isinstance(row["choices"], list) else []
        cells = []
        for i in range(4):
            choice_text = choices[i] if i < len(choices) else ""
            choice_text = str(choice_text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            cells.append(Paragraph(f"<b>{i + 1}</b>&nbsp;&nbsp;{choice_text}", choice_style))

        table = Table([cells], colWidths=[42 * mm, 42 * mm, 42 * mm, 42 * mm])
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)
        story.append(Spacer(1, 5 * mm))

    def footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setFont(font_name, 8)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawRightString(195 * mm, 8 * mm, f"Page {doc_obj.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output_path


def pdf_page(df):
    st.subheader("📄 PDF生成")
    st.caption("年度回ごとの問題一覧PDFを作成します。PDFには答え・解説・日本語訳・選択肢解析を入れません。")

    if df.empty:
        st.warning("問題データがありません。")
        return

    exams = sorted(df["exam"].dropna().unique().tolist(), key=lambda x: tuple(map(int, x.split("-"))) if "-" in x else (9999, 9999))
    selected_exam = st.selectbox("PDFを作成する年度回", exams)
    exam_df = df[df["exam"] == selected_exam].copy()

    st.info(f"{selected_exam} の問題数: {len(exam_df)}問")

    preview_cols = ["exam", "qno", "question"]
    st.dataframe(exam_df[preview_cols].sort_values("qno"), use_container_width=True, hide_index=True)

    if st.button("この年度回のPDFを生成して保存", type="primary"):
        try:
            pdf_path = make_question_pdf(exam_df, selected_exam)
            st.success(f"PDFを保存しました: {pdf_path}")
            with open(pdf_path, "rb") as f:
                st.download_button(
                    "生成したPDFをダウンロード",
                    data=f.read(),
                    file_name=pdf_path.name,
                    mime="application/pdf",
                )
        except Exception as e:
            st.error(f"PDF生成に失敗しました: {e}")

def render_hero(df):
    st.markdown(
        """
        <div class="hero">
          <span class="pill">Eiken Grade Pre-1</span><span class="pill">Vocabulary DB</span><span class="pill">Translation + Choice Analysis</span>
          <h1>Learning Engish Dashbord</h1>
          <p>過去問題の文章・日本語訳・選択肢解析・類義語を一元管理し、ダッシュボードから問題を追加できます。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("問題数", len(df))
    c2.metric("収録回", df["exam"].nunique() if not df.empty else 0)
    c3.metric("単語数", df["correct_word"].nunique() if not df.empty else 0)
    c4.metric("Grade", "Pre-1")


def sidebar_filters(df):
    st.sidebar.title("📘 Menu")
    if st.session_state.get("auth_email"):
        st.sidebar.caption(f"ログイン中: {st.session_state['auth_email']}")
        if st.sidebar.button("ログアウト"):
            logout_user()
            st.rerun()
    st.sidebar.divider()

    page_options = ["🏠 Overview", "📚 試験問題", "🧠 Quiz", "📗 パス単", "🧪 パス単テスト", "🌟 special-lesson", "📈 学習記録", "📝 単語帳", "📄 PDF生成", "➕ 問題を追加", "🛠 データ管理"]
    app_progress = load_user_progress("app", {})
    set_session_default_from_progress("main_page_select", app_progress.get("last_page"), page_options)

    page = st.sidebar.radio(
        "画面",
        page_options,
        key="main_page_select",
        label_visibility="collapsed",
    )

    question_submenu = None
    if page == "📚 試験問題":
        with st.sidebar.expander("📚 試験問題サブメニュー", expanded=True):
            question_submenu = st.radio(
                "問題タイプ",
                ["Vocabulary", "Reading", "Grammar"],
                index=0,
                key="question_list_submenu",
            )

    st.sidebar.divider()
    st.sidebar.subheader("Filter")

    if df.empty or "exam" not in df.columns:
        exams = []
    else:
        exams = (
            df["exam"]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        # 年度順に並べる：2024-1, 2024-2, 2024-3, 2025-1...
        def exam_sort_key(x):
            try:
                year, round_no = x.split("-")
                return int(year), int(round_no)
            except Exception:
                return 9999, 9999

        exams = sorted(exams, key=exam_sort_key)

    selected = st.sidebar.multiselect(
        "年度回",
        exams,
        default=exams
    )

    keyword = st.sidebar.text_input(
        "検索",
        placeholder="例: remote / 迂回 / alarm"
    )

    return page, selected, keyword, question_submenu


def apply_filter(df, selected, keyword):
    out = df.copy()
    if selected:
        out = out[out["exam"].isin(selected)]
    if keyword:
        k = keyword.lower().strip()
        mask = (
            out["question"].str.lower().str.contains(k, na=False)
            | out["translation"].str.lower().str.contains(k, na=False)
            | out["correct_word"].str.lower().str.contains(k, na=False)
            | out["explanation"].str.lower().str.contains(k, na=False)
            | out["synonyms"].str.lower().str.contains(k, na=False)
        )
        out = out[mask]
    return out


def render_card(row, show_answer=True):
    choices = row["choices"]
    notes = row["choice_notes"]
    correct = choices[int(row["answer"]) - 1]
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(f'<span class="badge">{row["exam"]}</span><span class="badge">Q{int(row["qno"])}</span><span class="badge">{row.get("difficulty", "標準")}</span>', unsafe_allow_html=True)
    st.markdown(f'<div class="question"><span class="qnum">({int(row["qno"])})</span> {row["question"]}</div>', unsafe_allow_html=True)
    cols = st.columns(4)
    for i, ch in enumerate(choices, start=1):
        prefix = "✅" if show_answer and i == int(row["answer"]) else f"{i}."
        cols[i-1].markdown(f"**{prefix} {ch}**")
    if show_answer:
        st.markdown(f'<div class="translation">🇯🇵 {row["translation"]}</div>', unsafe_allow_html=True)
        st.markdown(f'<p class="answer">正解: {int(row["answer"])}. {correct}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="small"><b>解説:</b> {row["explanation"]}</p>', unsafe_allow_html=True)
        with st.expander("選択肢の意味・ひっかけポイント"):
            for n in notes:
                st.write("・" + n)
        st.markdown(f'<p class="small"><b>類義語:</b> {row["synonyms"]}</p>', unsafe_allow_html=True)

        meaning = extract_choice_note(row, int(row["answer"]))
        if st.button(f"📝 {correct} を単語帳に登録", key=f"vocab_card_{row['id']}"):
            ok, msg = add_vocab_word(
                correct,
                meaning=meaning,
                japanese_translation=meaning,
                explanation=row.get("explanation", ""),
                source_exam=row["exam"],
                source_qno=int(row["qno"]),
                example_sentence=row["question"],
                synonyms=row.get("synonyms", ""),
                note="試験問題から登録",
            )
            st.success(msg) if ok else st.error(msg)

        with st.expander("わからない選択肢を単語帳に登録"):
            for idx, ch in enumerate(choices, start=1):
                choice_meaning = extract_choice_note(row, idx)
                c_word, c_btn = st.columns([3, 1])
                c_word.write(f"{idx}. **{ch}**  {choice_meaning}")
                if c_btn.button("登録", key=f"vocab_choice_{row['id']}_{idx}"):
                    ok, msg = add_vocab_word(
                        ch,
                        meaning=choice_meaning,
                        japanese_translation=choice_meaning,
                        explanation=row.get("explanation", ""),
                        source_exam=row["exam"],
                        source_qno=int(row["qno"]),
                        example_sentence=row["question"],
                        synonyms="",
                        note="試験問題の選択肢から登録",
                    )
                    st.success(msg) if ok else st.error(msg)
    st.markdown('</div>', unsafe_allow_html=True)



def render_my_study_overview_visible():
    """Overviewに必ず表示する本人用サマリー。前回修正が見えない環境でも分かるように、overview()内から直接呼びます。"""
    st.markdown("## 👤 自分の学習状況（Overview）")
    user_email = st.session_state.get("auth_email", "")
    progress_df = pd.DataFrame()
    events_df = pd.DataFrame()
    try:
        progress_df = load_study_progress()
    except Exception as e:
        st.warning(f"自分の学習記録を読み込めませんでした: {e}")
    try:
        events_df = load_study_events(limit=10)
    except Exception:
        events_df = pd.DataFrame()

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(f"**ログイン中:** {html.escape(str(user_email))}", unsafe_allow_html=True)

    if progress_df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("自分の全体進捗", "0.0%")
        c2.metric("記録項目", 0)
        c3.metric("完了/正解", "0 / 0")
        c4.metric("最終学習", "-")
        st.info("まだ自分の学習記録がありません。パス単・パス単テスト・special-lessonを使うと、ここに自動で表示されます。")
    else:
        dfp = progress_df.copy()
        dfp["total_count"] = pd.to_numeric(dfp["total_count"], errors="coerce").fillna(0).astype(int)
        dfp["completed_count"] = pd.to_numeric(dfp["completed_count"], errors="coerce").fillna(0).astype(int)
        dfp["score_rate"] = pd.to_numeric(dfp["score_rate"], errors="coerce").fillna(0.0)
        total_count = int(dfp["total_count"].sum())
        completed_count = int(dfp["completed_count"].sum())
        overall = percent_value(completed_count, total_count)
        last_day = str(dfp["updated_at"].max())[:10] if "updated_at" in dfp.columns else "-"

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("自分の全体進捗", f"{overall:.1f}%")
        c2.metric("記録項目", len(dfp))
        c3.metric("完了/正解", f"{completed_count} / {total_count}")
        c4.metric("最終学習", last_day or "-")

        st.markdown("### 最近勉強した内容")
        for _, row in dfp.sort_values("updated_at", ascending=False).head(5).iterrows():
            rate = float(row.get("score_rate") or 0)
            st.progress(min(1.0, max(0.0, rate / 100)))
            st.write(
                f"**{row.get('title', '')}**  "
                f"{int(row.get('completed_count') or 0)} / {int(row.get('total_count') or 0)} "
                f"（{rate:.1f}%） / {row.get('status', '')}"
            )

        area_df = dfp.groupby("area", as_index=False).agg(
            total_count=("total_count", "sum"),
            completed_count=("completed_count", "sum"),
            records=("item_key", "count"),
        )
        area_df["進捗率%"] = area_df.apply(lambda r: percent_value(r["completed_count"], r["total_count"]), axis=1).round(1)
        area_df = area_df.rename(columns={"area": "分野", "total_count": "合計", "completed_count": "完了/正解", "records": "記録数"})
        st.markdown("### 分野別の自分の進捗")
        st.dataframe(area_df[["分野", "進捗率%", "完了/正解", "合計", "記録数"]], use_container_width=True, hide_index=True)

    st.markdown("### 前回の学習場所")
    last_rows = []
    try:
        app_progress = load_user_progress("app", {})
        passitan_progress = load_user_progress("passitan", {})
        passitan_test_progress = load_user_progress("passitan_test", {})
        special_progress = load_user_progress("special_lesson", {})
        if app_progress.get("last_page"):
            last_rows.append({"項目": "前回開いた画面", "内容": app_progress.get("last_page", "")})
        if passitan_progress:
            last_rows.append({"項目": "パス単", "内容": f"{passitan_progress.get('selected_grade','')} / {passitan_progress.get('section_label') or passitan_progress.get('start_no','')} / {passitan_progress.get('view_mode','')}"})
        if passitan_test_progress:
            last_rows.append({"項目": "パス単テスト", "内容": f"{passitan_test_progress.get('selected_grade','')} / {passitan_test_progress.get('scope_label','')} / {passitan_test_progress.get('selected_count','')}"})
        if special_progress:
            last_rows.append({"項目": "special-lesson", "内容": f"Unit: {special_progress.get('selected_unit','')} / Type: {special_progress.get('selected_qtype','')} / {special_progress.get('count_label','')}"})
    except Exception:
        last_rows = []
    if last_rows:
        st.dataframe(pd.DataFrame(last_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("前回の場所はまだ保存されていません。")

    if not events_df.empty:
        ev = events_df.copy()
        ev["score_rate"] = pd.to_numeric(ev["score_rate"], errors="coerce").fillna(0).round(1)
        ev = ev.rename(columns={"area": "分野", "event_type": "種類", "title": "内容", "total_count": "問題数", "completed_count": "正解/完了", "score_rate": "正解率%", "created_at": "日時"})
        st.markdown("### 自分の最近のテスト履歴")
        st.dataframe(ev[["分野", "種類", "内容", "問題数", "正解/完了", "正解率%", "日時"]].head(10), use_container_width=True, hide_index=True)

    st.markdown('</div>', unsafe_allow_html=True)


def overview(df):
    render_hero(df)
    render_my_study_overview_visible()
    render_all_user_ranking_overview()
    st.subheader("📊 収録データ")
    col1, col2 = st.columns([1.1, 1])
    with col1:
        count = df.groupby("exam").size().reset_index(name="questions") if not df.empty else pd.DataFrame()
        st.bar_chart(count.set_index("exam") if not count.empty else count)
    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 学習の使い方")
        st.write("1. 試験問題で文章・訳・選択肢を確認")
        st.write("2. Quizで答えを選ぶ")
        st.write("3. 類義語をまとめて覚える")
        st.write("4. パス単・テスト・special-lessonの学習記録はOverviewと学習記録に自動表示")
        st.markdown('</div>', unsafe_allow_html=True)
    st.subheader("🔥 最近の重要語")
    if df.empty:
        st.info("問題データがありません。")
    else:
        sample = df[["exam", "qno", "correct_word", "synonyms"]].tail(12).sort_values(["exam", "qno"])
        st.dataframe(sample, use_container_width=True, hide_index=True)


def list_page(df, submenu="Vocabulary"):
    st.subheader(f"📚 試験問題 / {submenu}")

    if submenu == "Vocabulary":
        st.caption("語彙問題の文章、日本語訳、正解、選択肢解析、類義語をカード形式で確認できます。")
        target_df = df
    elif submenu == "Reading":
        st.caption("Reading問題をここに表示します。現在のDBにReading問題がある場合は、tagsに Reading を入れると表示できます。")
        if "tags" in df.columns:
            target_df = df[df["tags"].astype(str).str.contains("Reading|読解|リーディング", case=False, na=False)]
        else:
            target_df = df.iloc[0:0]
    elif submenu == "Grammar":
        st.caption("Grammar問題をここに表示します。現在のDBにGrammar問題がある場合は、tagsに Grammar を入れると表示できます。")
        if "tags" in df.columns:
            target_df = df[df["tags"].astype(str).str.contains("Grammar|文法|グラマー", case=False, na=False)]
        else:
            target_df = df.iloc[0:0]
    else:
        target_df = df

    show = st.toggle("答えと解説を表示", value=False)

    if target_df.empty:
        st.info(f"{submenu} の問題データはまだありません。『問題を追加』画面でtagsに {submenu} を入れると、このサブメニューに表示できます。")
        return

    for _, row in target_df.iterrows():
        render_card(row, show_answer=show)


def quiz_page(df):
    st.subheader("🧠 Quiz Mode")

    if df.empty:
        st.warning("問題がありません。")
        return

    if "quiz_id" not in st.session_state:
        st.session_state.quiz_id = int(random.choice(df["id"].tolist()))
        st.session_state.quiz_view = "question"
        st.session_state.quiz_selected = None

    if st.session_state.quiz_id not in df["id"].tolist():
        st.session_state.quiz_id = int(random.choice(df["id"].tolist()))
        st.session_state.quiz_view = "question"
        st.session_state.quiz_selected = None

    row = df[df["id"] == st.session_state.quiz_id].iloc[0]

    if st.session_state.get("quiz_view") == "answer":
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(
            f'<span class="badge">{row["exam"]}</span>'
            f'<span class="badge">Q{int(row["qno"])}</span>',
            unsafe_allow_html=True,
        )
        st.markdown(f'<div class="question">{row["question"]}</div>', unsafe_allow_html=True)

        selected_num = st.session_state.get("quiz_selected")
        correct_num = int(row["answer"])
        correct_word = row["correct_word"]

        if selected_num == correct_num:
            st.success("正解です！")
        else:
            st.error(f"不正解です。正解は {correct_num}. {correct_word} です。")

        st.markdown(f'<div class="translation">🇯🇵 {row["translation"]}</div>', unsafe_allow_html=True)
        st.markdown(f'<p class="answer">正解: {correct_num}. {correct_word}</p>', unsafe_allow_html=True)
        st.write("**解説:**", row["explanation"])
        st.write("**類義語:**", row["synonyms"])

        with st.expander("選択肢の意味・ひっかけポイント", expanded=True):
            for n in row["choice_notes"]:
                st.write("・" + n)

        meaning = extract_choice_note(row, correct_num)
        if st.button(f"📝 {correct_word} を単語帳に登録", key=f"vocab_quiz_{row['id']}"):
            ok, msg = add_vocab_word(
                correct_word,
                meaning=meaning,
                japanese_translation=meaning,
                explanation=row.get("explanation", ""),
                source_exam=row["exam"],
                source_qno=int(row["qno"]),
                example_sentence=row["question"],
                synonyms=row.get("synonyms", ""),
                note="Quizから登録",
            )
            st.success(msg) if ok else st.error(msg)

        with st.expander("わからない選択肢を単語帳に登録"):
            for idx, ch in enumerate(row["choices"], start=1):
                choice_meaning = extract_choice_note(row, idx)
                c_word, c_btn = st.columns([3, 1])
                c_word.write(f"{idx}. **{ch}**  {choice_meaning}")
                if c_btn.button("登録", key=f"vocab_quiz_choice_{row['id']}_{idx}"):
                    ok, msg = add_vocab_word(
                        ch,
                        meaning=choice_meaning,
                        japanese_translation=choice_meaning,
                        explanation=row.get("explanation", ""),
                        source_exam=row["exam"],
                        source_qno=int(row["qno"]),
                        example_sentence=row["question"],
                        synonyms="",
                        note="Quizの選択肢から登録",
                    )
                    st.success(msg) if ok else st.error(msg)

        c1, c2 = st.columns(2)
        with c1:
            if st.button("元の画面に戻る"):
                st.session_state.quiz_view = "question"
                st.rerun()
        with c2:
            if st.button("次の問題へ"):
                st.session_state.quiz_id = int(random.choice(df["id"].tolist()))
                st.session_state.quiz_view = "question"
                st.session_state.quiz_selected = None
                st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)
        return

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(
        f'<span class="badge">{row["exam"]}</span>'
        f'<span class="badge">Q{int(row["qno"])}</span>',
        unsafe_allow_html=True,
    )
    st.markdown(f'<div class="question">{row["question"]}</div>', unsafe_allow_html=True)
    options = [f"{i}. {c}" for i, c in enumerate(row["choices"], start=1)]
    choice = st.radio("答えを選んでください", options, index=None, key=f"quiz_choice_{row['id']}")

    if st.button("Confirm"):
        if not choice:
            st.warning("選択肢を選んでください。")
        else:
            st.session_state.quiz_selected = int(choice.split(".")[0])
            st.session_state.quiz_view = "answer"
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)


def vocab_page():
    st.subheader("📝 自分用の単語帳・復習")
    st.caption("わからない単語を登録し、忘却曲線を考慮して復習できます。次回復習日は自動計算されます。")

    vocab_df = load_vocab()
    due_count = int(vocab_df["is_due"].sum()) if not vocab_df.empty and "is_due" in vocab_df.columns else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("登録単語数", len(vocab_df))
    c2.metric("今日の復習", due_count)
    c3.metric("復習中", int((vocab_df["status"] == "復習中").sum()) if not vocab_df.empty else 0)
    c4.metric("覚えた", int((vocab_df["status"] == "覚えた").sum()) if not vocab_df.empty else 0)

    tab_review, tab_list, tab_add = st.tabs(["今日の復習", "単語リスト", "手入力で追加"])

    with tab_review:
        if vocab_df.empty:
            st.info("まだ単語帳に単語がありません。")
        else:
            due_df = vocab_df[vocab_df["is_due"]].copy()
            if due_df.empty:
                st.success("今日復習する単語はありません。")
            else:
                st.info("ボタンを押すと、次回復習日が自動で更新されます。")
                for _, row in due_df.iterrows():
                    st.markdown('<div class="card">', unsafe_allow_html=True)
                    st.markdown(
                        f'<span class="badge">{row["status"]}</span>'
                        f'<span class="badge">次回: {row["next_review_date"]}</span>'
                        f'<span class="badge">間隔: {int(row["interval_days"] or 0)}日</span>'
                        f'<span class="badge">復習回数: {int(row["review_count"] or 0)}</span>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(f"### {row['word']}")
                    if row.get("meaning"):
                        st.write("**意味:**", row["meaning"])
                    if row.get("japanese_translation"):
                        st.write("**日本語翻訳・説明:**", row["japanese_translation"])
                    if row.get("explanation"):
                        st.write("**解説:**", row["explanation"])
                    if row.get("example_sentence"):
                        st.write("**例文:**", row["example_sentence"])
                    if row.get("synonyms"):
                        st.write("**類義語:**", row["synonyms"])
                    if row.get("note"):
                        st.write("**自分用メモ:**", row["note"])

                    c1, c2, c3, c4 = st.columns(4)
                    actions = [("again", "もう一度"), ("hard", "難しい"), ("good", "覚えた"), ("easy", "簡単")]
                    for col, (result, label) in zip([c1, c2, c3, c4], actions):
                        with col:
                            if st.button(label, key=f"review_{result}_{row['id']}"):
                                ok, msg = review_vocab_word(row["id"], result)
                                st.success(msg) if ok else st.error(msg)
                                st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)

    with tab_list:
        if vocab_df.empty:
            st.info("まだ単語帳に単語がありません。")
        else:
            status_filter = st.multiselect(
                "ステータス",
                ["未学習", "復習中", "覚えた"],
                default=["未学習", "復習中", "覚えた"],
            )
            due_only = st.checkbox("今日復習する単語だけ表示", value=False)
            keyword = st.text_input("単語帳内検索", placeholder="word / meaning / memo")

            view = vocab_df.copy()
            if status_filter:
                view = view[view["status"].isin(status_filter)]
            if due_only:
                view = view[view["is_due"]]
            if keyword:
                k = keyword.lower().strip()
                view = view[
                    view["word"].astype(str).str.lower().str.contains(k, na=False)
                    | view["meaning"].astype(str).str.lower().str.contains(k, na=False)
                    | view["japanese_translation"].astype(str).str.lower().str.contains(k, na=False)
                    | view["explanation"].astype(str).str.lower().str.contains(k, na=False)
                    | view["synonyms"].astype(str).str.lower().str.contains(k, na=False)
                    | view["note"].astype(str).str.lower().str.contains(k, na=False)
                ]

            st.download_button(
                "単語帳CSVをダウンロード",
                view.to_csv(index=False).encode("utf-8-sig"),
                file_name="my_vocab_list.csv",
                mime="text/csv",
            )

            for _, row in view.iterrows():
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.markdown(
                    f'<span class="badge">{row["status"]}</span>'
                    f'<span class="badge">{row["source_exam"] or "manual"}</span>'
                    f'<span class="badge">Q{int(row["source_qno"] or 0) if pd.notna(row["source_qno"]) else "-"}</span>'
                    f'<span class="badge">次回復習: {row["next_review_date"]}</span>',
                    unsafe_allow_html=True,
                )
                st.markdown(f'### {row["word"]}')
                if row["meaning"]:
                    st.write("**意味:**", row["meaning"])
                if row["japanese_translation"]:
                    st.write("**日本語翻訳・説明:**", row["japanese_translation"])
                if row["explanation"]:
                    st.write("**解説:**", row["explanation"])
                if row["synonyms"]:
                    st.write("**類義語:**", row["synonyms"])
                if row["example_sentence"]:
                    st.write("**例文:**", row["example_sentence"])
                if row["note"]:
                    st.write("**メモ:**", row["note"])

                c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1])
                with c1:
                    if st.button("未学習", key=f"status_new_{row['id']}"):
                        update_vocab_status(row["id"], "未学習")
                        st.rerun()
                with c2:
                    if st.button("復習中", key=f"status_review_{row['id']}"):
                        update_vocab_status(row["id"], "復習中")
                        st.rerun()
                with c3:
                    if st.button("覚えた", key=f"status_done_{row['id']}"):
                        update_vocab_status(row["id"], "覚えた")
                        st.rerun()
                with c4:
                    if st.button("今日復習", key=f"status_due_{row['id']}"):
                        con = connect()
                        con.execute("UPDATE user_vocab SET next_review_date=DATE('now'), updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(row["id"]),))
                        con.commit()
                        con.close()
                        st.rerun()
                with c5:
                    if st.button("削除", key=f"vocab_delete_{row['id']}"):
                        delete_vocab_word(row["id"])
                        st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

    with tab_add:
        with st.form("manual_vocab_add", clear_on_submit=True):
            c1, c2 = st.columns([1, 2])
            word = c1.text_input("単語", placeholder="例: remote")
            meaning = c2.text_input("短い意味", placeholder="例: 遠い、人里離れた")
            japanese_translation = st.text_area("日本語翻訳・説明", height=80, placeholder="詳しい意味、ニュアンス、覚え方")
            explanation = st.text_area("解説", height=80, placeholder="なぜ重要か、どんな文脈で使うか")
            synonyms = st.text_input("類義語", placeholder="例: distant, isolated, faraway")
            example = st.text_area("例文", height=80, placeholder="例: The village is in a remote area.")
            note = st.text_area("自分用メモ", height=80, placeholder="なぜ間違えたか、覚え方など")
            submitted = st.form_submit_button("単語帳に追加")
            if submitted:
                ok, msg = add_vocab_word(
                    word,
                    meaning=meaning,
                    japanese_translation=japanese_translation,
                    explanation=explanation,
                    example_sentence=example,
                    synonyms=synonyms,
                    note=note,
                )
                st.success(msg) if ok else st.error(msg)
                st.rerun()




def render_browser_speak_button(word, key, label="🔊", height=34):
    """ブラウザ標準の Web Speech API で英単語を読み上げるボタン。MP3は生成しません。"""
    word_text = str(word or "").strip()
    if not word_text:
        return

    # JavaScript文字列として安全に渡す
    word_js = json.dumps(word_text, ensure_ascii=False)
    label_html = html.escape(label)
    components.html(
        f"""
        <button id="speak-{key}" class="speak-btn" type="button" aria-label="Speak {html.escape(word_text)}">{label_html}</button>
        <script>
        const btn = document.getElementById("speak-{key}");
        btn.addEventListener("click", function() {{
            const text = {word_js};
            if (!("speechSynthesis" in window)) {{
                alert("このブラウザは音声読み上げに対応していません。");
                return;
            }}
            window.speechSynthesis.cancel();
            const u = new SpeechSynthesisUtterance(text);
            u.lang = "en-US";
            u.rate = 0.82;
            u.pitch = 1.0;
            u.volume = 1.0;

            const voices = window.speechSynthesis.getVoices();
            const enVoice = voices.find(v => v.lang === "en-US") || voices.find(v => v.lang && v.lang.startsWith("en"));
            if (enVoice) u.voice = enVoice;
            window.speechSynthesis.speak(u);
        }});
        </script>
        <style>
        html, body {{ margin: 0; padding: 0; background: transparent; overflow: hidden; }}
        .speak-btn {{
            width: 100%;
            height: {max(28, int(height) - 4)}px;
            min-height: 28px;
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,.45);
            background: transparent;
            color: #eef4ff;
            font-size: 16px;
            font-weight: 800;
            cursor: pointer;
            line-height: 1;
        }}
        .speak-btn:hover {{ background: rgba(255,255,255,.08); color: #ffffff; }}
        .speak-btn:active {{ transform: scale(.96); }}
        </style>
        """,
        height=height,
    )

def passitan_page():
    st.subheader("📗 パス単")
    st.caption("英検準1級・英検1級を切り替えて学習できます。スマホではカード表示、PCでは表表示を選べます。🔊ボタンでブラウザ音声読み上げができます。")

    passitan_all_df = load_passitan_words()

    if passitan_all_df.empty:
        st.warning("パス単データがDBに入っていません。CSVをアップロードして取り込んでください。")
        uploaded = st.file_uploader("パス単CSVをアップロード", type=["csv"])
        if uploaded is not None:
            ok, msg = import_passitan_csv_to_db(uploaded)
            st.success(msg) if ok else st.error(msg)
            if ok:
                st.rerun()
        return

    passitan_all_df = passitan_all_df.copy()
    passitan_all_df["grade_label"] = passitan_all_df["source"].apply(passitan_grade_label)
    passitan_all_df["display_no"] = passitan_all_df.apply(passitan_display_no, axis=1)

    preferred = ["英検準1級", "英検1級"]
    existing_labels = passitan_all_df["grade_label"].dropna().astype(str).unique().tolist()
    grade_options = [x for x in preferred if x in existing_labels] + [x for x in existing_labels if x not in preferred]

    progress = load_user_progress("passitan", {})
    set_session_default_from_progress("passitan_grade_select", progress.get("selected_grade"), grade_options)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    selected_grade = st.selectbox("教材を選択", grade_options, index=0, key="passitan_grade_select")
    st.caption("前回の教材・Section・開始No・表示形式を自動で復元します。")
    st.markdown('</div>', unsafe_allow_html=True)

    passitan_df = passitan_all_df[passitan_all_df["grade_label"] == selected_grade].copy()
    if passitan_df.empty:
        st.warning(f"{selected_grade} のデータがDBにありません。")
        return

    total = len(passitan_df)
    known_count = int(passitan_df["known"].fillna(0).astype(int).sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("選択中", selected_grade)
    c2.metric("登録単語数", total)
    c3.metric("わかった単語", known_count)
    c4.metric("未チェック", total - known_count)

    source_names = " / ".join(passitan_df["source"].dropna().astype(str).unique().tolist())
    st.caption(f"現在のsource: {source_names}")

    grade_slug = passitan_key_slug(selected_grade)

    st.markdown('<div class="card">', unsafe_allow_html=True)

    max_passitan_no = max(1, int(passitan_df["display_no"].max()))
    is_pre1_passitan = selected_grade == "英検準1級"
    start_no = 1
    end_no = max_passitan_no
    display_n = 100 if is_pre1_passitan else 50
    section_key = f"passitan_section_{grade_slug}"
    start_key = f"passitan_start_no_{grade_slug}"
    display_n_key = f"display_n_{grade_slug}"
    keyword_key = f"passitan_keyword_{grade_slug}"
    hide_known_key = f"hide_known_{grade_slug}"
    view_mode_key = f"view_mode_{grade_slug}"

    set_session_default_from_progress(display_n_key, progress.get("display_n"), [10, 20, 50])
    set_session_default_from_progress(keyword_key, progress.get("keyword"))
    set_session_default_from_progress(hide_known_key, progress.get("hide_known"), [True, False])
    set_session_default_from_progress(view_mode_key, progress.get("view_mode"), ["スマホカード", "PC表"])
    try:
        saved_start_no = int(progress.get("start_no"))
    except Exception:
        saved_start_no = None
    if saved_start_no is not None:
        set_session_default_from_progress(start_key, saved_start_no)

    if is_pre1_passitan:
        sections = build_passitan_sections(max_passitan_no, section_size=100, fixed_count=19)
        valid_section_labels = [sec["label"] for sec in sections]
        set_session_default_from_progress(section_key, progress.get("section_label"), valid_section_labels)
        if section_key not in st.session_state:
            st.session_state[section_key] = sections[0]["label"]
        if st.session_state[section_key] not in valid_section_labels:
            st.session_state[section_key] = valid_section_labels[0]

        col_a, col_b, col_c, col_d = st.columns([1.4, 2, 1, 1.2])
        with col_a:
            selected_section_label = st.selectbox(
                "Sectionを選択",
                valid_section_labels,
                key=section_key,
            )
        selected_section = next(sec for sec in sections if sec["label"] == selected_section_label)
        start_no = int(selected_section["start"])
        end_no = int(selected_section["end"])
        with col_b:
            keyword = st.text_input("検索", placeholder="例: affect / 影響", key=keyword_key)
        with col_c:
            hide_known = st.checkbox("わかった単語を隠す", value=False, key=hide_known_key)
        with col_d:
            view_mode = st.radio(
                "表示形式",
                ["スマホカード", "PC表"],
                index=0,
                horizontal=False,
                key=view_mode_key,
                help="携帯電話では『スマホカード』を使うと表崩れを防げます。",
            )
        st.info(f"{selected_section_label} を表示します。範囲: No.{start_no}〜No.{end_no}（100語）")
    else:
        col_a, col_b, col_c, col_d, col_e = st.columns([1, 1, 2, 1, 1.2])
        with col_a:
            display_n = st.selectbox("表示件数", [10, 20, 50], index=2, key=display_n_key)
        with col_b:
            if start_key not in st.session_state:
                st.session_state[start_key] = 1
            st.session_state[start_key] = min(
                max(1, int(st.session_state[start_key])),
                max_passitan_no,
            )
            start_no = st.number_input(
                "開始No",
                min_value=1,
                max_value=max_passitan_no,
                step=int(display_n),
                key=start_key,
            )
        with col_c:
            keyword = st.text_input("検索", placeholder="例: affect / 影響", key=keyword_key)
        with col_d:
            hide_known = st.checkbox("わかった単語を隠す", value=False, key=hide_known_key)
        with col_e:
            view_mode = st.radio(
                "表示形式",
                ["スマホカード", "PC表"],
                index=0,
                horizontal=False,
                key=view_mode_key,
                help="携帯電話では『スマホカード』を使うと表崩れを防げます。",
            )
    save_user_progress("passitan", {
        "selected_grade": selected_grade,
        "section_label": selected_section_label if is_pre1_passitan else "",
        "start_no": int(start_no),
        "end_no": int(end_no),
        "display_n": int(display_n) if not is_pre1_passitan else 100,
        "keyword": keyword,
        "hide_known": bool(hide_known),
        "view_mode": view_mode,
    })
    st.markdown('</div>', unsafe_allow_html=True)

    view = passitan_df.copy()
    if keyword:
        k = keyword.lower().strip()
        view = view[
            view["word"].astype(str).str.lower().str.contains(k, na=False)
            | view["meaning"].astype(str).str.lower().str.contains(k, na=False)
            | view["example_sentence"].astype(str).str.lower().str.contains(k, na=False)
        ]
    elif is_pre1_passitan:
        view = view[(view["display_no"] >= int(start_no)) & (view["display_no"] <= int(end_no))]
    else:
        view = view[view["display_no"] >= int(start_no)]
    if hide_known:
        view = view[view["known"].fillna(0).astype(int) == 0]
    view = view.sort_values("display_no")
    if not is_pre1_passitan:
        view = view.head(display_n)

    # 現在表示中の範囲を学習記録に保存します。
    range_total = int(len(view))
    range_known = int(view["known"].fillna(0).astype(int).sum()) if not view.empty else 0
    progress_title = f"{selected_grade} {selected_section_label if is_pre1_passitan else f'No.{int(start_no)}〜'}"
    save_study_progress(
        area="パス単",
        item_key=f"{selected_grade}_{int(start_no)}_{int(end_no) if is_pre1_passitan else int(start_no) + int(display_n) - 1}",
        title=progress_title,
        unit=selected_grade,
        section_no=selected_section_label if is_pre1_passitan else str(start_no),
        total_count=range_total,
        completed_count=range_known,
        status="完了" if range_total and range_known >= range_total else "学習中",
        payload={"start_no": int(start_no), "end_no": int(end_no) if is_pre1_passitan else int(start_no) + int(display_n) - 1},
    )

    st.download_button(
        f"{selected_grade} CSVをダウンロード",
        passitan_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"passitan_words_{grade_slug}.csv",
        mime="text/csv",
    )

    st.markdown(
        """
        <style>
        .passitan-card {
            padding: 12px 14px;
            border-radius: 16px;
            background: rgba(255,255,255,.045);
            border: 1px solid rgba(255,255,255,.18);
            margin: 0 0 10px 0;
        }
        .passitan-card-top {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 6px;
        }
        .passitan-card-no {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 38px;
            height: 24px;
            border-radius: 999px;
            background: rgba(255,255,255,.12);
            color: #dce8fb;
            font-size: 12px;
            font-weight: 850;
            flex: 0 0 auto;
        }
        .passitan-card-word {
            color: #ffffff;
            font-size: 20px;
            font-weight: 850;
            line-height: 1.2;
            overflow-wrap: anywhere;
        }
        .passitan-card-speak {
            margin-left: auto;
            width: 48px;
            flex: 0 0 48px;
        }
        .passitan-card-meaning {
            color: #b7ffcf;
            font-size: 13px;
            line-height: 1.35;
            margin: 0 0 6px 0;
        }
        .passitan-card-example {
            color: #d7e2f5;
            font-size: 20px !important;
            line-height: 1.45;
            margin: 0;
            overflow-wrap: anywhere;
        }
        .passitan-table-header,
        .passitan-cell {
            box-sizing: border-box;
            min-height: 34px;
            padding: 4px 6px;
            margin: 0;
            display: flex;
            align-items: center;
            overflow: hidden;
            border-left: 1px solid rgba(255,255,255,.24);
            border-bottom: 1px solid rgba(255,255,255,.20);
            border-radius: 0;
        }
        .passitan-table-header {
            background: rgba(255,255,255,.16);
            border-top: 1px solid rgba(255,255,255,.40);
            font-weight: 850;
            color: #eef4ff;
        }
        .passitan-cell { background: rgba(255,255,255,.035); }
        .passitan-cell-center { justify-content: center; text-align: center; }
        .passitan-word {
            display: inline-block;
            font-size: 16px;
            font-weight: 850;
            color: #fff;
            max-width: 100%;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            cursor: help;
        }
        .passitan-example {
            width: 100%;
            color: #d7e2f5;
            font-size: 30px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        div[data-testid="stHorizontalBlock"]:has(.passitan-table-row) { gap: 0 !important; }
        div[data-testid="stHorizontalBlock"]:has(.passitan-table-row) > div[data-testid="column"] { padding: 0 !important; }
        div[data-testid="stHorizontalBlock"]:has(.passitan-table-row) div[data-testid="element-container"] { margin: 0 !important; padding: 0 !important; }
        div[data-testid="stHorizontalBlock"]:has(.passitan-table-row) div[data-testid="stCheckbox"] { display:flex !important; justify-content:center !important; align-items:center !important; min-height:34px !important; }
        div[data-testid="stHorizontalBlock"]:has(.passitan-table-row) div[data-testid="stCheckbox"] label { justify-content:center !important; width:100% !important; }
        div[data-testid="stHorizontalBlock"]:has(.passitan-table-row) div[data-testid="stCheckbox"] p { display:none !important; }
        div[data-testid="stHorizontalBlock"]:has(.passitan-table-row) div[data-testid="stCheckbox"] input,
        div[data-testid="stHorizontalBlock"]:has(.passitan-table-row) div[data-testid="stCheckbox"] svg,
        div[data-testid="stHorizontalBlock"]:has(.passitan-table-row) div[data-testid="stCheckbox"] [role="checkbox"] {
            transform: scale(1.35) !important;
            transform-origin: center center !important;
        }
        div[data-testid="stHorizontalBlock"]:has(.passitan-table-row) div[data-testid="stButton"] { display:flex !important; justify-content:center !important; align-items:center !important; min-height:34px !important; }
        div[data-testid="stHorizontalBlock"]:has(.passitan-table-row) div[data-testid="stButton"] > button {
            width: 58px !important;
            min-width: 58px !important;
            height: 26px !important;
            min-height: 26px !important;
            padding: 0 6px !important;
            border-radius: 6px !important;
            font-size: 12px !important;
            background: transparent !important;
            background-image: none !important;
            color: #eef4ff !important;
            border: 1px solid rgba(255,255,255,.45) !important;
            box-shadow: none !important;
        }
        .passitan-next-wrap {
            position: fixed;
            right: 24px;
            bottom: 24px;
            z-index: 9999;
            background: rgba(8,17,31,.78);
            border: 1px solid rgba(255,255,255,.16);
            border-radius: 16px;
            padding: 8px;
            box-shadow: 0 16px 40px rgba(0,0,0,.35);
        }
        @media (max-width: 768px) {
            .hero h1 { font-size: 30px; }
            .card { padding: 14px; border-radius: 18px; }
            .passitan-card { padding: 12px; border-radius: 14px; }
            .passitan-card-word { font-size: 19px; }
            .passitan-card-example { font-size: 30px; }
            .passitan-next-wrap { right: 12px; bottom: 12px; padding: 6px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if view.empty:
        st.info("表示する単語がありません。")
        return

    if view_mode == "スマホカード":
        for _, row in view.iterrows():
            row_id = int(row["id"])
            no = int(row.get("display_no", row["no"]))
            word = str(row.get("word", ""))
            meaning = str(row.get("meaning", ""))
            example = str(row.get("example_sentence", ""))
            is_known = bool(int(row.get("known") or 0))

            safe_word = html.escape(word)
            safe_meaning = html.escape(meaning)

            # hint_example = make_example_with_word_hint(example, word, hint_len=2)
            safe_example = html.escape(example)

            st.markdown(
                f"""
                <div class="passitan-card">
                  <div class="passitan-card-top">
                    <span class="passitan-card-no">{no}</span>
                    <span class="passitan-card-word" title="{safe_meaning}">{safe_word}</span>
                  </div>
                  <p class="passitan-card-meaning">{safe_meaning}</p>
                  <p class="passitan-card-example">{safe_example}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            a0, a1, a2 = st.columns([0.8, 1, 1])
            with a0:
                render_browser_speak_button(word, key=f"card_{row_id}", label="🔊", height=36)
            with a1:
                checked = st.checkbox(
                    "Known",
                    value=is_known,
                    key=f"known_card_{row_id}",
                )
                if checked != is_known:
                    update_passitan_known(row_id, checked)
                    st.rerun()
            with a2:
                if st.button("登録", key=f"add_passitan_vocab_card_{row_id}", use_container_width=True):
                    ok, msg = add_vocab_word(
                        word,
                        meaning=meaning,
                        japanese_translation=meaning,
                        explanation=f"{selected_grade} パス単から登録",
                        example_sentence=example,
                        note="パス単リストから登録",
                    )
                    st.success(msg) if ok else st.error(msg)
    else:
        h_no, h_word, h_speak, h_example, h_known, h_add = st.columns([0.38, 1.45, 0.56, 5.5, 0.78, 0.86], gap=None)
        h_no.markdown('<div class="passitan-table-header passitan-cell-center passitan-table-row">No.</div>', unsafe_allow_html=True)
        h_word.markdown('<div class="passitan-table-header passitan-table-row">英単語</div>', unsafe_allow_html=True)
        h_speak.markdown('<div class="passitan-table-header passitan-cell-center passitan-table-row">音声</div>', unsafe_allow_html=True)
        h_example.markdown('<div class="passitan-table-header passitan-table-row">例文</div>', unsafe_allow_html=True)
        h_known.markdown('<div class="passitan-table-header passitan-cell-center passitan-table-row">Known</div>', unsafe_allow_html=True)
        h_add.markdown('<div class="passitan-table-header passitan-cell-center passitan-table-row">単語帳</div>', unsafe_allow_html=True)

        for _, row in view.iterrows():
            row_id = int(row["id"])
            no = int(row.get("display_no", row["no"]))
            word = str(row.get("word", ""))
            meaning = str(row.get("meaning", ""))
            example = str(row.get("example_sentence", ""))
            is_known = bool(int(row.get("known") or 0))

            safe_word = html.escape(word)
            safe_meaning = html.escape(meaning)

            hint_example = make_example_with_word_hint(example, word, hint_len=2)
            safe_example = html.escape(hint_example)

            c_no, c_word, c_speak, c_example, c_known, c_add = st.columns([0.38, 1.45, 0.56, 5.5, 0.78, 0.86], gap=None)
            with c_no:
                st.markdown(f'<div class="passitan-cell passitan-cell-center passitan-table-row"><b>{no}</b></div>', unsafe_allow_html=True)
            with c_word:
                st.markdown(f'<div class="passitan-cell passitan-table-row"><span class="passitan-word" title="{safe_meaning}">{safe_word}</span></div>', unsafe_allow_html=True)
            with c_speak:
                st.markdown('<div class="passitan-table-row"></div>', unsafe_allow_html=True)
                render_browser_speak_button(word, key=f"table_{row_id}", label="🔊", height=34)
            with c_example:
                st.markdown(f'<div class="passitan-cell passitan-table-row"><div class="passitan-example">{safe_example}</div></div>', unsafe_allow_html=True)
            with c_known:
                checked = st.checkbox(
                    " ",
                    value=is_known,
                    key=f"known_table_{row_id}",
                    label_visibility="collapsed",
                )
                if checked != is_known:
                    update_passitan_known(row_id, checked)
                    st.rerun()
            with c_add:
                if st.button("登録", key=f"add_passitan_vocab_table_{row_id}"):
                    ok, msg = add_vocab_word(
                        word,
                        meaning=meaning,
                        japanese_translation=meaning,
                        explanation=f"{selected_grade} パス単から登録",
                        example_sentence=example,
                        note="パス単リストから登録",
                    )
                    st.success(msg) if ok else st.error(msg)

    max_no = int(passitan_df["display_no"].max())

    if is_pre1_passitan:
        sections = build_passitan_sections(max_no, section_size=100, fixed_count=19)
        current_idx = next((i for i, sec in enumerate(sections) if sec["start"] == int(start_no)), 0)

        def go_next_passitan_section():
            if current_idx + 1 < len(sections):
                st.session_state[section_key] = sections[current_idx + 1]["label"]

        if not keyword and current_idx + 1 < len(sections):
            st.markdown('<div class="passitan-next-wrap">', unsafe_allow_html=True)
            st.button("Next Section", key=f"passitan_next_section_bottom_{grade_slug}", on_click=go_next_passitan_section)
            st.markdown('</div>', unsafe_allow_html=True)
    else:
        next_start = int(start_no) + int(display_n)

        def go_next_passitan():
            st.session_state[start_key] = min(next_start, max_no)

        if not keyword and next_start <= max_no:
            st.markdown('<div class="passitan-next-wrap">', unsafe_allow_html=True)
            st.button("Next", key=f"passitan_next_bottom_{grade_slug}", on_click=go_next_passitan)
            st.markdown('</div>', unsafe_allow_html=True)


def make_example_with_word_hint(example, word, hint_len=2):
    """
    例文中の英単語を、頭文字だけ残して残りを ____ にする。
    例: abandon -> ab____
    """
    import re

    example = str(example or "")
    word = str(word or "").strip()

    if not example or not word:
        return example

    hint = word[:hint_len]
    # hidden = hint + "____"
    rest_len = max(len(word) - hint_len, 0)

    # 大文字小文字を無視して、単語単位で置換
    pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)

    underscores = "&thinsp;".join(["_"] * rest_len)
    hidden = f"{hint}&thinsp;{underscores}" if underscores else hint

    # 例文に単語がある場合だけ置換
    if pattern.search(example):
        return pattern.sub(hidden, example)

    # 例文に単語が見つからない場合は、例文の後ろにヒントを付ける
    return f"{example}  ({hidden})"

def normalize_typed_answer(text_value):
    """タイピング回答の比較用に、大小文字・前後空白・連続スペースを吸収します。"""
    return " ".join(str(text_value or "").strip().lower().split())


def split_word_prefix(word, prefix_len=2):
    """テスト用に、英単語の頭文字だけをヒントとして分離します。"""
    word = str(word or "").strip()
    if not word:
        return "", ""
    prefix_len = min(int(prefix_len), len(word))
    return word[:prefix_len], word[prefix_len:]


def build_typed_full_answer(prefix, rest_text):
    """頭文字ヒント + タイピングした残り部分を結合して採点用の回答にします。"""
    return f"{str(prefix or '')}{str(rest_text or '').strip()}"


def blank_word_in_example(example, word, hint_len=2):
    import re

    example = str(example or "")
    word = str(word or "").strip()

    if not example or not word:
        return example

    hint = word[:hint_len]
    rest_len = max(len(word) - hint_len, 0)

    # 狭い隙間：&thinsp; を使う
    underscores = "&thinsp;".join(["_"] * rest_len)
    hidden = f"{hint}&thinsp;{underscores}" if underscores else hint

    pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)

    if pattern.search(example):
        return pattern.sub(hidden, example)

    return f"{example}  ({hidden})"

def build_passitan_test_scope_options(passitan_df, selected_grade):
    """パス単テスト用のSection選択肢を作ります。準1級はSection 1〜19 + All sections。"""
    max_no = max(1, int(passitan_df["display_no"].max()))
    if selected_grade == "英検準1級":
        sections = build_passitan_sections(max_no, section_size=100, fixed_count=19)
    else:
        sections = build_passitan_sections(max_no, section_size=100, fixed_count=None)

    options = [{"label": f"All sections: 1〜{max_no}", "start": 1, "end": max_no, "is_all": True}]
    for sec in sections:
        options.append({"label": sec["label"], "start": sec["start"], "end": sec["end"], "is_all": False})
    return options




def play_well_done_voice(text="Well Done!!"):
    """ブラウザ標準の Web Speech API で Well Done!! を自動読み上げします。"""
    text_js = json.dumps(str(text or "Well Done!!"), ensure_ascii=False)
    components.html(
        f"""
        <script>
        (function() {{
            const text = {text_js};
            if (!("speechSynthesis" in window)) return;
            window.speechSynthesis.cancel();
            const u = new SpeechSynthesisUtterance(text);
            u.lang = "en-US";
            u.rate = 0.85;
            u.pitch = 1.15;
            u.volume = 1.0;
            const setVoiceAndSpeak = function() {{
                const voices = window.speechSynthesis.getVoices();
                const enVoice = voices.find(v => v.lang === "en-US") || voices.find(v => v.lang && v.lang.startsWith("en"));
                if (enVoice) u.voice = enVoice;
                window.speechSynthesis.speak(u);
            }};
            if (window.speechSynthesis.getVoices().length === 0) {{
                window.speechSynthesis.onvoiceschanged = setVoiceAndSpeak;
                setTimeout(setVoiceAndSpeak, 300);
            }} else {{
                setVoiceAndSpeak();
            }}
        }})();
        </script>
        """,
        height=0,
    )

def passitan_test_page():
    st.subheader("🧪 パス単テスト")
    st.caption("日本語の意味を非表示にして、音声または例文ヒントを使いながら、頭文字2文字以外の残りをタイピングします。最後にまとめてチェックできます。")

    passitan_all_df = load_passitan_words()
    if passitan_all_df.empty:
        st.warning("パス単データがDBに入っていません。まず『📗 パス単』画面でCSVをアップロードしてください。")
        return

    passitan_all_df = passitan_all_df.copy()
    passitan_all_df["grade_label"] = passitan_all_df["source"].apply(passitan_grade_label)
    passitan_all_df["display_no"] = passitan_all_df.apply(passitan_display_no, axis=1)

    preferred = ["英検準1級", "英検1級"]
    existing_labels = passitan_all_df["grade_label"].dropna().astype(str).unique().tolist()
    grade_options = [x for x in preferred if x in existing_labels] + [x for x in existing_labels if x not in preferred]

    progress = load_user_progress("passitan_test", {})
    set_session_default_from_progress("passitan_test_grade", progress.get("selected_grade"), grade_options)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.caption("前回の教材・出題範囲・出題数・順番を自動で復元します。")
    c_grade, c_scope, c_count, c_mode = st.columns([1.2, 2.0, 1.2, 1.2])
    with c_grade:
        selected_grade = st.selectbox("教材を選択", grade_options, index=0, key="passitan_test_grade")

    passitan_df = passitan_all_df[passitan_all_df["grade_label"] == selected_grade].copy()
    if passitan_df.empty:
        st.warning(f"{selected_grade} のデータがDBにありません。")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    scope_options = build_passitan_test_scope_options(passitan_df, selected_grade)
    scope_labels = [opt["label"] for opt in scope_options]
    grade_slug = passitan_key_slug(selected_grade)
    scope_key = f"passitan_test_scope_{grade_slug}"
    count_key = f"passitan_test_count_{grade_slug}"
    order_key = f"passitan_test_order_{grade_slug}"
    audio_key = f"passitan_test_audio_{grade_slug}"
    hint_key = f"passitan_test_hint_{grade_slug}"
    hide_known_key = f"passitan_test_hide_known_{grade_slug}"
    set_session_default_from_progress(scope_key, progress.get("scope_label"), scope_labels)
    set_session_default_from_progress(count_key, progress.get("selected_count"), ["10問", "20問", "50問", "100問", "選択範囲すべて"])
    set_session_default_from_progress(order_key, progress.get("order_mode"), ["順番通り", "シャッフル"])
    set_session_default_from_progress(audio_key, progress.get("show_audio"), [True, False])
    set_session_default_from_progress(hint_key, progress.get("show_example_hint"), [True, False])
    set_session_default_from_progress(hide_known_key, progress.get("hide_known"), [True, False])
    with c_scope:
        selected_scope_label = st.selectbox("出題範囲", scope_labels, index=1 if len(scope_labels) > 1 else 0, key=scope_key)
    selected_scope = next(opt for opt in scope_options if opt["label"] == selected_scope_label)

    scoped_df = passitan_df[
        (passitan_df["display_no"] >= int(selected_scope["start"]))
        & (passitan_df["display_no"] <= int(selected_scope["end"]))
    ].sort_values("display_no").copy()

    with c_count:
        count_options = ["10問", "20問", "50問", "100問", "選択範囲すべて"]
        selected_count = st.selectbox("出題数", count_options, index=1, key=count_key)
    with c_mode:
        order_mode = st.radio("順番", ["順番通り", "シャッフル"], index=0, key=order_key)

    c_audio, c_hint, c_known = st.columns([1, 1.2, 1.2])
    with c_audio:
        show_audio = st.checkbox("音声ボタンを表示", value=True, key=audio_key)
    with c_hint:
        show_example_hint = st.checkbox("例文ヒントを表示（日本語なし）", value=True, key=hint_key)
    with c_known:
        hide_known = st.checkbox("Knownを除外", value=False, key=hide_known_key)
    save_user_progress("passitan_test", {
        "selected_grade": selected_grade,
        "scope_label": selected_scope_label,
        "selected_count": selected_count,
        "order_mode": order_mode,
        "show_audio": bool(show_audio),
        "show_example_hint": bool(show_example_hint),
        "hide_known": bool(hide_known),
    })
    st.markdown('</div>', unsafe_allow_html=True)

    if hide_known:
        scoped_df = scoped_df[scoped_df["known"].fillna(0).astype(int) == 0]

    if scoped_df.empty:
        st.info("この条件で出題できる単語がありません。")
        return

    if selected_count == "選択範囲すべて":
        test_n = len(scoped_df)
    else:
        test_n = min(int(selected_count.replace("問", "")), len(scoped_df))

    test_key_base = f"passitan_test_{passitan_key_slug(selected_grade)}_{selected_scope['start']}_{selected_scope['end']}_{test_n}_{order_mode}_{hide_known}"
    if order_mode == "シャッフル":
        seed_key = f"{test_key_base}_seed"
        if seed_key not in st.session_state:
            st.session_state[seed_key] = random.randint(1, 10_000_000)
        test_df = scoped_df.sample(n=test_n, random_state=int(st.session_state[seed_key])).copy()
    else:
        test_df = scoped_df.head(test_n).copy()

    st.info(f"出題範囲: {selected_scope_label} / 出題数: {len(test_df)}問。日本語の意味はチェック後に表示します。")

    st.markdown(
        """
        <style>
        .passitan-test-card {
            padding: 12px 14px;
            border-radius: 16px;
            background: rgba(255,255,255,.045);
            border: 1px solid rgba(255,255,255,.18);
            margin: 0 0 10px 0;
        }
        .passitan-test-no {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 999px;
            background: rgba(255,255,255,.13);
            color: #dce8fb;
            font-size: 12px;
            font-weight: 850;
            margin-bottom: 6px;
        }
        .passitan-test-example {
            color: #d7e2f5;
            font-size: 24px !important;
            line-height: 2.55;
            overflow-wrap: anywhere;
            margin: 8px 0 12px 0;
            font-weight: 750;
        }
        .passitan-test-prefix {
            min-height: 25px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 12px;
            background: rgba(79,172,254,.18);
            border: 1px solid rgba(79,172,254,.35);
            color: #ffffff;
            font-size: 22px;
            font-weight: 900;
            letter-spacing: .04em;
        }
        .passitan-test-result-ok { color: #b7ffcf; font-weight: 850; }
        .passitan-test-result-ng { color: #ffb7b7; font-weight: 850; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    answers = {}
    rows = list(test_df.iterrows())
    for idx, (_, row) in enumerate(rows, start=1):
        row_id = int(row["id"])
        no = int(row.get("display_no", row.get("no", 0)))
        word = str(row.get("word", ""))
        prefix_hint, _rest_hint = split_word_prefix(word, prefix_len=2)
        example = str(row.get("example_sentence", ""))
        hint_text = make_example_with_word_hint(example, word, hint_len=2) if show_example_hint else ""

        st.markdown('<div class="passitan-test-card">', unsafe_allow_html=True)
        st.markdown(f'<span class="passitan-test-no">Q{idx} / No.{no}</span>', unsafe_allow_html=True)
        if hint_text:
            # st.markdown(f'<p class="passitan-test-example">{html.escape(hint_text)}</p>', unsafe_allow_html=True)
            st.markdown(f'<p class="passitan-test-example">{hint_text}</p>',unsafe_allow_html=True)

        if show_audio:
            c_speak, c_prefix, c_input = st.columns([0.7, 0.1, 2.0])
            with c_speak:
                render_browser_speak_button(word, key=f"test_{row_id}_{idx}", label="🔊", height=38)
            # with c_prefix:
            #     st.markdown(f'<div class="passitan-test-prefix">{html.escape(prefix_hint)}</div>', unsafe_allow_html=True)
            with c_input:
                answers[row_id] = st.text_input(
                    "残りを入力",
                    key=f"answer_{test_key_base}_{row_id}",
                    label_visibility="collapsed",
                    placeholder="3文字目以降を入力",
                )
        else:
            c_prefix, c_input = st.columns([0.1, 2.0])
            # with c_prefix:
            #     st.markdown(f'<div class="passitan-test-prefix">{html.escape(prefix_hint)}</div>', unsafe_allow_html=True)
            with c_input:
                answers[row_id] = st.text_input(
                    "残りを入力",
                    key=f"answer_{test_key_base}_{row_id}",
                    label_visibility="collapsed",
                    placeholder="3文字目以降を入力",
                )
        st.markdown('</div>', unsafe_allow_html=True)

    c_check, c_shuffle = st.columns([1, 1])
    with c_check:
        checked = st.button("✅ 最後にチェックする", type="primary", key=f"check_{test_key_base}")
    with c_shuffle:
        if order_mode == "シャッフル" and st.button("🔄 シャッフルを更新", key=f"reshuffle_{test_key_base}"):
            st.session_state[f"{test_key_base}_seed"] = random.randint(1, 10_000_000)
            st.rerun()

    if checked:
        correct_count = 0
        result_rows = []
        for idx, (_, row) in enumerate(rows, start=1):
            row_id = int(row["id"])
            no = int(row.get("display_no", row.get("no", 0)))
            correct_word = str(row.get("word", ""))
            prefix_hint, _rest_hint = split_word_prefix(correct_word, prefix_len=2)
            typed_rest = answers.get(row_id, "")
            typed_full = build_typed_full_answer(prefix_hint, typed_rest)
            ok = normalize_typed_answer(typed_full) == normalize_typed_answer(correct_word)
            if ok:
                correct_count += 1
            result_rows.append({
                "No": no,
                "結果": "○" if ok else "×",
                "入力": typed_full,
                "正解": correct_word,
                "意味": str(row.get("meaning", "")),
                "例文": str(row.get("example_sentence", "")),
            })

        score_rate = correct_count / max(1, len(result_rows)) * 100
        save_study_progress(
            area="パス単テスト",
            item_key=f"{selected_grade}_{selected_scope_label}",
            title=f"{selected_grade} / {selected_scope_label}",
            unit=selected_grade,
            section_no=selected_scope_label,
            total_count=len(result_rows),
            completed_count=correct_count,
            score_rate=score_rate,
            status="合格" if score_rate >= 80 else "復習必要",
            payload={"order_mode": order_mode, "selected_count": selected_count},
        )
        add_study_event(
            area="パス単テスト",
            event_type="check",
            title=f"{selected_grade} / {selected_scope_label}",
            total_count=len(result_rows),
            completed_count=correct_count,
            score_rate=score_rate,
            payload={"selected_count": selected_count},
        )
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(f"### 結果: {correct_count} / {len(result_rows)} 問正解（{score_rate:.1f}%）")
        if correct_count == len(result_rows):
            st.balloons()
            play_well_done_voice("Well Done!!")
            st.success("全問正解です！ Well Done!!")
        elif score_rate >= 80:
            st.balloons()
            play_well_done_voice("Well Done!!")
            st.success("かなり良いです。80%以上正解です。Well Done!! 間違えた単語だけ復習しましょう。")
        else:
            st.warning("間違えた単語を確認して、もう一度テストしましょう。")
        st.dataframe(pd.DataFrame(result_rows), use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

def add_page():
    st.subheader("➕ 問題を追加")
    st.caption("今後の問題はここから直接データベースへ追加できます。")
    with st.form("add_question", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        year = c1.text_input("Year", "2025")
        session = c2.text_input("Session", "4")
        grade = c3.text_input("Grade", "Pre-1")
        qno = c4.number_input("Q No.", min_value=1, step=1)
        question = st.text_area("英文問題", height=100, placeholder="The sentence has a _____ blank.")
        translation = st.text_area("日本語訳", height=90)
        c1, c2, c3, c4 = st.columns(4)
        choices = [
            c1.text_input("1"),
            c2.text_input("2"),
            c3.text_input("3"),
            c4.text_input("4"),
        ]
        answer = st.selectbox("正解番号", [1, 2, 3, 4])
        explanation = st.text_area("解説", height=90)
        choice_notes_text = st.text_area("選択肢解析（1行1つ）", height=110, placeholder="remote=遠い、人里離れた")
        synonyms = st.text_input("類義語", placeholder="distant, isolated, faraway")
        difficulty = st.selectbox("難易度", ["易しい", "標準", "難しい"])
        tags = st.text_input("タグ", "語彙,英検準1級")
        submitted = st.form_submit_button("登録する")
        if submitted:
            if not question or not all(choices):
                st.error("英文問題と4つの選択肢を入力してください。")
            else:
                try:
                    notes = [x.strip() for x in choice_notes_text.splitlines() if x.strip()]
                    add_question((
                        year, session, grade, int(qno), question, translation,
                        json.dumps(choices, ensure_ascii=False), int(answer), explanation,
                        json.dumps(notes, ensure_ascii=False), synonyms, difficulty, tags,
                    ))
                    st.success("登録しました。")
                except sqlite3.IntegrityError:
                    st.error("同じ Year / Session / Grade / Q No. がすでに存在します。")



def special_lesson_page():
    st.subheader("🌟 special-lesson")
    st.caption("english_exercises_answers_jp.db の questions テーブルから、穴埋め・文法・語形変化の問題を作成します。各問題ごとに Confirm を押すと、翻訳と解説を表示します。")

    lesson_df, err = load_special_lesson_questions()
    if err:
        st.warning(err)
    if lesson_df.empty:
        return

    progress = load_user_progress("special_lesson", {})
    unit_options = ["すべて"] + sorted(lesson_df["unit"].dropna().unique().tolist())
    qtype_options = ["すべて"] + sorted(lesson_df["qtype"].dropna().unique().tolist())
    count_options = ["5問", "10問", "20問", "すべて"]
    order_options = ["順番通り", "シャッフル"]
    set_session_default_from_progress("special_lesson_unit", progress.get("selected_unit"), unit_options)
    set_session_default_from_progress("special_lesson_qtype", progress.get("selected_qtype"), qtype_options)
    set_session_default_from_progress("special_lesson_count", progress.get("count_label"), count_options)
    set_session_default_from_progress("special_lesson_order", progress.get("order_mode"), order_options)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.caption("前回のUnit・問題タイプ・出題数・順番を自動で復元します。")
    c_unit, c_type, c_count, c_order = st.columns([2.0, 1.3, 1.0, 1.1])
    with c_unit:
        selected_unit = st.selectbox("Unit", unit_options, index=0, key="special_lesson_unit")
    with c_type:
        selected_qtype = st.selectbox("問題タイプ", qtype_options, index=0, key="special_lesson_qtype")
    with c_count:
        count_label = st.selectbox("出題数", count_options, index=1, key="special_lesson_count")
    with c_order:
        order_mode = st.radio("順番", order_options, index=0, key="special_lesson_order")
    save_user_progress("special_lesson", {
        "selected_unit": selected_unit,
        "selected_qtype": selected_qtype,
        "count_label": count_label,
        "order_mode": order_mode,
    })
    st.markdown('</div>', unsafe_allow_html=True)

    view = lesson_df.copy()
    if selected_unit != "すべて":
        view = view[view["unit"] == selected_unit]
    if selected_qtype != "すべて":
        view = view[view["qtype"] == selected_qtype]

    if view.empty:
        st.info("この条件で出題できる問題がありません。")
        return

    if count_label == "すべて":
        test_n = len(view)
    else:
        test_n = min(int(count_label.replace("問", "")), len(view))

    special_key_base = f"special_lesson_{selected_unit}_{selected_qtype}_{test_n}_{order_mode}"
    if order_mode == "シャッフル":
        seed_key = f"{special_key_base}_seed"
        if seed_key not in st.session_state:
            st.session_state[seed_key] = random.randint(1, 10_000_000)
        test_df = view.sample(n=test_n, random_state=int(st.session_state[seed_key])).copy()
    else:
        test_df = view.head(test_n).copy()

    st.info(f"出題数: {len(test_df)}問 / Unit: {selected_unit} / Type: {selected_qtype}")

    st.markdown(
        """
        <style>
        .special-lesson-card {
            padding: 14px 16px;
            border-radius: 18px;
            background: rgba(255,255,255,.045);
            border: 1px solid rgba(255,255,255,.18);
            margin: 0 0 12px 0;
        }
        .special-lesson-meta {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            background: rgba(255,255,255,.13);
            color: #dce8fb;
            font-size: 12px;
            font-weight: 850;
            margin-right: 6px;
            margin-bottom: 8px;
        }
        .special-lesson-question {
            color: #ffffff;
            font-size: 22px;
            line-height: 1.75;
            font-weight: 800;
            margin: 8px 0 12px 0;
        }
        .special-lesson-feedback {
            margin-top: 12px;
            padding: 12px 14px;
            border-radius: 14px;
            background: rgba(255,255,255,.055);
            border: 1px solid rgba(255,255,255,.12);
            color: #dce8fb;
            line-height: 1.65;
        }
        .special-lesson-ok { color: #b7ffcf; font-weight: 850; }
        .special-lesson-ng { color: #ffb7b7; font-weight: 850; }
        .special-lesson-label { color: #78c7ff; font-weight: 850; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    answers = {}
    rows = list(test_df.reset_index(drop=True).iterrows())
    for idx, (_, row) in enumerate(rows, start=1):
        unit = str(row.get("unit", ""))
        qtype = str(row.get("qtype", ""))
        no = int(row.get("no", 0))
        question = str(row.get("question", ""))
        correct_answer = str(row.get("answer", ""))
        jp_translation = str(row.get("jp_translation", ""))
        explanation = str(row.get("explanation", ""))
        options = parse_special_options(row.get("options", ""))
        answer_key = f"special_answer_{special_key_base}_{idx}_{unit}_{qtype}_{no}"
        confirm_key = f"special_confirmed_{special_key_base}_{idx}_{unit}_{qtype}_{no}"

        st.markdown('<div class="special-lesson-card">', unsafe_allow_html=True)
        st.markdown(
            f'<span class="special-lesson-meta">Q{idx}</span>'
            f'<span class="special-lesson-meta">{html.escape(unit)}</span>'
            f'<span class="special-lesson-meta">{html.escape(qtype)}</span>'
            f'<span class="special-lesson-meta">No.{no}</span>',
            unsafe_allow_html=True,
        )
        st.markdown(f'<div class="special-lesson-question">{html.escape(question)}</div>', unsafe_allow_html=True)

        if options:
            selected = st.radio(
                "答えを選んでください",
                options,
                index=None,
                key=answer_key,
                horizontal=True,
            )
            answers[idx] = selected or ""
        else:
            answers[idx] = st.text_input(
                "答えを入力してください",
                key=answer_key,
                placeholder="英単語・語形を入力",
            )

        if st.button("Confirm", key=f"special_confirm_btn_{special_key_base}_{idx}_{unit}_{qtype}_{no}"):
            st.session_state[confirm_key] = True

        if st.session_state.get(confirm_key):
            user_answer = str(st.session_state.get(answer_key, "") or "")
            ok = normalize_special_answer(user_answer) == normalize_special_answer(correct_answer)
            result_class = "special-lesson-ok" if ok else "special-lesson-ng"
            result_text = "正解です！" if ok else "不正解です。"
            st.markdown(
                f"""
                <div class="special-lesson-feedback">
                  <div class="{result_class}">{result_text}</div>
                  <div><span class="special-lesson-label">あなたの答え:</span> {html.escape(user_answer or "未入力")}</div>
                  <div><span class="special-lesson-label">正解:</span> {html.escape(correct_answer)}</div>
                  <div><span class="special-lesson-label">日本語訳:</span> {html.escape(jp_translation)}</div>
                  <div><span class="special-lesson-label">解説:</span> {html.escape(explanation)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown('</div>', unsafe_allow_html=True)

    c_check, c_shuffle = st.columns([1, 1])
    with c_check:
        checked = st.button("✅ 全体の答えをチェック", type="primary", key=f"special_check_{special_key_base}")
    with c_shuffle:
        if order_mode == "シャッフル" and st.button("🔄 シャッフルを更新", key=f"special_reshuffle_{special_key_base}"):
            st.session_state[f"{special_key_base}_seed"] = random.randint(1, 10_000_000)
            # シャッフル時は表示済みConfirm状態をクリアします。
            for key in list(st.session_state.keys()):
                if str(key).startswith(f"special_confirmed_{special_key_base}"):
                    st.session_state.pop(key, None)
            st.rerun()

    if checked:
        result_rows = []
        correct_count = 0
        for idx, (_, row) in enumerate(rows, start=1):
            correct_answer = str(row.get("answer", ""))
            user_answer = str(answers.get(idx, ""))
            ok = normalize_special_answer(user_answer) == normalize_special_answer(correct_answer)
            if ok:
                correct_count += 1
            result_rows.append({
                "No": int(row.get("no", 0)),
                "Unit": str(row.get("unit", "")),
                "Type": str(row.get("qtype", "")),
                "結果": "○" if ok else "×",
                "入力": user_answer,
                "正解": correct_answer,
                "日本語訳": str(row.get("jp_translation", "")),
                "解説": str(row.get("explanation", "")),
            })

        score_rate = correct_count / max(1, len(result_rows)) * 100
        save_study_progress(
            area="special-lesson",
            item_key=f"{selected_unit}_{selected_qtype}",
            title=f"Unit: {selected_unit} / Type: {selected_qtype}",
            unit=selected_unit,
            section_no=selected_qtype,
            total_count=len(result_rows),
            completed_count=correct_count,
            score_rate=score_rate,
            status="合格" if score_rate >= 80 else "復習必要",
            payload={"count_label": count_label, "order_mode": order_mode},
        )
        add_study_event(
            area="special-lesson",
            event_type="check",
            title=f"Unit: {selected_unit} / Type: {selected_qtype}",
            total_count=len(result_rows),
            completed_count=correct_count,
            score_rate=score_rate,
            payload={"count_label": count_label},
        )
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(f"### 結果: {correct_count} / {len(result_rows)} 問正解（{score_rate:.1f}%）")
        if score_rate >= 80:
            st.balloons()
            play_well_done_voice("Well Done!!")
            st.success("Well Done!! 80%以上正解です。")
        else:
            st.warning("間違えた問題を確認して、もう一度練習しましょう。")
        st.dataframe(pd.DataFrame(result_rows), use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

def study_records_page():
    st.subheader("📈 学習記録")
    st.caption("ユーザーごとに、前回どこまで学習したか・進捗率・テスト結果を保存して表示します。")

    progress_df = load_study_progress()
    events_df = load_study_events(limit=200)

    if progress_df.empty:
        st.info("まだ学習記録がありません。パス単・パス単テスト・special-lessonを使うと自動で記録されます。")
        return

    progress_df = progress_df.copy()
    progress_df["score_rate"] = pd.to_numeric(progress_df["score_rate"], errors="coerce").fillna(0)
    progress_df["total_count"] = pd.to_numeric(progress_df["total_count"], errors="coerce").fillna(0).astype(int)
    progress_df["completed_count"] = pd.to_numeric(progress_df["completed_count"], errors="coerce").fillna(0).astype(int)

    total_items = int(progress_df["total_count"].sum())
    completed_items = int(progress_df["completed_count"].sum())
    overall_rate = percent_value(completed_items, total_items)
    latest_updated = str(progress_df["updated_at"].max()) if "updated_at" in progress_df.columns else ""

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("全体進捗", f"{overall_rate:.1f}%")
    c2.metric("記録項目", len(progress_df))
    c3.metric("完了/正解", completed_items)
    c4.metric("最終学習", latest_updated[:10])

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### 学習中の場所")
    latest = progress_df.sort_values("updated_at", ascending=False).head(6)
    for _, row in latest.iterrows():
        rate = float(row.get("score_rate") or 0)
        st.progress(min(1.0, max(0.0, rate / 100)))
        st.write(
            f"**{row.get('title','')}**  —  {int(row.get('completed_count') or 0)} / {int(row.get('total_count') or 0)} "
            f"（{rate:.1f}%） / {row.get('status','')} / 更新: {row.get('updated_at','')}"
        )
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### 分野別の進捗")
    area_summary = progress_df.groupby("area", as_index=False).agg(
        total_count=("total_count", "sum"),
        completed_count=("completed_count", "sum"),
        records=("item_key", "count"),
    )
    area_summary["進捗率%"] = area_summary.apply(lambda r: percent_value(r["completed_count"], r["total_count"]), axis=1).round(1)
    st.dataframe(area_summary.rename(columns={"area": "分野", "total_count": "合計", "completed_count": "完了/正解", "records": "記録数"}), use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### 詳細")
    detail = progress_df.rename(columns={
        "area": "分野",
        "title": "内容",
        "unit": "教材/Unit",
        "section_no": "Section/Type",
        "total_count": "合計",
        "completed_count": "完了/正解",
        "score_rate": "進捗率%",
        "status": "状態",
        "updated_at": "更新日時",
    })
    show_cols = ["分野", "内容", "教材/Unit", "Section/Type", "合計", "完了/正解", "進捗率%", "状態", "更新日時"]
    st.dataframe(detail[show_cols], use_container_width=True, hide_index=True)
    st.download_button(
        "学習記録CSVをダウンロード",
        detail[show_cols].to_csv(index=False).encode("utf-8-sig"),
        file_name="study_records.csv",
        mime="text/csv",
    )
    st.markdown('</div>', unsafe_allow_html=True)

    if not events_df.empty:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### テスト履歴")
        events_view = events_df.rename(columns={
            "area": "分野",
            "event_type": "種類",
            "title": "内容",
            "total_count": "問題数",
            "completed_count": "正解数",
            "score_rate": "正解率%",
            "created_at": "日時",
        })
        st.dataframe(events_view, use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)


def data_page(df):
    st.subheader("🛠 データ管理")
    st.write("SQLite DB:", str(DB_PATH))
    export = df.drop(columns=["choices_json", "choice_notes_json"], errors="ignore").copy()
    export["choices"] = export["choices"].apply(lambda x: " | ".join(x) if isinstance(x, list) else x)
    export["choice_notes"] = export["choice_notes"].apply(lambda x: " | ".join(x) if isinstance(x, list) else x)
    st.download_button(
        "CSVをダウンロード",
        export.to_csv(index=False).encode("utf-8-sig"),
        file_name="eiken_pre1_vocab_export.csv",
        mime="text/csv",
    )
    st.dataframe(export[["id", "exam", "qno", "question", "correct_word", "synonyms"]], use_container_width=True, hide_index=True)
    with st.expander("問題を削除"):
        qid = st.number_input("削除するID", min_value=1, step=1)
        if st.button("削除する", type="secondary"):
            delete_question(qid)
            st.success("削除しました。画面を再読み込みしてください。")


def main():
    init_db()
    if not st.session_state.get("auth_user_id"):
        auth_page()
        return

    df = load_questions()
    page, selected, keyword, question_submenu = sidebar_filters(df)
    save_user_progress("app", {"last_page": page})
    fdf = apply_filter(df, selected, keyword)
    if page == "🏠 Overview":
        overview(fdf)
    elif page == "📚 試験問題":
        list_page(fdf, submenu=question_submenu or "Vocabulary")
    elif page == "🧠 Quiz":
        quiz_page(fdf)
    elif page == "📗 パス単":
        passitan_page()
    elif page == "🧪 パス単テスト":
        passitan_test_page()
    elif page == "🌟 special-lesson":
        special_lesson_page()
    elif page == "📈 学習記録":
        study_records_page()
    elif page == "📝 単語帳":
        vocab_page()
    elif page == "📄 PDF生成":
        pdf_page(df)
    elif page == "➕ 問題を追加":
        add_page()
    elif page == "🛠 データ管理":
        data_page(fdf)


if __name__ == "__main__":
    main()
