import html
import json
import random
import sqlite3
import hashlib
import secrets
from urllib.parse import quote
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

# TOEFL-5600 用DB。app.py と同じフォルダの toefl_5600.db を優先し、
# 開発環境では /mnt/data/toefl_5600.db も読み込みます。
TOEFL_5600_DB_CANDIDATES = [
    APP_DIR / "toefl_5600.db",
    Path("/mnt/data/toefl_5600.db"),
]
TOEFL_5600_DB_PATH = next((p for p in TOEFL_5600_DB_CANDIDATES if p.exists()), TOEFL_5600_DB_CANDIDATES[0])

# TOEFL-KMF-word 用DB。CSVから作成した toefl_kmf_words.db を読み込みます。
TOEFL_KMF_WORD_DB_CANDIDATES = [
    APP_DIR / "toefl_kmf_words.db",
    Path("/mnt/data/toefl_kmf_words.db"),
]
TOEFL_KMF_WORD_DB_PATH = next((p for p in TOEFL_KMF_WORD_DB_CANDIDATES if p.exists()), TOEFL_KMF_WORD_DB_CANDIDATES[0])

# scientificamerican.com 用DB。日本語翻訳入りの science_articles_bilingual.db を優先し、
# 旧 scientificamerican.db も互換のため読み込みます。
SCIENTIFICAMERICAN_DB_CANDIDATES = [
    APP_DIR / "science_articles_bilingual.db",
    Path("/mnt/data/science_articles_bilingual.db"),
    APP_DIR / "scientificamerican.db",
    Path("/mnt/data/scientificamerican.db"),
]
SCIENTIFICAMERICAN_DB_PATH = next((p for p in SCIENTIFICAMERICAN_DB_CANDIDATES if p.exists()), SCIENTIFICAMERICAN_DB_CANDIDATES[0])
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
.choice-line { color:#ffffff; font-size: 22px; line-height: 1.85; font-weight: 700; }
.choice-line b { font-size: 22px; font-weight: 800; }
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


def auth_page():
    """ログイン前だけ表示する登録 / ログイン画面。"""
    st.markdown(
        """
        <div class="hero">
          <span class="pill">Login Required</span><span class="pill">Email Account</span>
          <h1>Learning Engish Dashbord</h1>
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


def ensure_vocab_strategy_tables(cur):
    """単語横断整理・忘却曲線レビュー用テーブルを追加します。"""
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS vocab_group_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            group_type TEXT NOT NULL,
            group_key TEXT NOT NULL,
            title TEXT NOT NULL,
            review_count INTEGER DEFAULT 0,
            ease_factor REAL DEFAULT 2.5,
            interval_days INTEGER DEFAULT 0,
            repetitions INTEGER DEFAULT 0,
            lapses INTEGER DEFAULT 0,
            last_reviewed_at TEXT DEFAULT '',
            next_review_date TEXT DEFAULT '',
            status TEXT DEFAULT '未学習',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, group_type, group_key)
        )
        """
    )


COMMON_PHRASES = {
    "adhere": [("adhere to", "〜に固執する、〜を守る、〜に従う")],
    "comply": [("comply with", "〜に従う、〜を守る")],
    "conform": [("conform to", "〜に従う、〜に一致する")],
    "consist": [("consist of", "〜から成る"), ("consist in", "〜にある、本質が〜にある")],
    "depend": [("depend on", "〜に依存する、〜次第である")],
    "rely": [("rely on", "〜に頼る、〜を信頼する")],
    "insist": [("insist on", "〜を強く主張する")],
    "persist": [("persist in", "〜をし続ける、固執する")],
    "result": [("result in", "〜という結果になる"), ("result from", "〜から生じる")],
    "stem": [("stem from", "〜に由来する、〜から生じる")],
    "attribute": [("attribute A to B", "AをBのせい・おかげだと考える")],
    "accuse": [("accuse A of B", "AをBのことで非難する、告発する")],
    "deprive": [("deprive A of B", "AからBを奪う")],
    "remind": [("remind A of B", "AにBを思い出させる")],
    "prevent": [("prevent A from doing", "Aが〜するのを防ぐ")],
    "prohibit": [("prohibit A from doing", "Aが〜することを禁止する")],
    "distinguish": [("distinguish A from B", "AとBを区別する")],
    "derive": [("derive from", "〜に由来する")],
    "dispose": [("dispose of", "〜を処分する")],
    "cope": [("cope with", "〜に対処する")],
    "deal": [("deal with", "〜に対処する、〜を扱う")],
    "object": [("object to", "〜に反対する")],
    "appeal": [("appeal to", "〜に訴える、魅力がある")],
    "refer": [("refer to", "〜に言及する、〜を参照する")],
    "amount": [("amount to", "合計〜になる、結局〜に等しい")],
    "account": [("account for", "〜を説明する、〜の割合を占める")],
    "bring": [("bring about", "〜を引き起こす")],
    "carry": [("carry out", "〜を実行する")],
    "figure": [("figure out", "〜を理解する、解決する")],
    "look": [("look into", "〜を調査する"), ("look up", "〜を調べる")],
    "take": [("take over", "〜を引き継ぐ"), ("take into account", "〜を考慮に入れる")],
    "give": [("give up", "〜をあきらめる"), ("give in", "屈する")],
    "put": [("put off", "〜を延期する"), ("put up with", "〜に耐える")],
    "come": [("come up with", "〜を思いつく")],
    "make": [("make up for", "〜を埋め合わせる")],
    "run": [("run into", "〜に偶然会う、問題にぶつかる"), ("run out of", "〜を使い果たす")],
}

ANTONYM_PAIRS = [
    ("increase", "decrease"), ("expand", "shrink"), ("accept", "reject"),
    ("include", "exclude"), ("major", "minor"), ("optimistic", "pessimistic"),
    ("positive", "negative"), ("temporary", "permanent"), ("ancient", "modern"),
    ("private", "public"), ("domestic", "foreign"), ("import", "export"),
    ("advantage", "disadvantage"), ("efficient", "inefficient"), ("active", "passive"),
    ("visible", "invisible"), ("legal", "illegal"), ("formal", "informal"),
    ("internal", "external"), ("superior", "inferior"), ("maximum", "minimum"),
    ("scarce", "abundant"), ("urban", "rural"), ("voluntary", "compulsory"),
    ("construct", "destroy"), ("permit", "prohibit"), ("success", "failure"),
    ("secure", "insecure"), ("accurate", "inaccurate"), ("relevant", "irrelevant"),
    ("stable", "unstable"), ("mature", "immature"), ("likely", "unlikely"),
    ("ordinary", "extraordinary"), ("flexible", "rigid"), ("generous", "stingy"),
    ("humble", "arrogant"), ("minority", "majority"), ("expand", "contract"),
]

WORD_FAMILY_HINTS = {
    "administer": ["administer", "administration", "administrative", "administrator"],
    "misery": ["misery", "miserable", "miserably"],
    "vary": ["vary", "various", "variety", "variable", "variation"],
    "benefit": ["benefit", "beneficial", "beneficiary"],
    "industry": ["industry", "industrial", "industrious"],
    "economy": ["economy", "economic", "economical", "economics", "economist"],
    "politics": ["politics", "political", "politician"],
    "history": ["history", "historic", "historical", "historian"],
    "science": ["science", "scientific", "scientist"],
    "confidence": ["confidence", "confident", "confidential"],
    "evidence": ["evidence", "evident", "evidently"],
    "significance": ["significance", "significant", "significantly"],
    "depend": ["depend", "dependent", "independent", "dependence"],
    "rely": ["rely", "reliable", "reliability", "unreliable"],
    "create": ["create", "creation", "creative", "creativity", "creator"],
    "destroy": ["destroy", "destruction", "destructive"],
    "produce": ["produce", "product", "production", "productive", "producer"],
    "consume": ["consume", "consumer", "consumption", "consumable"],
    "compete": ["compete", "competition", "competitive", "competitor"],
    "permit": ["permit", "permission", "permissible"],
    "decide": ["decide", "decision", "decisive", "decidedly"],
    "explain": ["explain", "explanation", "explanatory"],
    "describe": ["describe", "description", "descriptive"],
    "compare": ["compare", "comparison", "comparative", "comparable"],
    "analyze": ["analyze", "analysis", "analytical", "analyst"],
    "benefit": ["benefit", "beneficial", "beneficiary"],
    "participate": ["participate", "participation", "participant", "participatory"],
    "maintain": ["maintain", "maintenance", "maintainable"],
    "recognize": ["recognize", "recognition", "recognizable"],
    "apply": ["apply", "application", "applicant", "applicable"],
    "destroy": ["destroy", "destruction", "destructive"],
    "construct": ["construct", "construction", "constructive"],
    "protect": ["protect", "protection", "protective"],
    "attract": ["attract", "attraction", "attractive"],
    "inform": ["inform", "information", "informative"],
}


def _clean_word(w):
    import re
    w = str(w or "").strip().lower()
    w = re.sub(r"^[^a-z]+|[^a-z]+$", "", w)
    return w


def _soundex(word):
    word = _clean_word(word)
    if not word:
        return ""
    first = word[0].upper()
    mapping = {
        **dict.fromkeys(list("bfpv"), "1"),
        **dict.fromkeys(list("cgjkqsxz"), "2"),
        **dict.fromkeys(list("dt"), "3"),
        "l": "4",
        **dict.fromkeys(list("mn"), "5"),
        "r": "6",
    }
    digits = []
    prev = mapping.get(word[0], "")
    for ch in word[1:]:
        d = mapping.get(ch, "")
        if d and d != prev:
            digits.append(d)
        prev = d
    return (first + "".join(digits) + "000")[:4]


def _family_root(word):
    w = _clean_word(word)
    irregular = {
        "administer": "administ", "administration": "administ", "administrative": "administ", "administrator": "administ",
        "miserable": "miser", "misery": "miser", "miserably": "miser",
        "various": "vari", "variety": "vari", "variable": "vari", "variation": "vari",
        "beneficial": "benefit", "beneficiary": "benefit",
        "economic": "econom", "economical": "econom", "economist": "econom",
        "analysis": "analy", "analytical": "analy", "analyst": "analy", "analyze": "analy",
        "maintenance": "maintain", "recognition": "recogniz", "recognizable": "recogniz",
        "application": "apply", "applicant": "apply", "applicable": "apply",
    }
    if w in irregular:
        return irregular[w]
    suffixes = ["ically", "ability", "ibility", "ation", "ition", "ously", "fully", "less", "ness", "ment", "ence", "ance", "able", "ible", "tion", "sion", "ity", "ive", "ous", "ial", "ical", "ally", "ing", "ed", "er", "or", "ly", "al", "ic", "ize", "ise", "ate"]
    for suf in suffixes:
        if w.endswith(suf) and len(w) > len(suf) + 3:
            return w[:-len(suf)]
    if w.endswith("y") and len(w) > 5:
        return w[:-1]
    return w


POS_OVERRIDES = {
    "administer": "verb",
    "administration": "noun",
    "administrative": "adj",
    "administrator": "noun",
    "misery": "noun",
    "miserable": "adj",
    "miserably": "adv",
    "vary": "verb",
    "various": "adj",
    "variety": "noun",
    "variable": "adj/noun",
    "variation": "noun",
    "benefit": "noun/verb",
    "beneficial": "adj",
    "beneficiary": "noun",
    "industry": "noun",
    "industrial": "adj",
    "industrious": "adj",
    "economy": "noun",
    "economic": "adj",
    "economical": "adj",
    "economics": "noun",
    "economist": "noun",
    "politics": "noun",
    "political": "adj",
    "politician": "noun",
    "history": "noun",
    "historic": "adj",
    "historical": "adj",
    "historian": "noun",
    "science": "noun",
    "scientific": "adj",
    "scientist": "noun",
    "confidence": "noun",
    "confident": "adj",
    "confidential": "adj",
    "evidence": "noun",
    "evident": "adj",
    "evidently": "adv",
    "significance": "noun",
    "significant": "adj",
    "significantly": "adv",
    "depend": "verb",
    "dependent": "adj/noun",
    "independent": "adj",
    "dependence": "noun",
    "rely": "verb",
    "reliable": "adj",
    "reliability": "noun",
    "unreliable": "adj",
    "create": "verb",
    "creation": "noun",
    "creative": "adj",
    "creativity": "noun",
    "creator": "noun",
    "destroy": "verb",
    "destruction": "noun",
    "destructive": "adj",
    "produce": "verb",
    "product": "noun",
    "production": "noun",
    "productive": "adj",
    "producer": "noun",
    "consume": "verb",
    "consumer": "noun",
    "consumption": "noun",
    "consumable": "adj/noun",
    "compete": "verb",
    "competition": "noun",
    "competitive": "adj",
    "competitor": "noun",
    "permit": "verb/noun",
    "permission": "noun",
    "permissible": "adj",
    "decide": "verb",
    "decision": "noun",
    "decisive": "adj",
    "decidedly": "adv",
    "explain": "verb",
    "explanation": "noun",
    "explanatory": "adj",
    "describe": "verb",
    "description": "noun",
    "descriptive": "adj",
    "compare": "verb",
    "comparison": "noun",
    "comparative": "adj/noun",
    "comparable": "adj",
    "analyze": "verb",
    "analysis": "noun",
    "analytical": "adj",
    "analyst": "noun",
    "participate": "verb",
    "participation": "noun",
    "participant": "noun",
    "participatory": "adj",
    "maintain": "verb",
    "maintenance": "noun",
    "maintainable": "adj",
    "recognize": "verb",
    "recognition": "noun",
    "recognizable": "adj",
    "apply": "verb",
    "application": "noun",
    "applicant": "noun",
    "applicable": "adj",
    "construct": "verb",
    "construction": "noun",
    "constructive": "adj",
    "protect": "verb",
    "protection": "noun",
    "protective": "adj",
    "attract": "verb",
    "attraction": "noun",
    "attractive": "adj",
    "inform": "verb",
    "information": "noun",
    "informative": "adj",
}


def infer_part_of_speech(word):
    """派生語表示用の簡易品詞推定。手動辞書を優先し、一般的な語尾で補完します。"""
    w = _clean_word(word)
    if not w:
        return ""
    if w in POS_OVERRIDES:
        return POS_OVERRIDES[w]

    # 副詞
    if w.endswith("ly") and len(w) > 4:
        return "adv"

    # 名詞になりやすい語尾
    noun_suffixes = (
        "tion", "sion", "ation", "ition", "ment", "ness", "ity",
        "ence", "ance", "cy", "ism", "ist", "or", "er",
        "ship", "hood", "ure", "al", "age", "dom"
    )
    if w.endswith(noun_suffixes):
        return "noun"

    # 形容詞になりやすい語尾
    adj_suffixes = (
        "ive", "ative", "able", "ible", "al", "ial", "ical",
        "ous", "ious", "ful", "less", "ent", "ant", "ary", "ory"
    )
    if w.endswith(adj_suffixes):
        return "adj"

    # 動詞になりやすい語尾
    verb_suffixes = ("ize", "ise", "ify", "ate", "en")
    if w.endswith(verb_suffixes):
        return "verb"

    return "word"


def format_word_with_pos(word):
    word_text = str(word or "").strip()
    pos = infer_part_of_speech(word_text)
    return f"{word_text} ({pos})" if pos else word_text


def _load_passitan_words_for_strategy():
    con = connect()
    try:
        df = pd.read_sql_query(
            """
            SELECT id, no, word, meaning, example_sentence, source, known
            FROM passitan_words
            ORDER BY no
            """,
            con,
        )
    except Exception:
        df = pd.DataFrame()
    finally:
        con.close()
    if df.empty:
        return df
    df["word_clean"] = df["word"].apply(_clean_word)
    df = df[df["word_clean"] != ""].copy()
    df["grade_label"] = df["source"].apply(passitan_grade_label) if "source" in df.columns else ""
    df["display_no"] = df.apply(passitan_display_no, axis=1) if "source" in df.columns else df["no"]
    return df


def _phrase_list_for_word(word):
    w = _clean_word(word)
    return COMMON_PHRASES.get(w, [])


def format_phrase_for_word(word):
    phrases = _phrase_list_for_word(word)
    if not phrases:
        return ""
    return " / ".join([f"{p}: {m}" for p, m in phrases])


def format_word_family_hint_for_word(word):
    """手動登録した品詞派生ヒントを、該当単語から直接表示できる文字列にします。"""
    wc = _clean_word(word)
    if not wc:
        return ""

    for root, variants in WORD_FAMILY_HINTS.items():
        cleaned_variants = [_clean_word(v) for v in variants]
        # administer のように、動詞と administration / administrative のrootが単純一致しないものも、
        # WORD_FAMILY_HINTS に入っていれば必ず表示します。
        if wc == _clean_word(root) or wc in cleaned_variants:
            labels = []
            seen = set()
            for v in variants:
                vc = _clean_word(v)
                if vc and vc not in seen:
                    seen.add(vc)
                    labels.append(format_word_with_pos(v))
            return " / ".join(labels)
    return ""


def build_vocab_strategy_index(groups=None):
    """単語ごとに、同義語・反対語・発音注意・品詞派生・熟語セットを引ける辞書を作ります。"""
    groups = groups if groups is not None else build_vocab_strategy_groups(max_each=200)
    index = {}
    for g in groups:
        for w in g.get("words", []):
            wc = _clean_word(w)
            if wc:
                index.setdefault(wc, []).append(g)
        # 反対語タイトル "a ⇔ b" のようなものも拾う
        title = str(g.get("title", ""))
        if "⇔" in title:
            for part in title.split("⇔"):
                wc = _clean_word(part)
                if wc:
                    index.setdefault(wc, []).append(g)
    return index


def get_vocab_strategy_items_for_word(word, strategy_index=None):
    """パス単カードに表示する関連情報をカテゴリ別に返します。"""
    wc = _clean_word(word)
    if not wc:
        return []
    strategy_index = strategy_index or build_vocab_strategy_index()
    groups = strategy_index.get(wc, [])
    items = []
    seen = set()

    # 熟語は必ずCOMMON_PHRASESから表示
    phrase_text = format_phrase_for_word(word)
    if phrase_text:
        items.append(("熟語", phrase_text))
        seen.add(("熟語", phrase_text))

    # administer -> administration / administrative のような、語根だけでは拾いにくい派生語を補強表示
    family_hint_text = format_word_family_hint_for_word(word)
    if family_hint_text:
        items.append(("品詞派生", family_hint_text))
        seen.add(("品詞派生", family_hint_text))

    label_map = {
        "同義語": "同義語",
        "反対語": "反対語",
        "発音注意": "発音が近い",
        "品詞派生": "品詞派生",
        "熟語セット": "熟語",
    }
    order = {"同義語": 1, "反対語": 2, "発音注意": 3, "品詞派生": 4, "熟語セット": 5}
    for g in sorted(groups, key=lambda x: order.get(x.get("type", ""), 99)):
        gtype = str(g.get("type", ""))
        label = label_map.get(gtype, gtype or "関連")
        words = [str(x) for x in g.get("words", []) if str(x).strip()]
        others = [x for x in words if _clean_word(x) != wc]

        if gtype == "熟語セット":
            text = str(g.get("details", "")).replace(" = ", ": ")
            if not text or text == phrase_text:
                continue
        elif gtype == "反対語":
            text = " / ".join(others) if others else str(g.get("title", ""))
            if g.get("meaning"):
                text = f"{text}（{g.get('meaning')}）"
        elif gtype == "同義語":
            text = " / ".join(others) if others else str(g.get("details", ""))
        elif gtype == "発音注意":
            text = " / ".join(others) if others else str(g.get("title", ""))
            examples = str(g.get("examples", "")).strip()
            if examples:
                text = f"{text}｜{examples}"
        elif gtype == "品詞派生":
            text = " / ".join([format_word_with_pos(x) for x in words])
            details = str(g.get("details", "")).strip()
            if details and details not in text:
                text = f"{text}｜{details}"
        else:
            text = str(g.get("details", "")) or " / ".join(others)

        text = " ".join(str(text or "").split())
        if not text:
            continue
        key = (label, text)
        if key not in seen:
            seen.add(key)
            items.append((label, text))

    return items


def render_vocab_strategy_items_html(word, strategy_index=None, compact=False):
    items = get_vocab_strategy_items_for_word(word, strategy_index=strategy_index)
    if not items:
        return ""
    max_items = 5 if compact else 8
    html_lines = []
    for label, text in items[:max_items]:
        html_lines.append(
            f'<div class="passitan-related-line"><span class="passitan-related-label">{html.escape(label)}</span> {html.escape(text)}</div>'
        )
    return '<div class="passitan-related-box">' + ''.join(html_lines) + '</div>'


def build_vocab_strategy_groups(max_each=120):
    """DB内の単語を横断して、覚えやすいグループを自動生成します。"""
    words_df = _load_passitan_words_for_strategy()
    groups = []
    if words_df.empty:
        return groups

    word_set = set(words_df["word_clean"].tolist())
    word_meta = {r["word_clean"]: r for _, r in words_df.iterrows()}

    # 1) 熟語・セット表現
    for w, phrases in COMMON_PHRASES.items():
        if w in word_set:
            r = word_meta[w]
            groups.append({
                "type": "熟語セット",
                "key": f"phrase::{w}",
                "title": str(r["word"]),
                "words": [str(r["word"])],
                "meaning": str(r.get("meaning", "")),
                "details": " / ".join([f"{p} = {m}" for p, m in phrases]),
                "reason": "単語単体ではなく、前置詞・型とセットで覚える",
                "examples": str(r.get("example_sentence", "")),
            })

    # 2) 同義語：questionsテーブルのsynonymsを利用
    con = connect()
    try:
        qdf = pd.read_sql_query("SELECT question, choices_json, answer, synonyms FROM questions WHERE synonyms IS NOT NULL AND synonyms != ''", con)
    except Exception:
        qdf = pd.DataFrame()
    finally:
        con.close()
    for _, row in qdf.iterrows():
        try:
            choices = json.loads(row.get("choices_json", "[]"))
            ans = int(row.get("answer", 0))
            correct = str(choices[ans - 1]) if 1 <= ans <= len(choices) else ""
        except Exception:
            correct = ""
        if not correct:
            continue
        syns = [x.strip() for x in str(row.get("synonyms", "")).replace(";", ",").split(",") if x.strip()]
        if syns:
            groups.append({
                "type": "同義語",
                "key": f"syn::{_clean_word(correct)}",
                "title": correct,
                "words": [correct] + syns[:6],
                "meaning": "似た意味の単語をまとめて覚える",
                "details": ", ".join(syns[:8]),
                "reason": "選択肢問題では、言い換え・類義語で理解できると強い",
                "examples": str(row.get("question", "")),
            })

    # 3) 反対語：辞書ペア + DB内にあるものを優先表示
    for a, b in ANTONYM_PAIRS:
        if a in word_set or b in word_set:
            ar = word_meta.get(a)
            br = word_meta.get(b)
            a_mean = str(ar.get("meaning", "")) if ar is not None else ""
            b_mean = str(br.get("meaning", "")) if br is not None else ""
            groups.append({
                "type": "反対語",
                "key": f"ant::{a}::{b}",
                "title": f"{a} ⇔ {b}",
                "words": [a, b],
                "meaning": f"{a_mean} / {b_mean}".strip(" /"),
                "details": f"{a} の反対語: {b}",
                "reason": "反対語で覚えると意味の境界がはっきりする",
                "examples": "",
            })

    # 4) 品詞派生：名詞・形容詞・副詞などを同じrootでまとめる
    fam = {}
    for _, r in words_df.iterrows():
        w = str(r["word_clean"])
        if len(w) >= 4 and " " not in w:
            fam.setdefault(_family_root(w), []).append(r)
    for root, rows in fam.items():
        uniq = []
        seen = set()
        for r in rows:
            wc = str(r["word_clean"])
            if wc not in seen:
                seen.add(wc); uniq.append(r)
        if len(uniq) >= 2:
            labels = [str(r["word"]) for r in uniq[:8]]
            display_labels = [format_word_with_pos(r["word"]) for r in uniq[:8]]
            meanings = [f"{format_word_with_pos(r['word'])}: {r.get('meaning','')}" for r in uniq[:5]]
            groups.append({
                "type": "品詞派生",
                "key": f"family::{root}",
                "title": " / ".join(display_labels[:4]),
                "words": labels,
                "meaning": " | ".join(meanings),
                "details": "同じ語根・派生語として整理",
                "reason": "名詞・形容詞・副詞をセットで覚える。例: misery / miserable",
                "examples": " / ".join([str(r.get("example_sentence", "")) for r in uniq[:2] if str(r.get("example_sentence", ""))]),
            })

    # 手動ヒントで代表的な品詞派生を補強
    for root, variants in WORD_FAMILY_HINTS.items():
        present = [w for w in variants if _clean_word(w) in word_set]
        if len(present) >= 2:
            groups.append({
                "type": "品詞派生",
                "key": f"familyhint::{root}",
                "title": " / ".join([format_word_with_pos(w) for w in present]),
                "words": present,
                "meaning": "派生語をセットで暗記",
                "details": " → ".join([format_word_with_pos(w) for w in present]),
                "reason": "同じ語根から品詞を横に広げる",
                "examples": "",
            })

    # 5) 発音が近くて間違いやすい：Soundex近似 + 長さが近いもの
    sound_groups = {}
    for _, r in words_df.iterrows():
        w = str(r["word_clean"])
        if len(w) >= 5 and " " not in w:
            sound_groups.setdefault(_soundex(w), []).append(r)
    for code, rows in sound_groups.items():
        uniq = []
        seen = set()
        for r in rows:
            wc = str(r["word_clean"])
            if wc not in seen:
                seen.add(wc); uniq.append(r)
        if 2 <= len(uniq) <= 8:
            labels = [str(r["word"]) for r in uniq]
            # あまりにも関係ない大集団を避けるため、先頭文字または長さ差を軽く確認
            if max(len(_clean_word(x)) for x in labels) - min(len(_clean_word(x)) for x in labels) <= 4:
                groups.append({
                    "type": "発音注意",
                    "key": f"sound::{code}::{'-'.join(sorted([_clean_word(x) for x in labels])[:5])}",
                    "title": " / ".join(labels[:5]),
                    "words": labels,
                    "meaning": "発音・綴りが近く、選択肢で混同しやすい",
                    "details": f"音声コード: {code}",
                    "reason": "見た目・音が近い単語は、意味を対比して覚える",
                    "examples": " | ".join([f"{r['word']}: {r.get('meaning','')}" for r in uniq[:5]]),
                })

    # 重複を削除し、タイプごとに上限
    dedup = []
    seen_keys = set()
    counts = {}
    priority = {"熟語セット": 0, "同義語": 1, "反対語": 2, "品詞派生": 3, "発音注意": 4}
    for g in sorted(groups, key=lambda x: (priority.get(x["type"], 9), x["key"])):
        if g["key"] in seen_keys:
            continue
        if counts.get(g["type"], 0) >= max_each:
            continue
        seen_keys.add(g["key"])
        counts[g["type"]] = counts.get(g["type"], 0) + 1
        dedup.append(g)
    return dedup


def load_vocab_group_reviews(user_id):
    con = connect()
    try:
        df = pd.read_sql_query(
            """
            SELECT group_type, group_key, review_count, ease_factor, interval_days,
                   repetitions, lapses, last_reviewed_at, next_review_date, status
            FROM vocab_group_reviews
            WHERE user_id=?
            """,
            con,
            params=(int(user_id),),
        )
    except Exception:
        df = pd.DataFrame()
    finally:
        con.close()
    return df


def review_vocab_group(user_id, group_type, group_key, title, result):
    con = connect()
    cur = con.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO vocab_group_reviews
        (user_id, group_type, group_key, title, next_review_date)
        VALUES (?, ?, ?, ?, DATE('now'))
        """,
        (int(user_id), str(group_type), str(group_key), str(title)),
    )
    cur.execute(
        """
        SELECT ease_factor, interval_days, repetitions, lapses
        FROM vocab_group_reviews
        WHERE user_id=? AND group_type=? AND group_key=?
        """,
        (int(user_id), str(group_type), str(group_key)),
    )
    row = cur.fetchone() or (2.5, 0, 0, 0)
    ease = float(row[0] or 2.5)
    interval = int(row[1] or 0)
    reps = int(row[2] or 0)
    lapses = int(row[3] or 0)

    if result == "again":
        reps = 0; interval = 1; ease = max(1.3, ease - 0.25); lapses += 1; status = "復習中"
    elif result == "hard":
        reps += 1; interval = max(1, int(round(max(interval, 1) * 1.2))); ease = max(1.3, ease - 0.15); status = "復習中"
    elif result == "easy":
        reps += 1
        interval = 3 if reps <= 1 else 7 if reps == 2 else max(interval + 1, int(round(interval * (ease + 0.35))))
        ease = min(3.2, ease + 0.15); status = "覚えた" if interval >= 14 else "復習中"
    else:
        reps += 1
        interval = 1 if reps <= 1 else 3 if reps == 2 else max(interval + 1, int(round(interval * ease)))
        status = "覚えた" if interval >= 14 else "復習中"

    next_date = (date.today() + timedelta(days=interval)).isoformat()
    cur.execute(
        """
        UPDATE vocab_group_reviews
        SET title=?, status=?, review_count=review_count+1, ease_factor=?, interval_days=?,
            repetitions=?, lapses=?, last_reviewed_at=DATE('now'), next_review_date=?, updated_at=CURRENT_TIMESTAMP
        WHERE user_id=? AND group_type=? AND group_key=?
        """,
        (str(title), status, ease, interval, reps, lapses, next_date, int(user_id), str(group_type), str(group_key)),
    )
    con.commit(); con.close()
    return next_date


def vocab_strategy_page():
    st.subheader("🧩 単語整理・忘却曲線プラン")
    st.caption("DB内の単語を横断して、反対語・同義語・発音注意・品詞派生・熟語セットで整理します。グループ単位で復習日も管理できます。")

    groups = build_vocab_strategy_groups(max_each=160)
    if not groups:
        st.warning("単語データが見つかりません。passitan_words テーブルを確認してください。")
        return

    user_id = int(st.session_state.get("auth_user_id", 0) or 0)
    review_df = load_vocab_group_reviews(user_id) if user_id else pd.DataFrame()
    review_map = {}
    if not review_df.empty:
        for _, r in review_df.iterrows():
            review_map[(str(r["group_type"]), str(r["group_key"]))] = r.to_dict()

    for g in groups:
        r = review_map.get((g["type"], g["key"]), {})
        g["next_review_date"] = str(r.get("next_review_date", "")) or today_iso()
        g["status"] = str(r.get("status", "未学習") or "未学習")
        g["review_count"] = int(r.get("review_count", 0) or 0)
        g["is_due"] = g["next_review_date"] <= today_iso()

    summary_df = pd.DataFrame([{
        "分類": g["type"],
        "タイトル": g["title"],
        "単語": ", ".join(g["words"][:8]),
        "説明": g["details"],
        "次回復習": g["next_review_date"],
        "状態": g["status"],
        "復習回数": g["review_count"],
    } for g in groups])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("整理グループ数", len(groups))
    c2.metric("今日復習", sum(1 for g in groups if g["is_due"]))
    c3.metric("熟語セット", sum(1 for g in groups if g["type"] == "熟語セット"))
    c4.metric("品詞派生", sum(1 for g in groups if g["type"] == "品詞派生"))

    tab_due, tab_all, tab_export = st.tabs(["今日の復習", "分類別に見る", "CSV出力"])

    with tab_due:
        due_groups = [g for g in groups if g["is_due"]]
        if not due_groups:
            st.success("今日復習するグループはありません。")
        else:
            type_filter = st.multiselect(
                "復習する分類",
                ["熟語セット", "同義語", "反対語", "発音注意", "品詞派生"],
                default=["熟語セット", "同義語", "反対語", "発音注意", "品詞派生"],
                key="vocab_strategy_due_type_filter",
            )
            due_groups = [g for g in due_groups if g["type"] in type_filter]
            for i, g in enumerate(due_groups[:80], start=1):
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.markdown(
                    f'<span class="badge">{html.escape(g["type"])}</span>'
                    f'<span class="badge">次回: {html.escape(g["next_review_date"])}</span>'
                    f'<span class="badge">復習: {g["review_count"]}回</span>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"### {html.escape(g['title'])}", unsafe_allow_html=True)
                st.write("**単語:**", " / ".join(g["words"]))
                if g.get("meaning"):
                    st.write("**意味:**", g["meaning"])
                st.write("**整理ポイント:**", g["details"])
                st.write("**覚え方:**", g["reason"])
                if g.get("examples"):
                    st.write("**例文・メモ:**", g["examples"])
                cols = st.columns(4)
                for col, (result, label) in zip(cols, [("again", "もう一度"), ("hard", "難しい"), ("good", "覚えた"), ("easy", "簡単")]):
                    with col:
                        if st.button(label, key=f"vocab_group_review_{i}_{result}_{g['key']}"):
                            next_date = review_vocab_group(user_id, g["type"], g["key"], g["title"], result)
                            st.success(f"次回復習日を {next_date} にしました。")
                            st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

    with tab_all:
        selected_type = st.selectbox(
            "分類を選択",
            ["すべて", "熟語セット", "同義語", "反対語", "発音注意", "品詞派生"],
            key="vocab_strategy_type",
        )
        keyword = st.text_input("検索", placeholder="例: adhere / miserable / decrease", key="vocab_strategy_keyword")
        view_groups = groups
        if selected_type != "すべて":
            view_groups = [g for g in view_groups if g["type"] == selected_type]
        if keyword:
            k = keyword.lower().strip()
            view_groups = [g for g in view_groups if k in (g["title"] + " " + " ".join(g["words"]) + " " + g.get("details", "") + " " + g.get("meaning", "")).lower()]

        st.info(f"表示グループ: {len(view_groups)}件")
        for i, g in enumerate(view_groups[:150], start=1):
            with st.expander(f"{g['type']}｜{g['title']}｜次回 {g['next_review_date']}", expanded=False):
                st.write("**単語:**", " / ".join(g["words"]))
                if g.get("meaning"):
                    st.write("**意味:**", g["meaning"])
                st.write("**整理ポイント:**", g["details"])
                st.write("**覚え方:**", g["reason"])
                if g.get("examples"):
                    st.write("**例文・メモ:**", g["examples"])
                c1, c2 = st.columns([1, 3])
                with c1:
                    if st.button("今日復習に入れる", key=f"vocab_group_due_{i}_{g['key']}"):
                        con = connect(); cur = con.cursor()
                        cur.execute(
                            """
                            INSERT OR IGNORE INTO vocab_group_reviews
                            (user_id, group_type, group_key, title, next_review_date)
                            VALUES (?, ?, ?, ?, DATE('now'))
                            """,
                            (user_id, g["type"], g["key"], g["title"]),
                        )
                        cur.execute(
                            """
                            UPDATE vocab_group_reviews
                            SET next_review_date=DATE('now'), updated_at=CURRENT_TIMESTAMP
                            WHERE user_id=? AND group_type=? AND group_key=?
                            """,
                            (user_id, g["type"], g["key"]),
                        )
                        con.commit(); con.close()
                        st.success("今日の復習に入れました。")
                        st.rerun()

    with tab_export:
        st.download_button(
            "単語整理CSVをダウンロード",
            summary_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="vocab_strategy_groups.csv",
            mime="text/csv",
        )
        st.dataframe(summary_df, use_container_width=True, hide_index=True)


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
    ensure_vocab_strategy_tables(cur)

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


def normalize_question_grade_label(grade_value, tags_value=""):
    """questions.grade / tags から、試験問題画面用の級ラベルを作ります。"""
    text = f"{grade_value or ''} {tags_value or ''}".replace("１", "1").lower()
    if "準1" in text or "準１" in text or "pre-1" in text or "pre1" in text:
        return "英検準1級"
    if "英検1級" in text or "英検 1級" in text or "grade 1" in text or text.strip() in {"1", "1級", "grade1"}:
        return "英検1級"
    if str(grade_value or "").strip():
        return str(grade_value).strip()
    return "その他"


def normalize_question_category(tags_value="", question_value=""):
    """tags から Vocabulary / Reading / Grammar を判定します。"""
    text = f"{tags_value or ''} {question_value or ''}".lower()
    if any(k.lower() in text for k in ["reading", "読解", "リーディング", "長文"]):
        return "Reading"
    if any(k.lower() in text for k in ["grammar", "文法", "グラマー", "語法"]):
        return "Grammar"
    if any(k.lower() in text for k in ["vocabulary", "vocab", "語彙", "単語"]):
        return "Vocabulary"
    return "Vocabulary"


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
    df["question_grade_label"] = df.apply(lambda r: normalize_question_grade_label(r.get("grade", ""), r.get("tags", "")), axis=1)
    df["question_category"] = df.apply(lambda r: normalize_question_category(r.get("tags", ""), r.get("question", "")), axis=1)
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



def get_query_param_value(name, default=""):
    """StreamlitのURLクエリから値を安全に1つ取り出します。"""
    try:
        value = st.query_params.get(name, default)
    except Exception:
        try:
            params = st.experimental_get_query_params()
            value = params.get(name, [default])
        except Exception:
            value = default
    if isinstance(value, list):
        return value[0] if value else default
    return value if value is not None else default


def apply_passitan_jump_from_query():
    """試験問題のリンクからパス単へ移動するためのURLパラメータを処理します。

    st.radio(key="main_page") を生成した後に main_page を直接変更すると
    StreamlitAPIException になるため、ここでは pending_main_page に保存します。
    sidebar_filters() の radio 生成前に pending_main_page を反映します。
    """
    word = str(get_query_param_value("goto_passitan_word", "") or "").strip()
    if not word:
        return
    grade = str(get_query_param_value("goto_passitan_grade", "") or "").strip()
    no = str(get_query_param_value("goto_passitan_no", "") or "").strip()

    st.session_state["pending_main_page"] = "📗 パス単"
    st.session_state["passitan_jump_word"] = word
    if grade:
        st.session_state["passitan_jump_grade"] = grade
    if no:
        st.session_state["passitan_jump_no"] = no

    # URLにパラメータが残ると、検索欄を消しても毎回同じ単語へ戻るため、処理後にクリアします。
    try:
        st.query_params.clear()
    except Exception:
        pass


def build_passitan_word_index():
    """パス単に登録されている単語を、試験問題ハイライト用の辞書にします。"""
    df = load_passitan_words()
    if df.empty:
        return {}
    df = df.copy()
    df["grade_label"] = df["source"].apply(passitan_grade_label)
    df["display_no"] = df.apply(passitan_display_no, axis=1)
    index = {}
    for _, row in df.iterrows():
        word = str(row.get("word", "") or "").strip()
        if not word:
            continue
        key = word.lower()
        # 同じ単語が複数ある場合は、最初に見つかったものをリンク先にします。
        index.setdefault(key, {
            "word": word,
            "grade": str(row.get("grade_label", "")),
            "no": int(row.get("display_no", row.get("no", 0)) or 0),
            "meaning": str(row.get("meaning", "") or ""),
        })
    return index


def jump_to_passitan_word(info):
    """同じStreamlitセッション内でパス単へ移動する予約をします。

    main_page は sidebar の radio widget key と同じため、
    widget生成後に直接書き換えると StreamlitAPIException になります。
    そのため、ここでは pending_main_page に保存し、次のrerun開始時に反映します。
    """
    st.session_state["pending_main_page"] = "📗 パス単"
    st.session_state["passitan_jump_word"] = str(info.get("word", "") or "")
    if info.get("grade"):
        st.session_state["passitan_jump_grade"] = str(info.get("grade", "") or "")
    if info.get("no"):
        st.session_state["passitan_jump_no"] = str(info.get("no", "") or "")


def _passitan_match_pattern(passitan_index):
    """パス単語検索用の正規表現を作ります。"""
    import re
    if not passitan_index:
        return None
    words = [w for w in passitan_index.keys() if len(str(w)) >= 3]
    if not words:
        return None
    words = sorted(words, key=len, reverse=True)
    return re.compile(r"(?<![A-Za-z])(" + "|".join(re.escape(w) for w in words) + r")(?![A-Za-z])", re.IGNORECASE)


def collect_passitan_matches(texts, passitan_index):
    """文章・選択肢に出たパス単語を重複なしで集めます。"""
    pattern = _passitan_match_pattern(passitan_index)
    if pattern is None:
        return []
    found = {}
    for text in texts:
        for m in pattern.finditer(str(text or "")):
            info = passitan_index.get(m.group(0).lower())
            if info:
                found.setdefault(str(info.get("word", "")).lower(), info)
    return list(found.values())


def highlight_passitan_words(text, passitan_index):
    """文章中にパス単登録語が出たら、クリック可能な緑色リンクにします。

    追加ボタンは出さず、単語そのものをクリックすると同じStreamlitアプリ内で
    📗 パス単へ移動し、検索欄にその単語を入れます。
    """
    from urllib.parse import urlencode

    text = str(text or "")
    pattern = _passitan_match_pattern(passitan_index)
    if not text or pattern is None:
        return html.escape(text)

    out = []
    pos = 0
    for m in pattern.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        matched = m.group(0)
        info = passitan_index.get(matched.lower())
        if info:
            title = f"{info.get('grade', 'パス単') or 'パス単'} No.{info.get('no', '')} / {info.get('meaning', '')}"
            query = urlencode({
                "goto_passitan_word": str(info.get("word", matched) or matched),
                "goto_passitan_grade": str(info.get("grade", "") or ""),
                "goto_passitan_no": str(info.get("no", "") or ""),
            })
            out.append(
                f'<a class="passitan-hit" href="?{html.escape(query)}" target="_self" '
                f'title="{html.escape(title)}">{html.escape(matched)}</a>'
            )
        else:
            out.append(html.escape(matched))
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)

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

    page_options = ["🏠 Overview", "📚 試験問題", "🧠 Quiz", "📗 パス単", "🧪 パス単テスト", "🧩 単語整理", "📕 TOEFL-5600", "📙 TOEFL-KMF-word", "🔬 scientificamerican.com", "🌟 special-lesson", "📝 単語帳", "📄 PDF生成", "➕ 問題を追加", "🛠 データ管理"]

    # 別画面からの移動予約を、radio widget生成前に反映します。
    # widget生成後に st.session_state["main_page"] を変更するとエラーになるためです。
    pending_page = st.session_state.pop("pending_main_page", None)
    if pending_page in page_options:
        st.session_state["main_page"] = pending_page

    if st.session_state.get("main_page") not in page_options:
        st.session_state["main_page"] = page_options[0]
    page = st.sidebar.radio(
        "画面",
        page_options,
        label_visibility="collapsed",
        key="main_page",
    )

    question_submenu = None
    question_grade = None
    if page == "📚 試験問題":
        with st.sidebar.expander("📚 試験問題サブメニュー", expanded=True):
            grade_candidates = []
            if not df.empty and "question_grade_label" in df.columns:
                grade_candidates = df["question_grade_label"].dropna().astype(str).unique().tolist()
            # DBに英検1級の問題がまだ入っていない場合でも、
            # 級の選択肢には常に「英検準1級」「英検1級」を表示します。
            preferred_grades = ["英検準1級", "英検1級"]
            grade_options = preferred_grades + [g for g in grade_candidates if g not in preferred_grades]
            question_grade = st.radio(
                "級を選択",
                grade_options,
                index=0,
                key="question_list_grade",
            )
            question_submenu = st.radio(
                "カテゴリ",
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

    return page, selected, keyword, question_submenu, question_grade


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


def render_card(row, show_answer=True, passitan_index=None, highlight_passitan=False):
    choices = row["choices"]
    notes = row["choice_notes"]
    correct = choices[int(row["answer"]) - 1]
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(f'<span class="badge">{row["exam"]}</span><span class="badge">Q{int(row["qno"])}</span><span class="badge">{row.get("difficulty", "標準")}</span>', unsafe_allow_html=True)
    question_html = highlight_passitan_words(row["question"], passitan_index) if highlight_passitan else html.escape(str(row["question"]))
    st.markdown(f'<div class="question"><span class="qnum">({int(row["qno"])})</span> {question_html}</div>', unsafe_allow_html=True)
    cols = st.columns(4)
    for i, ch in enumerate(choices, start=1):
        prefix = "✅" if show_answer and i == int(row["answer"]) else f"{i}."
        choice_html = highlight_passitan_words(ch, passitan_index) if highlight_passitan else html.escape(str(ch))
        cols[i-1].markdown(f'<div class="choice-line"><b>{html.escape(prefix)}</b> {choice_html}</div>', unsafe_allow_html=True)

    # パス単に存在する単語は、問題文・選択肢の中で緑色ハイライトのみ表示します。
    # 追加の「📗 単語名」ボタンは表示しません。
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


def overview(df):
    render_hero(df)
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
        st.write("4. 新しい問題は『問題を追加』から登録")
        st.markdown('</div>', unsafe_allow_html=True)
    st.subheader("🔥 最近の重要語")
    sample = df[["exam", "qno", "correct_word", "synonyms"]].tail(12).sort_values(["exam", "qno"])
    st.dataframe(sample, use_container_width=True, hide_index=True)


def list_page(df, submenu="Vocabulary", selected_grade="英検準1級"):
    st.subheader(f"📚 試験問題 / {selected_grade} / {submenu}")

    target_df = df.copy()

    if "question_grade_label" in target_df.columns and selected_grade:
        target_df = target_df[target_df["question_grade_label"] == selected_grade]

    if "question_category" in target_df.columns and submenu:
        target_df = target_df[target_df["question_category"] == submenu]
    elif "tags" in target_df.columns and submenu == "Reading":
        target_df = target_df[target_df["tags"].astype(str).str.contains("Reading|読解|リーディング|長文", case=False, na=False)]
    elif "tags" in target_df.columns and submenu == "Grammar":
        target_df = target_df[target_df["tags"].astype(str).str.contains("Grammar|文法|グラマー|語法", case=False, na=False)]

    if submenu == "Vocabulary":
        st.caption("語彙問題の文章、日本語訳、正解、選択肢解析、類義語をカード形式で確認できます。")
    elif submenu == "Reading":
        st.caption("Reading問題を表示します。tagsに Reading / 読解 / リーディング / 長文 が入っている問題が対象です。")
    elif submenu == "Grammar":
        st.caption("Grammar問題を表示します。tagsに Grammar / 文法 / グラマー / 語法 が入っている問題が対象です。")

    if not target_df.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("級", selected_grade)
        c2.metric("カテゴリ", submenu)
        c3.metric("問題数", len(target_df))

    passitan_index = {}
    highlight_passitan = submenu == "Vocabulary"
    if highlight_passitan:
        passitan_index = build_passitan_word_index()
        st.markdown(
            """
            <style>
            .passitan-hit {
                color: #32d583 !important;
                font-weight: 900;
                text-decoration: underline;
                text-decoration-thickness: 2px;
                cursor: pointer;
                text-underline-offset: 3px;
                background: rgba(50, 213, 131, .12);
                border-radius: 6px;
                padding: 0 4px;
            }
            .passitan-hit:hover { background: rgba(50, 213, 131, .24); }
            .choice-line { color: #ffffff; font-size: 22px; line-height: 1.85; font-weight: 700; }
            </style>
            """,
            unsafe_allow_html=True,
        )
        if passitan_index:
            st.caption("緑色の単語はパス単に登録済みです。単語をクリックすると、再ログインなしでパス単へ移動します。")

    show = st.toggle("答えと解説を表示", value=False)

    if target_df.empty:
        st.info(
            f"{selected_grade} / {submenu} の問題データはまだありません。"
            f"『問題を追加』画面で Grade と Category を選択するか、tagsに {submenu} を入れると表示できます。"
        )
        return

    for _, row in target_df.iterrows():
        render_card(row, show_answer=show, passitan_index=passitan_index, highlight_passitan=highlight_passitan)


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


def connect_toefl_kmf_word_db():
    return sqlite3.connect(TOEFL_KMF_WORD_DB_PATH, check_same_thread=False)


def load_toefl_kmf_words():
    """toefl_kmf_words.db から KMF TOEFL 単語を読み込みます。"""
    db_path = next((p for p in TOEFL_KMF_WORD_DB_CANDIDATES if p.exists()), None)
    if db_path is None:
        return pd.DataFrame(), "DBが見つかりません: toefl_kmf_words.db を app.py と同じフォルダに置いてください。"

    try:
        con = sqlite3.connect(db_path, check_same_thread=False)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='kmf_words'")
        if cur.fetchone() is None:
            con.close()
            return pd.DataFrame(), f"TOEFL-KMF-word DBに kmf_words テーブルがありません: {db_path.name}"

        cur.execute("PRAGMA table_info(kmf_words)")
        existing_cols = {row[1] for row in cur.fetchall()}
        required_cols = {"global_order", "source_type", "list_no", "section", "word", "meaning_jp"}
        missing = sorted(required_cols - existing_cols)
        if missing:
            con.close()
            return pd.DataFrame(), f"TOEFL-KMF-word DBの kmf_words テーブルに必要な列がありません: {', '.join(missing)}"

        word_index_expr = "word_index" if "word_index" in existing_cols else "`index` AS word_index"
        phonetic_expr = "phonetic" if "phonetic" in existing_cols else "'' AS phonetic"
        example1_expr = "example1_en" if "example1_en" in existing_cols else "'' AS example1_en"
        example2_expr = "example2_en" if "example2_en" in existing_cols else "'' AS example2_en"
        known_expr = "known" if "known" in existing_cols else "0 AS known"
        note_expr = "note" if "note" in existing_cols else "'' AS note"
        id_expr = "id" if "id" in existing_cols else "rowid AS id"
        df = pd.read_sql_query(
            f"""
            SELECT {id_expr}, global_order, source_type, list_no, section, {word_index_expr},
                   word, {phonetic_expr}, meaning_jp, {example1_expr}, {example2_expr},
                   {known_expr}, {note_expr}
            FROM kmf_words
            ORDER BY global_order
            """,
            con,
        )
        con.close()
    except Exception as e:
        return pd.DataFrame(), f"TOEFL-KMF-word DBの読み込みに失敗しました: {e}"

    if df.empty:
        return df, "TOEFL-KMF-word のデータがありません。"

    for col in ["source_type", "word", "phonetic", "meaning_jp", "example1_en", "example2_en", "note"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)
    for col in ["id", "global_order", "list_no", "section", "word_index", "known"]:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["source_db"] = str(db_path.name)
    return df, ""


def update_toefl_kmf_known(row_id, known):
    con = connect_toefl_kmf_word_db()
    con.execute(
        "UPDATE kmf_words SET known=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (1 if known else 0, int(row_id)),
    )
    con.commit()
    con.close()


def toefl_kmf_source_label(source_type):
    src = str(source_type or "").strip().lower()
    if src == "core":
        return "Core Vocabulary"
    if src == "listening":
        return "Listening Vocabulary"
    return str(source_type or "その他")


def toefl_kmf_word_page():
    st.subheader("📙 TOEFL-KMF-word")
    st.caption("kmf_toefl_words_list_meaning_jp.csv から作成したDBを読み込み、パス単と同じように単語・日本語意味・例文・Known・単語帳登録を表示します。")

    kmf_df, err = load_toefl_kmf_words()
    if err:
        st.warning(err)
    if kmf_df.empty:
        return

    kmf_df = kmf_df.copy()
    kmf_df["source_label"] = kmf_df["source_type"].apply(toefl_kmf_source_label)

    total = len(kmf_df)
    known_count = int(kmf_df["known"].fillna(0).astype(int).sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("登録単語数", total)
    c2.metric("わかった単語", known_count)
    c3.metric("未チェック", total - known_count)
    c4.metric("DB", str(kmf_df["source_db"].iloc[0]) if "source_db" in kmf_df.columns else "-")

    st.markdown(
        """
        <style>
        .kmf-card {
            padding: 12px 14px;
            border-radius: 16px;
            background: rgba(255,255,255,.045);
            border: 1px solid rgba(255,255,255,.18);
            margin: 0 0 10px 0;
        }
        .kmf-top { display:flex; align-items:center; gap:8px; margin-bottom: 6px; flex-wrap: wrap; }
        .kmf-no {
            display:inline-flex; align-items:center; justify-content:center;
            min-width: 46px; height:24px; border-radius:999px;
            background: rgba(255,255,255,.12); color:#dce8fb;
            font-size:12px; font-weight:850;
        }
        .kmf-tag {
            display:inline-flex; align-items:center; justify-content:center;
            min-width: 70px; height:24px; border-radius:999px;
            background: rgba(79,172,254,.15); color:#cfe8ff;
            font-size:12px; font-weight:800; padding: 0 9px;
        }
        .kmf-word { color:#ffffff; font-size:22px; font-weight:900; line-height:1.2; overflow-wrap:anywhere; }
        .kmf-phonetic { color:#aebbd0; font-size:14px; font-weight:700; }
        .kmf-meaning { color:#b7ffcf; font-size:15px; line-height:1.55; margin: 4px 0 8px 0; }
        .kmf-example { color:#d7e2f5; font-size:19px; line-height:1.55; margin: 4px 0; overflow-wrap:anywhere; }
        .kmf-table-header, .kmf-cell {
            box-sizing:border-box; min-height:44px; padding:5px 6px; margin:0;
            display:flex; align-items:center; overflow:hidden;
            border-left: 1px solid rgba(255,255,255,.24);
            border-bottom: 1px solid rgba(255,255,255,.20);
            border-radius:0;
        }
        .kmf-table-header { background:rgba(255,255,255,.16); border-top:1px solid rgba(255,255,255,.40); font-weight:850; color:#eef4ff; }
        .kmf-cell { background:rgba(255,255,255,.035); }
        .kmf-center { justify-content:center; text-align:center; }
        .kmf-table-word { font-size:16px; font-weight:900; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .kmf-table-meaning { color:#b7ffcf; font-size:12px; line-height:1.3; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .kmf-table-example { width:100%; color:#d7e2f5; font-size:16px; line-height:1.35; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        div[data-testid="stHorizontalBlock"]:has(.kmf-table-row) { gap: 0 !important; }
        div[data-testid="stHorizontalBlock"]:has(.kmf-table-row) > div[data-testid="column"] { padding: 0 !important; }
        div[data-testid="stHorizontalBlock"]:has(.kmf-table-row) div[data-testid="element-container"] { margin: 0 !important; padding: 0 !important; }
        div[data-testid="stHorizontalBlock"]:has(.kmf-table-row) div[data-testid="stCheckbox"] { display:flex !important; justify-content:center !important; align-items:center !important; min-height:34px !important; }
        div[data-testid="stHorizontalBlock"]:has(.kmf-table-row) div[data-testid="stCheckbox"] p { display:none !important; }
        div[data-testid="stHorizontalBlock"]:has(.kmf-table-row) div[data-testid="stButton"] { display:flex !important; justify-content:center !important; align-items:center !important; min-height:34px !important; }
        div[data-testid="stHorizontalBlock"]:has(.kmf-table-row) div[data-testid="stButton"] > button {
            width:58px !important; min-width:58px !important; height:26px !important; min-height:26px !important;
            padding:0 6px !important; border-radius:6px !important; font-size:12px !important;
            background:transparent !important; background-image:none !important; color:#eef4ff !important;
            border:1px solid rgba(255,255,255,.45) !important; box-shadow:none !important;
        }
        @media (max-width: 768px) {
            .kmf-word { font-size:20px; }
            .kmf-example { font-size:18px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="card">', unsafe_allow_html=True)
    source_options = ["すべて"] + sorted(kmf_df["source_label"].dropna().astype(str).unique().tolist())
    c_source, c_list, c_section, c_keyword, c_flags = st.columns([1.3, 1.0, 1.0, 2.0, 1.1])
    with c_source:
        selected_source = st.selectbox("Source", source_options, index=0, key="kmf_source_select")
    temp_df = kmf_df.copy()
    if selected_source != "すべて":
        temp_df = temp_df[temp_df["source_label"] == selected_source]
    list_options = ["すべて"] + [str(x) for x in sorted(temp_df["list_no"].dropna().astype(int).unique().tolist())]
    with c_list:
        selected_list = st.selectbox("List", list_options, index=0, key="kmf_list_select")
    temp_df2 = temp_df.copy()
    if selected_list != "すべて":
        temp_df2 = temp_df2[temp_df2["list_no"] == int(selected_list)]
    section_options = ["すべて"] + [str(x) for x in sorted(temp_df2["section"].dropna().astype(int).unique().tolist())]
    with c_section:
        selected_section = st.selectbox("Section", section_options, index=0, key="kmf_section_select")
    with c_keyword:
        keyword = st.text_input("検索", placeholder="例: abandon / 捨てる / academic", key="kmf_keyword")
    with c_flags:
        hide_known = st.checkbox("Knownを隠す", value=False, key="kmf_hide_known")
        view_mode = st.radio("表示", ["スマホカード", "PC表"], index=0, key="kmf_view_mode")
    st.markdown('</div>', unsafe_allow_html=True)

    view = kmf_df.copy()
    if selected_source != "すべて":
        view = view[view["source_label"] == selected_source]
    if selected_list != "すべて":
        view = view[view["list_no"] == int(selected_list)]
    if selected_section != "すべて":
        view = view[view["section"] == int(selected_section)]
    if keyword:
        k = keyword.lower().strip()
        view = view[
            view["word"].astype(str).str.lower().str.contains(k, na=False)
            | view["meaning_jp"].astype(str).str.lower().str.contains(k, na=False)
            | view["phonetic"].astype(str).str.lower().str.contains(k, na=False)
            | view["example1_en"].astype(str).str.lower().str.contains(k, na=False)
            | view["example2_en"].astype(str).str.lower().str.contains(k, na=False)
        ]
    if hide_known:
        view = view[view["known"].fillna(0).astype(int) == 0]
    view = view.sort_values("global_order")

    c_view, c_page = st.columns([1.3, 2.0])
    with c_view:
        display_n = st.selectbox("表示件数", [10, 20, 50, 100], index=2, key="kmf_display_n")
    total_view = len(view)
    max_page = max(1, (total_view + int(display_n) - 1) // int(display_n))
    with c_page:
        page_no = st.number_input("ページ", min_value=1, max_value=max_page, value=min(int(st.session_state.get("kmf_page_no", 1)), max_page), step=1, key="kmf_page_no")
    start = (int(page_no) - 1) * int(display_n)
    page_df = view.iloc[start:start + int(display_n)].copy()

    st.info(f"表示: {len(page_df)} / {total_view}語（ページ {page_no}/{max_page}）")
    export_cols = ["global_order", "source_type", "list_no", "section", "word_index", "word", "phonetic", "meaning_jp", "example1_en", "example2_en", "known"]
    st.download_button(
        "TOEFL-KMF-word CSVをダウンロード",
        view[export_cols].to_csv(index=False).encode("utf-8-sig"),
        file_name="toefl_kmf_words_export.csv",
        mime="text/csv",
    )

    if page_df.empty:
        st.info("この条件で表示できる単語がありません。")
        return

    if view_mode == "スマホカード":
        for _, row in page_df.iterrows():
            row_id = int(row["id"])
            global_order = int(row.get("global_order", 0))
            word = str(row.get("word", ""))
            phonetic = str(row.get("phonetic", ""))
            meaning = str(row.get("meaning_jp", ""))
            ex1 = str(row.get("example1_en", ""))
            ex2 = str(row.get("example2_en", ""))
            is_known = bool(int(row.get("known") or 0))
            tag = f"{row.get('source_label', '')} / List {int(row.get('list_no', 0))} / Sec {int(row.get('section', 0))}"
            st.markdown(
                f"""
                <div class="kmf-card">
                  <div class="kmf-top">
                    <span class="kmf-no">No.{global_order}</span>
                    <span class="kmf-tag">{html.escape(tag)}</span>
                    <span class="kmf-word">{html.escape(word)}</span>
                    <span class="kmf-phonetic">/{html.escape(phonetic)}/</span>
                  </div>
                  <div class="kmf-meaning">{html.escape(meaning)}</div>
                  <div class="kmf-example">1. {html.escape(ex1)}</div>
                  <div class="kmf-example">2. {html.escape(ex2)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            a0, a1, a2 = st.columns([0.8, 1, 1])
            with a0:
                render_browser_speak_button(word, key=f"kmf_card_{row_id}", label="🔊", height=36)
            with a1:
                checked = st.checkbox("Known", value=is_known, key=f"kmf_known_card_{row_id}")
                if checked != is_known:
                    update_toefl_kmf_known(row_id, checked)
                    st.rerun()
            with a2:
                if st.button("登録", key=f"kmf_add_vocab_card_{row_id}", use_container_width=True):
                    ok, msg = add_vocab_word(
                        word,
                        meaning=meaning,
                        japanese_translation=meaning,
                        explanation="TOEFL-KMF-word から登録",
                        example_sentence=ex1 or ex2,
                        note=f"TOEFL-KMF-word / {tag}",
                    )
                    st.success(msg) if ok else st.error(msg)
    else:
        h_no, h_word, h_speak, h_meaning, h_example, h_known, h_add = st.columns([0.5, 1.25, 0.52, 2.2, 4.2, 0.72, 0.8], gap=None)
        h_no.markdown('<div class="kmf-table-header kmf-center kmf-table-row">No.</div>', unsafe_allow_html=True)
        h_word.markdown('<div class="kmf-table-header kmf-table-row">英単語</div>', unsafe_allow_html=True)
        h_speak.markdown('<div class="kmf-table-header kmf-center kmf-table-row">音声</div>', unsafe_allow_html=True)
        h_meaning.markdown('<div class="kmf-table-header kmf-table-row">日本語意味</div>', unsafe_allow_html=True)
        h_example.markdown('<div class="kmf-table-header kmf-table-row">例文</div>', unsafe_allow_html=True)
        h_known.markdown('<div class="kmf-table-header kmf-center kmf-table-row">Known</div>', unsafe_allow_html=True)
        h_add.markdown('<div class="kmf-table-header kmf-center kmf-table-row">単語帳</div>', unsafe_allow_html=True)
        for _, row in page_df.iterrows():
            row_id = int(row["id"])
            global_order = int(row.get("global_order", 0))
            word = str(row.get("word", ""))
            phonetic = str(row.get("phonetic", ""))
            meaning = str(row.get("meaning_jp", ""))
            ex1 = str(row.get("example1_en", ""))
            ex2 = str(row.get("example2_en", ""))
            is_known = bool(int(row.get("known") or 0))
            c_no, c_word, c_speak, c_meaning, c_example, c_known, c_add = st.columns([0.5, 1.25, 0.52, 2.2, 4.2, 0.72, 0.8], gap=None)
            with c_no:
                st.markdown(f'<div class="kmf-cell kmf-center kmf-table-row"><b>{global_order}</b></div>', unsafe_allow_html=True)
            with c_word:
                st.markdown(f'<div class="kmf-cell kmf-table-row"><div><div class="kmf-table-word">{html.escape(word)}</div><div class="kmf-table-meaning">/{html.escape(phonetic)}/</div></div></div>', unsafe_allow_html=True)
            with c_speak:
                st.markdown('<div class="kmf-table-row"></div>', unsafe_allow_html=True)
                render_browser_speak_button(word, key=f"kmf_table_{row_id}", label="🔊", height=34)
            with c_meaning:
                st.markdown(f'<div class="kmf-cell kmf-table-row"><div class="kmf-table-meaning" title="{html.escape(meaning)}">{html.escape(meaning)}</div></div>', unsafe_allow_html=True)
            with c_example:
                example_text = ex1 if not ex2 else f"{ex1} / {ex2}"
                st.markdown(f'<div class="kmf-cell kmf-table-row"><div class="kmf-table-example" title="{html.escape(example_text)}">{html.escape(example_text)}</div></div>', unsafe_allow_html=True)
            with c_known:
                checked = st.checkbox(" ", value=is_known, key=f"kmf_known_table_{row_id}", label_visibility="collapsed")
                if checked != is_known:
                    update_toefl_kmf_known(row_id, checked)
                    st.rerun()
            with c_add:
                if st.button("登録", key=f"kmf_add_vocab_table_{row_id}"):
                    ok, msg = add_vocab_word(
                        word,
                        meaning=meaning,
                        japanese_translation=meaning,
                        explanation="TOEFL-KMF-word から登録",
                        example_sentence=ex1 or ex2,
                        note=f"TOEFL-KMF-word / {row.get('source_label', '')} / List {int(row.get('list_no', 0))} / Sec {int(row.get('section', 0))}",
                    )
                    st.success(msg) if ok else st.error(msg)

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

    jump_grade = st.session_state.pop("passitan_jump_grade", "") if st.session_state.get("passitan_jump_grade") else ""
    jump_word = st.session_state.pop("passitan_jump_word", "") if st.session_state.get("passitan_jump_word") else ""
    if jump_grade and jump_grade in grade_options:
        st.session_state["passitan_grade_select"] = jump_grade

    st.markdown('<div class="card">', unsafe_allow_html=True)
    selected_grade = st.selectbox("教材を選択", grade_options, index=0, key="passitan_grade_select")
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

    if is_pre1_passitan:
        sections = build_passitan_sections(max_passitan_no, section_size=100, fixed_count=19)
        if section_key not in st.session_state:
            st.session_state[section_key] = sections[0]["label"]
        valid_section_labels = [sec["label"] for sec in sections]
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
            keyword_key = f"passitan_keyword_{grade_slug}"
            if jump_word:
                st.session_state[keyword_key] = str(jump_word)
            keyword = st.text_input("検索", placeholder="例: affect / 影響", key=keyword_key)
        with col_c:
            hide_known = st.checkbox("わかった単語を隠す", value=False, key=f"hide_known_{grade_slug}")
        with col_d:
            view_mode = st.radio(
                "表示形式",
                ["スマホカード", "PC表"],
                index=0,
                horizontal=False,
                key=f"view_mode_{grade_slug}",
                help="携帯電話では『スマホカード』を使うと表崩れを防げます。",
            )
        st.info(f"{selected_section_label} を表示します。範囲: No.{start_no}〜No.{end_no}（100語）")
    else:
        col_a, col_b, col_c, col_d, col_e = st.columns([1, 1, 2, 1, 1.2])
        with col_a:
            display_n = st.selectbox("表示件数", [10, 20, 50], index=2, key=f"display_n_{grade_slug}")
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
            keyword_key = f"passitan_keyword_{grade_slug}"
            if jump_word:
                st.session_state[keyword_key] = str(jump_word)
            keyword = st.text_input("検索", placeholder="例: affect / 影響", key=keyword_key)
        with col_d:
            hide_known = st.checkbox("わかった単語を隠す", value=False, key=f"hide_known_{grade_slug}")
        with col_e:
            view_mode = st.radio(
                "表示形式",
                ["スマホカード", "PC表"],
                index=0,
                horizontal=False,
                key=f"view_mode_{grade_slug}",
                help="携帯電話では『スマホカード』を使うと表崩れを防げます。",
            )
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

    if jump_word:
        st.success(f"パス単で '{jump_word}' を表示しています。検索欄を空にすると通常表示に戻ります。")
        st.session_state.pop("passitan_jump_word", None)
        st.session_state.pop("passitan_jump_no", None)

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
        .passitan-related-box {
            margin: 6px 0 8px 0;
            padding: 8px 10px;
            border-radius: 12px;
            background: rgba(255,231,163,.08);
            border: 1px solid rgba(255,231,163,.18);
        }
        .passitan-related-line {
            color: #ffe7a3;
            font-size: 12.5px;
            line-height: 1.45;
            margin: 2px 0;
            overflow-wrap: anywhere;
        }
        .passitan-related-label {
            display: inline-block;
            min-width: 64px;
            color: #ffffff;
            font-weight: 850;
        }
        .passitan-word-cell-wrap {
            display: flex;
            flex-direction: column;
            gap: 2px;
            width: 100%;
            min-width: 0;
        }
        .passitan-word-meaning {
            color: #b7ffcf;
            font-size: 11.5px;
            line-height: 1.3;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
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
            min-height: 44px;
            padding: 5px 6px;
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

    # パス単の各単語に、同義語・反対語・発音が近い・品詞派生・熟語を表示するための索引
    vocab_strategy_index = build_vocab_strategy_index(build_vocab_strategy_groups(max_each=200))

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
            related_html = render_vocab_strategy_items_html(word, strategy_index=vocab_strategy_index, compact=False)

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
                  {related_html}
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
            related_html = render_vocab_strategy_items_html(word, strategy_index=vocab_strategy_index, compact=True)

            hint_example = make_example_with_word_hint(example, word, hint_len=2)
            safe_example = html.escape(hint_example)

            c_no, c_word, c_speak, c_example, c_known, c_add = st.columns([0.38, 1.45, 0.56, 5.5, 0.78, 0.86], gap=None)
            with c_no:
                st.markdown(f'<div class="passitan-cell passitan-cell-center passitan-table-row"><b>{no}</b></div>', unsafe_allow_html=True)
            with c_word:
                st.markdown(
                    f'<div class="passitan-cell passitan-table-row"><div class="passitan-word-cell-wrap">'
                    f'<span class="passitan-word" title="{safe_meaning}">{safe_word}</span>'
                    f'<span class="passitan-word-meaning">{safe_meaning}</span>'
                    f'{related_html}'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
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

    st.markdown('<div class="card">', unsafe_allow_html=True)
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
    with c_scope:
        selected_scope_label = st.selectbox("出題範囲", scope_labels, index=1 if len(scope_labels) > 1 else 0, key=f"passitan_test_scope_{passitan_key_slug(selected_grade)}")
    selected_scope = next(opt for opt in scope_options if opt["label"] == selected_scope_label)

    scoped_df = passitan_df[
        (passitan_df["display_no"] >= int(selected_scope["start"]))
        & (passitan_df["display_no"] <= int(selected_scope["end"]))
    ].sort_values("display_no").copy()

    with c_count:
        count_options = ["10問", "20問", "50問", "100問", "選択範囲すべて"]
        selected_count = st.selectbox("出題数", count_options, index=1, key=f"passitan_test_count_{passitan_key_slug(selected_grade)}")
    with c_mode:
        order_mode = st.radio("順番", ["順番通り", "シャッフル"], index=0, key=f"passitan_test_order_{passitan_key_slug(selected_grade)}")

    c_audio, c_hint, c_known = st.columns([1, 1.2, 1.2])
    with c_audio:
        show_audio = st.checkbox("音声ボタンを表示", value=True, key=f"passitan_test_audio_{passitan_key_slug(selected_grade)}")
    with c_hint:
        show_example_hint = st.checkbox("例文ヒントを表示（日本語なし）", value=True, key=f"passitan_test_hint_{passitan_key_slug(selected_grade)}")
    with c_known:
        hide_known = st.checkbox("Knownを除外", value=False, key=f"passitan_test_hide_known_{passitan_key_slug(selected_grade)}")
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

    st.markdown('<div class="card">', unsafe_allow_html=True)
    c_unit, c_type, c_count, c_order = st.columns([2.0, 1.3, 1.0, 1.1])
    with c_unit:
        unit_options = ["すべて"] + sorted(lesson_df["unit"].dropna().unique().tolist())
        selected_unit = st.selectbox("Unit", unit_options, index=0, key="special_lesson_unit")
    with c_type:
        qtype_options = ["すべて"] + sorted(lesson_df["qtype"].dropna().unique().tolist())
        selected_qtype = st.selectbox("問題タイプ", qtype_options, index=0, key="special_lesson_qtype")
    with c_count:
        count_label = st.selectbox("出題数", ["5問", "10問", "20問", "すべて"], index=1, key="special_lesson_count")
    with c_order:
        order_mode = st.radio("順番", ["順番通り", "シャッフル"], index=0, key="special_lesson_order")
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


def parse_toefl_red_phrases(value):
    """DBの red_phrases を表示用リストへ変換します。"""
    value = str(value or "").strip()
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except Exception:
        pass
    # 現在のDBは "phrase | phrase" 形式。改行やカンマにも軽く対応します。
    parts = []
    for chunk in value.replace("\n", "|").split("|"):
        chunk = chunk.strip()
        if chunk:
            parts.append(chunk)
    return parts



def parse_toefl_red_phrase_jp_items(row):
    """赤色フレーズの日本語説明を [{en, ja}] 形式にそろえます。"""
    red_phrases = parse_toefl_red_phrases(row.get("red_phrases", ""))
    jp_json = str(row.get("red_phrases_jp_json", "") or "").strip()
    jp_text = str(row.get("red_phrases_jp", "") or "").strip()

    items = []
    if jp_json:
        try:
            parsed = json.loads(jp_json)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        en = str(item.get("en", "") or "").strip()
                        ja = str(item.get("ja", "") or "").strip()
                        if en or ja:
                            items.append({"en": en, "ja": ja})
        except Exception:
            items = []

    if not items and jp_text:
        for chunk in jp_text.replace("\n", "|").split("|"):
            chunk = chunk.strip()
            if not chunk:
                continue
            if "：" in chunk:
                en, ja = chunk.split("：", 1)
            elif ":" in chunk:
                en, ja = chunk.split(":", 1)
            else:
                en, ja = "", chunk
            items.append({"en": en.strip(), "ja": ja.strip()})

    normalized = []
    for i, item in enumerate(items):
        en = item.get("en", "") or (red_phrases[i] if i < len(red_phrases) else "")
        ja = item.get("ja", "") or ""
        if en or ja:
            normalized.append({"en": str(en).strip(), "ja": str(ja).strip()})

    if not normalized:
        normalized = [{"en": p, "ja": ""} for p in red_phrases]
    return normalized


def _highlight_passitan_words_plain_segment(text, passitan_index):
    """HTMLタグを含まない通常テキスト部分だけ、英検単語を緑色にします。"""
    text = str(text or "")
    pattern = _passitan_match_pattern(passitan_index)
    if not text or pattern is None:
        return html.escape(text)

    out = []
    pos = 0
    for m in pattern.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        matched = m.group(0)
        info = passitan_index.get(matched.lower())
        if info:
            title = f"{info.get('grade', 'パス単') or 'パス単'} No.{info.get('no', '')} / {info.get('meaning', '')}"
            out.append(
                f'<span class="toefl5600-eiken-hit" title="{html.escape(title)}">{html.escape(matched)}</span>'
            )
        else:
            out.append(html.escape(matched))
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def render_toefl_text_with_highlights(text, red_phrases, passitan_index=None):
    """赤色フレーズを優先し、それ以外の英検1級・準1級単語を緑色にします。"""
    import re

    text = str(text or "")
    red_phrases = [str(x or "").strip() for x in (red_phrases or []) if str(x or "").strip()]
    passitan_index = passitan_index or {}
    if not text:
        return ""
    if not red_phrases:
        return _highlight_passitan_words_plain_segment(text, passitan_index)

    phrase_pattern = re.compile("(" + "|".join(re.escape(p) for p in sorted(red_phrases, key=len, reverse=True)) + ")", re.IGNORECASE)
    out = []
    pos = 0
    for m in phrase_pattern.finditer(text):
        out.append(_highlight_passitan_words_plain_segment(text[pos:m.start()], passitan_index))
        out.append('<mark class="toefl5600-red-hit">' + html.escape(m.group(0)) + '</mark>')
        pos = m.end()
    out.append(_highlight_passitan_words_plain_segment(text[pos:], passitan_index))
    return "".join(out)


def _toefl_table_columns(cur, table_name):
    cur.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cur.fetchall()}


def infer_toefl_title(row):
    """title列がない旧DBでも、本文内容から教材タイトルを推定します。"""
    title = str(row.get("title", "") or "").strip()
    if title and title != "TOEFL-5600":
        return title

    text_value = (
        str(row.get("english_text", "") or "")
        + " "
        + str(row.get("highlighted_html", "") or "")
        + " "
        + str(row.get("red_phrases", "") or "")
    ).lower()
    try:
        paragraph_no = int(row.get("paragraph_no", 0) or 0)
    except Exception:
        paragraph_no = 0

    if any(k in text_value for k in ["blue", "prussian", "gainsborough", "egyptian blue", "pigment"]):
        return "The History of Blue"
    if any(k in text_value for k in ["native", "aboriginal", "bison", "plains", "horse", "nomadic"]):
        return "The Changing Style of Native Americans"
    if any(k in text_value for k in ["research", "archaeologist", "archaeologists", "excavation"]):
        return "Research"
    if any(k in text_value for k in ["physical anthropology", "genetic", "mendel", "blood groups", "heredity"]):
        return "Modern Physical Anthropology"

    # 旧DBで paragraph_no だけが分かる場合のフォールバック
    if 1 <= paragraph_no <= 3:
        return "Modern Physical Anthropology"
    if 16 <= paragraph_no <= 21:
        return "The Changing Style of Native Americans"
    return title or "TOEFL-5600"


def load_toefl_5600_passages():
    """toefl_5600.db から TOEFL-5600 の本文データを読み込みます。

    旧DB: paragraphs(id, paragraph_no, english_text, highlighted_html, red_phrases)
    新DB: reading_passages(title, paragraph_no, english_text, highlighted_html, red_phrases)
    の両方に対応します。
    """
    db_path = next((p for p in TOEFL_5600_DB_CANDIDATES if p.exists()), None)
    if db_path is None:
        return pd.DataFrame(), "DBが見つかりません: toefl_5600.db を app.py と同じフォルダに置いてください。"

    try:
        con = sqlite3.connect(db_path, check_same_thread=False)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}

        if "reading_passages" in tables:
            table_name = "reading_passages"
        elif "paragraphs" in tables:
            table_name = "paragraphs"
        else:
            con.close()
            return pd.DataFrame(), f"TOEFL-5600 DBに reading_passages / paragraphs テーブルがありません: {db_path.name}"

        existing_cols = _toefl_table_columns(cur, table_name)
        required = {"paragraph_no", "english_text", "highlighted_html", "red_phrases"}
        missing = sorted(required - existing_cols)
        if missing:
            con.close()
            return pd.DataFrame(), f"TOEFL-5600 DBの {table_name} テーブルに必要な列がありません: {', '.join(missing)}"

        title_expr = "title" if "title" in existing_cols else "'TOEFL-5600' AS title"
        id_expr = "id" if "id" in existing_cols else "rowid AS id"
        red_phrases_jp_expr = "red_phrases_jp" if "red_phrases_jp" in existing_cols else "'' AS red_phrases_jp"
        red_phrases_jp_json_expr = "red_phrases_jp_json" if "red_phrases_jp_json" in existing_cols else "'' AS red_phrases_jp_json"
        df = pd.read_sql_query(
            f"""
            SELECT {id_expr}, {title_expr}, paragraph_no, english_text, highlighted_html, red_phrases,
                   {red_phrases_jp_expr}, {red_phrases_jp_json_expr}
            FROM {table_name}
            ORDER BY title, paragraph_no, id
            """,
            con,
        )
        con.close()
    except Exception as e:
        return pd.DataFrame(), f"TOEFL-5600 DBの読み込みに失敗しました: {e}"

    if df.empty:
        return df, "TOEFL-5600 のデータがありません。"

    for col in ["title", "english_text", "highlighted_html", "red_phrases", "red_phrases_jp", "red_phrases_jp_json"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)
    df["paragraph_no"] = pd.to_numeric(df["paragraph_no"], errors="coerce").fillna(0).astype(int)
    df["title"] = df.apply(infer_toefl_title, axis=1)
    df["red_phrase_list"] = df["red_phrases"].apply(parse_toefl_red_phrases)
    df["red_phrase_jp_items"] = df.apply(parse_toefl_red_phrase_jp_items, axis=1)
    df["source_db"] = str(db_path.name)
    return df, ""


def build_toefl_title_view(df):
    """paragraph行をタイトル単位にまとめ、表示時は段落ごとに改行します。"""
    grouped_rows = []
    title_order = [
        "Modern Physical Anthropology",
        "Research",
        "The Changing Style of Native Americans",
        "The History of Blue",
    ]
    order_map = {title: i for i, title in enumerate(title_order)}

    for title, g in df.sort_values(["title", "paragraph_no", "id"]).groupby("title", sort=False):
        g = g.sort_values(["paragraph_no", "id"])
        body_parts = []
        plain_parts = []
        phrase_list = []
        phrase_jp_items = []
        paragraph_numbers = []
        for _, row in g.iterrows():
            paragraph_numbers.append(int(row.get("paragraph_no", 0) or 0))
            plain_text = str(row.get("english_text", "") or "").strip()
            body_parts.append(plain_text)
            plain_parts.append(plain_text)
            for phrase in row.get("red_phrase_list", []) or []:
                if phrase and phrase not in phrase_list:
                    phrase_list.append(phrase)
            seen_jp = {(x.get("en", "").lower(), x.get("ja", "")) for x in phrase_jp_items}
            for item in row.get("red_phrase_jp_items", []) or []:
                en = str(item.get("en", "") or "").strip()
                ja = str(item.get("ja", "") or "").strip()
                key = (en.lower(), ja)
                if (en or ja) and key not in seen_jp:
                    phrase_jp_items.append({"en": en, "ja": ja})
                    seen_jp.add(key)

        grouped_rows.append({
            "title": str(title),
            "sort_order": order_map.get(str(title), 999),
            "paragraph_numbers": paragraph_numbers,
            "paragraph_count": len(g),
            "english_text": "\n\n".join(x for x in plain_parts if x),
            "paragraph_texts": body_parts,
            "highlighted_html": "\n".join(f'<p class="toefl5600-paragraph">{html.escape(x)}</p>' for x in body_parts if x),
            "red_phrase_list": phrase_list,
            "red_phrase_jp_items": phrase_jp_items,
            "red_phrases": " | ".join(phrase_list),
        })

    out = pd.DataFrame(grouped_rows)
    if not out.empty:
        out = out.sort_values(["sort_order", "title"]).drop(columns=["sort_order"], errors="ignore")
    return out

def toefl_5600_page():
    st.subheader("📕 TOEFL-5600")
    st.caption("toefl_5600.db の本文を、タイトルごとに1つの文章として表示します。赤色ハイライトは赤色、英検1級・準1級の単語は緑色で表示します。日本語説明は『試験問題』の『答えと解説を表示』と同じように切り替えできます。")

    df, err = load_toefl_5600_passages()
    if err:
        st.warning(err)
    if df.empty:
        return

    title_df = build_toefl_title_view(df)
    if title_df.empty:
        st.info("表示できるTOEFL-5600データがありません。")
        return

    st.markdown(
        """
        <style>
        .toefl5600-card {
            padding: 18px 20px;
            border-radius: 20px;
            background: rgba(255,255,255,.045);
            border: 1px solid rgba(255,255,255,.18);
            margin: 0 0 14px 0;
        }
        .toefl5600-meta {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            background: rgba(255,255,255,.13);
            color: #dce8fb;
            font-size: 12px;
            font-weight: 850;
            margin-right: 6px;
            margin-bottom: 10px;
        }
        .toefl5600-title {
            color: #ffffff;
            font-size: 24px;
            font-weight: 900;
            margin: 4px 0 10px 0;
        }
        .toefl5600-scroll {
            max-height: 520px;
            overflow-y: auto;
            padding: 16px 18px;
            border-radius: 16px;
            background: rgba(0,0,0,.16);
            border: 1px solid rgba(255,255,255,.12);
        }
        .toefl5600-text {
            color: #ffffff;
            font-size: 21px;
            line-height: 1.9;
            font-weight: 650;
            overflow-wrap: anywhere;
        }
        .toefl5600-paragraph {
            margin: 0 0 20px 0;
        }
        .toefl5600-paragraph:last-child {
            margin-bottom: 0;
        }
        .toefl5600-text mark,
        .toefl5600-text span[style*="color:red"],
        .toefl5600-text span[style*="color: red"],
        .toefl5600-text font[color="red"],
        .toefl5600-red-hit {
            color: #ff4d4d !important;
            background: rgba(255, 77, 77, .14) !important;
            border-radius: 5px;
            padding: 0 3px;
            font-weight: 900;
        }
        .toefl5600-eiken-hit {
            color: #32d583 !important;
            background: rgba(50, 213, 131, .12) !important;
            border-radius: 5px;
            padding: 0 3px;
            font-weight: 900;
            text-decoration: underline;
            text-decoration-thickness: 2px;
            text-underline-offset: 3px;
        }
        .toefl5600-jp-explain {
            margin-top: 12px;
            padding: 12px 14px;
            border-radius: 14px;
            background: rgba(50,213,131,.07);
            border: 1px solid rgba(50,213,131,.22);
            color: #dfffea;
            line-height: 1.75;
        }
        .toefl5600-jp-row {
            padding: 5px 0;
            border-bottom: 1px solid rgba(255,255,255,.08);
        }
        .toefl5600-jp-row:last-child { border-bottom: 0; }
        .toefl5600-jp-en { color: #ffffff; font-weight: 900; }
        .toefl5600-jp-ja { color: #dfffea; }
        .toefl5600-phrases {
            margin-top: 12px;
            padding: 12px 14px;
            border-radius: 14px;
            background: rgba(255,77,77,.08);
            border: 1px solid rgba(255,77,77,.22);
            color: #ffdede;
            line-height: 1.7;
        }
        .toefl5600-chip {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            background: rgba(255,77,77,.12);
            border: 1px solid rgba(255,77,77,.22);
            color: #ffdede;
            font-size: 13px;
            font-weight: 750;
            margin: 4px 6px 4px 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    titles = ["すべて"] + [x for x in title_df["title"].dropna().astype(str).tolist() if x.strip()]
    c1, c2, c3, c4 = st.columns([1.7, 2.0, 1.1, 1.4])
    with c1:
        selected_title = st.selectbox("Title", titles, index=0, key="toefl5600_title_select")
    with c2:
        keyword = st.text_input("検索", placeholder="例: anthropology / Native peoples / blue", key="toefl5600_keyword")
    with c3:
        show_phrases = st.checkbox("赤色フレーズ", value=True, key="toefl5600_show_phrases")
    with c4:
        show_jp_explain = st.toggle("日本語説明を表示", value=False, key="toefl5600_show_jp_explain")

    view = title_df.copy()
    if selected_title != "すべて":
        view = view[view["title"] == selected_title]
    if keyword:
        k = keyword.lower().strip()
        view = view[
            view["title"].astype(str).str.lower().str.contains(k, na=False)
            | view["english_text"].astype(str).str.lower().str.contains(k, na=False)
            | view["highlighted_html"].astype(str).str.lower().str.contains(k, na=False)
            | view["red_phrases"].astype(str).str.lower().str.contains(k, na=False)
        ]

    if view.empty:
        st.info("この条件で表示できるTOEFL-5600データがありません。")
        return

    export_df = view.drop(columns=["red_phrase_list", "red_phrase_jp_items", "paragraph_texts"], errors="ignore").copy()
    export_df["paragraph_numbers"] = export_df["paragraph_numbers"].apply(lambda xs: ", ".join(map(str, xs)) if isinstance(xs, list) else str(xs))
    st.download_button(
        "TOEFL-5600 CSVをダウンロード",
        export_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="toefl_5600_passages_by_title.csv",
        mime="text/csv",
    )

    c_total, c_title, c_para = st.columns(3)
    c_total.metric("表示タイトル数", len(view))
    c_title.metric("全タイトル数", title_df["title"].nunique())
    c_para.metric("元Paragraph数", int(view["paragraph_count"].sum()))

    passitan_index = build_passitan_word_index()
    if passitan_index:
        st.caption("緑色の単語は、英検1級・準1級のパス単DBに存在する単語です。赤色フレーズを優先して表示します。")

    for _, row in view.iterrows():
        title = str(row.get("title", "TOEFL-5600")) or "TOEFL-5600"
        paragraph_numbers = row.get("paragraph_numbers", []) or []
        paragraph_label = ", ".join(map(str, paragraph_numbers)) if isinstance(paragraph_numbers, list) else str(paragraph_numbers)
        phrases = row.get("red_phrase_list", []) or []
        phrase_jp_items = row.get("red_phrase_jp_items", []) or []
        paragraph_texts = row.get("paragraph_texts", []) or []
        if not isinstance(paragraph_texts, list) or not paragraph_texts:
            paragraph_texts = [str(row.get("english_text", "") or "")]
        body_html = "\n".join(
            f'<p class="toefl5600-paragraph">{render_toefl_text_with_highlights(p, phrases, passitan_index)}</p>'
            for p in paragraph_texts
            if str(p or "").strip()
        )

        st.markdown('<div class="toefl5600-card">', unsafe_allow_html=True)
        st.markdown(
            f'<span class="toefl5600-meta">TOEFL-5600</span>'
            f'<span class="toefl5600-meta">{html.escape(title)}</span>'
            f'<span class="toefl5600-meta">Paragraph {html.escape(paragraph_label)}</span>',
            unsafe_allow_html=True,
        )
        st.markdown(f'<div class="toefl5600-title">{html.escape(title)}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="toefl5600-scroll"><div class="toefl5600-text">{body_html}</div></div>', unsafe_allow_html=True)
        if show_phrases and phrases:
            chips = "".join(f'<span class="toefl5600-chip">{html.escape(x)}</span>' for x in phrases)
            st.markdown(f'<div class="toefl5600-phrases"><b>赤色フレーズ:</b><br>{chips}</div>', unsafe_allow_html=True)

        if show_jp_explain and phrase_jp_items:
            rows_html = []
            for item in phrase_jp_items:
                en = str(item.get("en", "") or "").strip()
                ja = str(item.get("ja", "") or "").strip()
                if en or ja:
                    rows_html.append(
                        '<div class="toefl5600-jp-row">'
                        f'<span class="toefl5600-jp-en">{html.escape(en)}</span>'
                        f'：<span class="toefl5600-jp-ja">{html.escape(ja)}</span>'
                        '</div>'
                    )
            if rows_html:
                st.markdown(
                    '<div class="toefl5600-jp-explain"><b>日本語説明:</b>' + ''.join(rows_html) + '</div>',
                    unsafe_allow_html=True,
                )
        st.markdown('</div>', unsafe_allow_html=True)




def load_scientificamerican_articles():
    """scientificamerican系DBから記事本文・日本語訳・画像を読み込みます。

    新DB: science_articles_bilingual.db / articles(id, title, subtitle, content, image, content_ja)
    旧DB: scientificamerican.db / articles(id, title, subtitle, content, image)
    の両方に対応します。
    """
    db_path = next((p for p in SCIENTIFICAMERICAN_DB_CANDIDATES if p.exists()), None)
    if db_path is None:
        return pd.DataFrame(), "DBが見つかりません: science_articles_bilingual.db または scientificamerican.db を app.py と同じフォルダに置いてください。"

    try:
        con = sqlite3.connect(db_path, check_same_thread=False)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='articles'")
        if cur.fetchone() is None:
            con.close()
            return pd.DataFrame(), f"scientificamerican DBに articles テーブルがありません: {db_path.name}"

        cur.execute("PRAGMA table_info(articles)")
        existing_cols = {row[1] for row in cur.fetchall()}
        required = {"title", "content"}
        missing = sorted(required - existing_cols)
        if missing:
            con.close()
            return pd.DataFrame(), f"scientificamerican DBの articles テーブルに必要な列がありません: {', '.join(missing)}"

        id_expr = "id" if "id" in existing_cols else "rowid AS id"
        subtitle_expr = "subtitle" if "subtitle" in existing_cols else "'' AS subtitle"
        image_expr = "image" if "image" in existing_cols else "NULL AS image"
        content_ja_expr = "content_ja" if "content_ja" in existing_cols else "'' AS content_ja"
        df = pd.read_sql_query(
            f"""
            SELECT {id_expr}, title, {subtitle_expr}, content, {content_ja_expr}, {image_expr}
            FROM articles
            ORDER BY id
            """,
            con,
        )
        con.close()
    except Exception as e:
        return pd.DataFrame(), f"scientificamerican DBの読み込みに失敗しました: {e}"

    if df.empty:
        return df, "scientificamerican.com の記事データがありません。"

    for col in ["title", "subtitle", "content", "content_ja"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)
    df["source_db"] = str(db_path.name)
    return df, ""


def scientificamerican_image_data_uri(image_value, max_width=760):
    """DBの画像BLOBを、本文と並べやすいサイズに圧縮して data URI に変換します。"""
    import base64
    import io

    if image_value is None:
        return ""
    try:
        blob = bytes(image_value)
    except Exception:
        return ""
    if not blob:
        return ""

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(blob))
        img = img.convert("RGB")
        if img.width > max_width:
            ratio = max_width / float(img.width)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=82, optimize=True)
        blob = out.getvalue()
        mime = "image/jpeg"
    except Exception:
        if blob[:8] == b"\x89PNG\r\n\x1a\n":
            mime = "image/png"
        else:
            mime = "image/jpeg"

    return f"data:{mime};base64," + base64.b64encode(blob).decode("ascii")


def render_scientificamerican_text(text, keyword="", passitan_index=None):
    """記事本文を段落HTMLへ変換。検索語とパス単語リンクを同時に強調します。"""
    import re

    text = str(text or "").strip()
    if not text:
        return ""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    passitan_index = passitan_index or {}
    passitan_pattern = _passitan_match_pattern(passitan_index) if passitan_index else None
    keyword_text = str(keyword or "").strip()
    keyword_pattern = re.compile(re.escape(keyword_text), re.IGNORECASE) if keyword_text else None

    def render_segment(segment):
        # まずパス単語をリンク化します。リンク化した範囲では検索語ハイライトは重ねません。
        if not segment:
            return ""
        if passitan_pattern is None:
            return render_keyword_only(segment)
        out = []
        pos = 0
        for m in passitan_pattern.finditer(segment):
            out.append(render_keyword_only(segment[pos:m.start()]))
            matched = m.group(0)
            info = passitan_index.get(matched.lower())
            if info:
                from urllib.parse import urlencode
                title = f"{info.get('grade', 'パス単') or 'パス単'} No.{info.get('no', '')} / {info.get('meaning', '')}"
                query = urlencode({
                    "goto_passitan_word": str(info.get("word", matched) or matched),
                    "goto_passitan_grade": str(info.get("grade", "") or ""),
                    "goto_passitan_no": str(info.get("no", "") or ""),
                })
                out.append(
                    f'<a class="sciam-eiken-hit" href="?{html.escape(query)}" target="_self" '
                    f'title="{html.escape(title)}">{html.escape(matched)}</a>'
                )
            else:
                out.append(html.escape(matched))
            pos = m.end()
        out.append(render_keyword_only(segment[pos:]))
        return "".join(out)

    def render_keyword_only(segment):
        if not segment:
            return ""
        if keyword_pattern is None:
            return html.escape(segment)
        out = []
        pos = 0
        for m in keyword_pattern.finditer(segment):
            out.append(html.escape(segment[pos:m.start()]))
            out.append(f'<mark class="sciam-keyword-hit">{html.escape(m.group(0))}</mark>')
            pos = m.end()
        out.append(html.escape(segment[pos:]))
        return "".join(out)

    return "".join(f'<p class="sciam-paragraph">{render_segment(p)}</p>' for p in paragraphs)


def scientificamerican_page():
    st.subheader("🔬 scientificamerican.com")
    st.caption("science_articles_bilingual.db の articles テーブルから、英文・日本語翻訳・画像を表示します。日本語翻訳は TOEFL-5600 と同じように切り替えできます。")

    df, err = load_scientificamerican_articles()
    if err:
        st.warning(err)
    if df.empty:
        return

    st.markdown(
        """
        <style>
        .sciam-card {
            padding: 18px 20px;
            border-radius: 20px;
            background: rgba(255,255,255,.045);
            border: 1px solid rgba(255,255,255,.18);
            margin: 0 0 16px 0;
        }
        .sciam-meta {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            background: rgba(255,255,255,.13);
            color: #dce8fb;
            font-size: 12px;
            font-weight: 850;
            margin-right: 6px;
            margin-bottom: 10px;
        }
        .sciam-title {
            color: #ffffff;
            font-size: 30px;
            line-height: 1.25;
            font-weight: 900;
            margin: 4px 0 8px 0;
        }
        .sciam-subtitle {
            color: #b7ffcf;
            font-size: 18px;
            line-height: 1.55;
            font-weight: 750;
            margin: 0 0 14px 0;
        }
        .sciam-scroll {
            max-height: 620px;
            overflow-y: auto;
            padding: 18px 20px;
            border-radius: 16px;
            background: rgba(0,0,0,.16);
            border: 1px solid rgba(255,255,255,.12);
        }
        .sciam-text {
            color: #ffffff;
            font-size: 20px;
            line-height: 1.9;
            font-weight: 650;
            overflow-wrap: anywhere;
        }
        .sciam-inline-image {
            float: right;
            width: min(42%, 390px);
            max-height: 360px;
            object-fit: contain;
            border-radius: 16px;
            border: 1px solid rgba(255,255,255,.16);
            background: rgba(0,0,0,.24);
            margin: 2px 0 14px 22px;
            box-shadow: 0 18px 45px rgba(0,0,0,.28);
        }
        .sciam-paragraph { margin: 0 0 20px 0; }
        .sciam-paragraph:last-child { margin-bottom: 0; }
        .sciam-keyword-hit {
            color: #111827 !important;
            background: #ffe066 !important;
            border-radius: 5px;
            padding: 0 3px;
            font-weight: 900;
        }
        .sciam-eiken-hit {
            color: #32d583 !important;
            background: rgba(50, 213, 131, .12) !important;
            border-radius: 5px;
            padding: 0 3px;
            font-weight: 900;
            text-decoration: underline;
            text-decoration-thickness: 2px;
            text-underline-offset: 3px;
            cursor: pointer;
        }
        .sciam-jp-box {
            margin-top: 14px;
            padding: 14px 16px;
            border-radius: 14px;
            background: rgba(50,213,131,.07);
            border: 1px solid rgba(50,213,131,.22);
            color: #dfffea;
            line-height: 1.85;
            font-size: 18px;
            overflow-wrap: anywhere;
        }
        .sciam-jp-title {
            color: #ffffff;
            font-weight: 900;
            margin-bottom: 8px;
        }
        .sciam-clear { clear: both; height: 1px; }
        @media (max-width: 768px) {
            .sciam-title { font-size: 24px; }
            .sciam-text { font-size: 18px; }
            .sciam-inline-image {
                float: none;
                width: 100%;
                max-height: 320px;
                margin: 0 0 14px 0;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    title_options = ["すべて"] + [str(x) for x in df["title"].dropna().astype(str).tolist() if str(x).strip()]
    c1, c2, c3, c4 = st.columns([2.0, 2.0, 1.2, 1.5])
    with c1:
        selected_title = st.selectbox("Article", title_options, index=0, key="sciam_title_select")
    with c2:
        keyword = st.text_input("検索", placeholder="例: ants / moon / compass", key="sciam_keyword")
    with c3:
        show_image = st.checkbox("画像を表示", value=True, key="sciam_show_image")
    with c4:
        show_japanese = st.toggle("日本語の翻訳を表示", value=False, key="sciam_show_japanese")

    view = df.copy()
    if selected_title != "すべて":
        view = view[view["title"] == selected_title]
    if keyword:
        k = keyword.lower().strip()
        view = view[
            view["title"].astype(str).str.lower().str.contains(k, na=False)
            | view["subtitle"].astype(str).str.lower().str.contains(k, na=False)
            | view["content"].astype(str).str.lower().str.contains(k, na=False)
            | view["content_ja"].astype(str).str.lower().str.contains(k, na=False)
        ]

    if view.empty:
        st.info("この条件で表示できる scientificamerican.com の記事がありません。")
        return

    export = view.drop(columns=["image"], errors="ignore").copy()
    st.download_button(
        "scientificamerican.com CSVをダウンロード",
        export.to_csv(index=False).encode("utf-8-sig"),
        file_name="scientificamerican_articles_bilingual.csv",
        mime="text/csv",
    )

    c_total, c_show, c_db = st.columns(3)
    c_total.metric("全記事数", len(df))
    c_show.metric("表示記事数", len(view))
    c_db.metric("DB", str(view["source_db"].iloc[0]) if "source_db" in view.columns and not view.empty else "-")

    passitan_index = build_passitan_word_index()
    if passitan_index:
        st.caption("緑色の単語は、英検準1級・英検1級のパス単DBに存在する単語です。クリックするとパス単画面へ移動します。")

    for _, row in view.iterrows():
        article_id = int(row.get("id", 0) or 0)
        title = str(row.get("title", "") or "Untitled")
        subtitle = str(row.get("subtitle", "") or "")
        content = str(row.get("content", "") or "")
        content_ja = str(row.get("content_ja", "") or "")
        image_uri = scientificamerican_image_data_uri(row.get("image")) if show_image else ""
        body_html = render_scientificamerican_text(content, keyword=keyword, passitan_index=passitan_index)
        image_html = f'<img class="sciam-inline-image" src="{image_uri}" alt="{html.escape(title)}">' if image_uri else ""
        jp_html = render_scientificamerican_text(content_ja, keyword=keyword, passitan_index={}) if content_ja else ""

        st.markdown('<div class="sciam-card">', unsafe_allow_html=True)
        st.markdown(
            f'<span class="sciam-meta">scientificamerican.com</span>'
            f'<span class="sciam-meta">Article ID {article_id}</span>'
            f'<span class="sciam-meta">{html.escape(str(row.get("source_db", "")))}</span>',
            unsafe_allow_html=True,
        )
        st.markdown(f'<div class="sciam-title">{html.escape(title)}</div>', unsafe_allow_html=True)
        if subtitle:
            st.markdown(f'<div class="sciam-subtitle">{html.escape(subtitle)}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="sciam-scroll"><div class="sciam-text">{image_html}{body_html}<div class="sciam-clear"></div></div></div>',
            unsafe_allow_html=True,
        )
        if show_japanese:
            if jp_html:
                st.markdown(
                    f'<div class="sciam-jp-box"><div class="sciam-jp-title">日本語の翻訳</div>{jp_html}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.info("このArticleには日本語翻訳 content_ja がありません。")
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

    apply_passitan_jump_from_query()
    df = load_questions()
    page, selected, keyword, question_submenu, question_grade = sidebar_filters(df)
    fdf = apply_filter(df, selected, keyword)
    if page == "🏠 Overview":
        overview(fdf)
    elif page == "📚 試験問題":
        list_page(fdf, submenu=question_submenu or "Vocabulary", selected_grade=question_grade or "英検準1級")
    elif page == "🧠 Quiz":
        quiz_page(fdf)
    elif page == "📗 パス単":
        passitan_page()
    elif page == "🧪 パス単テスト":
        passitan_test_page()
    elif page == "🧩 単語整理":
        vocab_strategy_page()
    elif page == "📕 TOEFL-5600":
        toefl_5600_page()
    elif page == "📙 TOEFL-KMF-word":
        toefl_kmf_word_page()
    elif page == "🔬 scientificamerican.com":
        scientificamerican_page()
    elif page == "🌟 special-lesson":
        special_lesson_page()
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
