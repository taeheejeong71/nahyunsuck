import html
import hashlib
import hmac
import secrets
import re
import time
import calendar
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="내 용돈 연구소", page_icon="◈", layout="wide", initial_sidebar_state="auto")
DB_PATH = Path(__file__).with_name("expenses.db")
CATEGORIES = ["식비", "간식", "교통", "쇼핑", "문화·취미", "학용품", "기타"]
FIELDS = ["id", "spent_on", "item", "category", "amount", "memo"]
COLORS = dict(zip(CATEGORIES, ["#1751D0", "#E2661E", "#0E9E8F", "#C08A00", "#D95D8F", "#2E7D32", "#9117D0"]))


def money(value):
    return f"{int(value):,}원"


def esc(value):
    return html.escape(str(value), quote=True)


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            salt TEXT NOT NULL, password_hash TEXT NOT NULL, created_at REAL NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, spent_on TEXT NOT NULL,
            item TEXT NOT NULL, category TEXT NOT NULL,
            amount INTEGER NOT NULL CHECK(amount > 0), memo TEXT DEFAULT '',
            user_id INTEGER REFERENCES users(id))""")
        columns = {r[1] for r in conn.execute("PRAGMA table_info(expenses)")}
        if "user_id" not in columns:
            conn.execute("ALTER TABLE expenses ADD COLUMN user_id INTEGER REFERENCES users(id)")
        conn.execute("CREATE INDEX IF NOT EXISTS expenses_user_idx ON expenses(user_id)")
        conn.execute("""CREATE TABLE IF NOT EXISTS monthly_budgets (
            user_id INTEGER NOT NULL REFERENCES users(id), month TEXT NOT NULL,
            amount INTEGER NOT NULL CHECK(amount >= 0),
            PRIMARY KEY(user_id, month))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS login_limits (
            username TEXT PRIMARY KEY, failures INTEGER NOT NULL, blocked_until REAL NOT NULL)""")
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    return conn


def password_digest(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 600000).hex()


def register_user(username, password):
    username = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{3,32}", username):
        raise ValueError("아이디는 영문 소문자·숫자·밑줄로 3~32자 입력하세요.")
    if not 5 <= len(password) <= 128:
        raise ValueError("비밀번호는 5~128자로 입력하세요.")
    salt = secrets.token_hex(16)
    digest = password_digest(password, salt)
    with closing(get_connection()) as conn:
        with conn:
            try:
                conn.execute("INSERT INTO users(username,salt,password_hash,created_at) VALUES (?,?,?,?)",
                             (username, salt, digest, time.time()))
            except sqlite3.IntegrityError:
                raise ValueError("사용할 수 없는 아이디입니다. 다른 아이디를 입력하세요.") from None


def authenticate(username, password):
    username = username.strip().lower()[:128]
    now = time.time()
    with closing(get_connection()) as conn:
        # Serial transaction prevents simultaneous attempts bypassing the counter.
        conn.execute("BEGIN IMMEDIATE")
        limit = conn.execute("SELECT failures, blocked_until FROM login_limits WHERE username=?", (username,)).fetchone()
        if limit and limit[1] > now:
            conn.rollback()
            return None
        user = conn.execute("SELECT id,username,salt,password_hash FROM users WHERE username=?", (username,)).fetchone()
        salt = user[2] if user else "0" * 32
        actual = password_digest(password[:129], salt)
        valid = hmac.compare_digest(actual, user[3] if user else "0" * 64) and len(password) <= 128
        if valid and user:
            conn.execute("DELETE FROM login_limits WHERE username=?", (username,))
            conn.commit()
            return {"id": int(user[0]), "username": user[1], "expires": now + 43200}
        failures = (limit[0] if limit and limit[1] == 0 else 0) + 1
        blocked = now + 300 if failures >= 5 else 0
        conn.execute("INSERT INTO login_limits VALUES (?,?,?) ON CONFLICT(username) DO UPDATE SET failures=excluded.failures, blocked_until=excluded.blocked_until",
                     (username, failures, blocked))
        conn.commit()
        return None


def current_user_id():
    auth = st.session_state.get("auth")
    if not auth or auth.get("expires", 0) <= time.time():
        raise PermissionError("로그인이 필요합니다.")
    return int(auth["id"])


def logout():
    st.session_state.clear()
    st.rerun()


@st.dialog("로그아웃 확인")
def confirm_logout_dialog():
    st.write("정말 로그아웃하시겠습니까?")
    st.caption("저장한 기록은 유지됩니다.")
    cancel, confirm = st.columns(2)
    if cancel.button("취소", key="logout_cancel", use_container_width=True):
        st.rerun()
    if confirm.button("로그아웃", key="logout_confirm", type="primary", use_container_width=True):
        logout()


def login_screen():
    st.markdown("""<style>
    .st-key-auth_shell {max-width:440px;margin:clamp(8px,5vh,48px) auto 0;padding:28px 26px;background:#FDFDFF;border:1px solid #E2E6F0;border-radius:20px;}
    .st-key-auth_shell .auth-brand {font-size:26px;font-weight:800;letter-spacing:-1px;color:#17283b;line-height:1.5;margin-bottom:4px;}
    .st-key-auth_shell .auth-tagline {font-size:14px;color:#64748b;line-height:1.6;margin-bottom:22px;}
    .st-key-auth_shell [data-testid="stForm"] {padding:12px 0 0;border:0;background:transparent;}
    .st-key-auth_shell [role="radiogroup"] {display:flex;gap:8px;padding:5px;background:#F2F4F7;border-radius:12px;}
    .st-key-auth_shell [role="radiogroup"] label {flex:1;justify-content:center;margin:0;padding:10px 12px;border-radius:9px;}
    .st-key-auth_shell [role="radiogroup"] label:has(input:checked) {background:#FDFDFF;color:#1751D0;box-shadow:0 1px 4px #17283b12;}
    .st-key-auth_shell [role="radiogroup"] label > div:first-child {display:none;}
    .st-key-auth_shell [data-testid="stFormSubmitButton"] button {min-height:48px;margin-top:10px;font-weight:700;}
    @media(max-width:600px) {.st-key-auth_shell {margin:8px auto 0;padding:24px 18px;border-radius:16px;}}
    </style>""", unsafe_allow_html=True)
    with st.container(key="auth_shell"):
        st.markdown('<div class="auth-brand">내 용돈 연구소</div><div class="auth-tagline">기록은 간단하게, 소비는 똑똑하게.</div>', unsafe_allow_html=True)
        mode = st.radio("접속 방식", ["로그인", "회원가입"], horizontal=True, label_visibility="collapsed", key="auth_mode")
        if "auth_notice" in st.session_state:
            st.success(st.session_state.pop("auth_notice"))
        with st.form(f"auth_form_{mode}", clear_on_submit=False):
            username = st.text_input("아이디", max_chars=32, placeholder="아이디 입력" if mode == "로그인" else "소문자·숫자·_ 3~32자")
            password = st.text_input("비밀번호", type="password", max_chars=128, placeholder="비밀번호 입력" if mode == "로그인" else "5자 이상")
            if mode == "회원가입":
                confirmation = st.text_input("비밀번호 확인", type="password", max_chars=128, placeholder="비밀번호 다시 입력")
            submitted = st.form_submit_button("로그인" if mode == "로그인" else "계정 만들기", type="primary", use_container_width=True)
        if submitted:
            try:
                if mode == "회원가입":
                    if password != confirmation:
                        st.error("비밀번호가 일치하지 않습니다.")
                    else:
                        with st.spinner("계정을 안전하게 만드는 중…"):
                            register_user(username, password)
                        st.session_state["auth_notice"] = "가입했습니다. 로그인으로 전환해 접속하세요."
                        st.rerun()
                else:
                    with st.spinner("로그인 확인 중…"):
                        auth = authenticate(username, password)
                    if auth:
                        st.session_state["auth"] = auth
                        st.session_state["page"] = "홈"
                        st.rerun()
                    else:
                        st.error("아이디·비밀번호가 올바르지 않거나 잠시 제한되었습니다. 5회 실패하면 5분 후 다시 시도하세요.")
            except ValueError as exc:
                st.error(str(exc))
            except sqlite3.Error:
                st.error("계정 저장소에 연결하지 못했습니다. 잠시 후 다시 시도하세요.")


def load_data():
    with closing(get_connection()) as conn:
        frame = pd.read_sql_query("SELECT id, spent_on, item, category, amount, memo FROM expenses WHERE user_id=? ORDER BY spent_on DESC, id DESC", conn, params=(current_user_id(),))
    frame = frame.reindex(columns=FIELDS)
    frame["spent_on"] = pd.to_datetime(frame["spent_on"], errors="coerce").dt.date
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce").fillna(0).astype("int64")
    for col in ["item", "category", "memo"]:
        frame[col] = frame[col].fillna("").astype(str)
    return frame


def delete_records(record_ids=None):
    uid = current_user_id()
    with closing(get_connection()) as conn:
        with conn:
            if record_ids is None:
                result = conn.execute("DELETE FROM expenses WHERE user_id=?", (uid,))
            else:
                ids = list(dict.fromkeys(int(i) for i in record_ids))
                if not ids:
                    return 0
                count = 0
                for rid in ids:
                    count += conn.execute("DELETE FROM expenses WHERE user_id=? AND id=?", (uid, rid)).rowcount
                return count
            return result.rowcount


def update_expense(record_id, day, item, category, amount, memo):
    if not item.strip() or not 1 <= int(amount) <= 100000000 or day > date.today():
        raise ValueError("사용한 곳, 금액, 날짜를 확인해 주세요.")
    with closing(get_connection()) as conn:
        with conn:
            return conn.execute("UPDATE expenses SET spent_on=?,item=?,category=?,amount=?,memo=? WHERE id=? AND user_id=?",
                (day.isoformat(), item.strip(), category, int(amount), memo.strip(), int(record_id), current_user_id())).rowcount


@st.dialog("기록 수정")
def edit_record_dialog(record_id):
    owned = load_data()
    matches = owned.loc[owned["id"].eq(record_id)]
    if matches.empty:
        st.info("기록이 삭제되었거나 접근할 수 없습니다.")
        return
    row = matches.iloc[0]
    with st.form(f"edit_dialog_{record_id}"):
        item = st.text_input("사용한 곳", value=row["item"], max_chars=100)
        amount = st.number_input("금액 (원)", min_value=1, max_value=100000000, value=max(1,min(100000000,int(row["amount"]))), step=100)
        day = st.date_input("날짜", value=row["spent_on"], max_value=max(date.today(), row["spent_on"]))
        options = CATEGORIES if row["category"] in CATEGORIES else CATEGORIES + [row["category"]]
        category = st.selectbox("종류", options, index=options.index(row["category"]))
        memo = st.text_input("메모", value=row["memo"], max_chars=500)
        if st.form_submit_button("변경사항 저장", type="primary", use_container_width=True):
            try:
                with st.spinner("저장 중…"):
                    count = update_expense(record_id, day, item, category, amount, memo)
                st.session_state["flash"] = "기록을 수정했습니다." if count else "기록을 찾지 못했습니다."
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
            except sqlite3.Error:
                st.error("저장하지 못했습니다. 다시 시도해 주세요.")


@st.dialog("삭제 확인")
def delete_records_dialog(record_ids=None):
    owned = load_data()
    all_records = record_ids is None
    targets = owned if all_records else owned.loc[owned["id"].isin(record_ids)]
    if targets.empty:
        st.info("삭제할 기록이 없습니다.")
        return
    st.warning(f"{'본인의 전체' if all_records else '선택한'} 기록 {len(targets)}건 · {money(targets['amount'].sum())}을 삭제합니다. 복구할 수 없습니다.")
    if all_records:
        st.caption("검색·필터에 숨겨진 기록도 삭제합니다. 계정과 월 예산은 유지합니다.")
        phrase = st.text_input("확인을 위해 ‘전체삭제’를 입력하세요")
        enabled = phrase == "전체삭제"
    else:
        enabled = True
    if st.button("영구 삭제 확정", type="primary", disabled=not enabled, use_container_width=True):
        try:
            with st.spinner("삭제 중…"):
                count = delete_records(None if all_records else targets["id"].tolist())
            st.session_state["flash"] = f"{count}건을 삭제했습니다."
            st.rerun()
        except sqlite3.Error:
            st.error("삭제하지 못했습니다. 다시 시도해 주세요.")


def month_name(value):
    if value == "전체":
        return "전체 기간"
    period = pd.Period(value, freq="M")
    now = pd.Period(date.today(), freq="M")
    tag = " · 이번 달" if period == now else " · 지난달" if period == now - 1 else ""
    return f"{period.year}년 {period.month}월{tag}"


def move_month(offset=0, reset=False):
    now = pd.Period(date.today(), freq="M")
    old = st.session_state.get("active_month", str(now))
    period = now if reset else pd.Period(old, freq="M") + offset
    st.session_state["active_month"] = str(min(period, now))
    st.session_state["ledger_page"] = 0


def reset_ledger_filters():
    st.session_state["ledger_query"] = ""
    st.session_state["ledger_category"] = "전체"
    st.session_state["ledger_all_months"] = False
    st.session_state["ledger_page"] = 0


def filter_records(frame, month="전체", category="전체", query=""):
    # A typed Boolean mask preserves columns even when there are zero rows.
    mask = pd.Series(True, index=frame.index, dtype=bool)
    if month != "전체":
        mask &= pd.to_datetime(frame["spent_on"], errors="coerce").dt.strftime("%Y-%m").eq(month)
    if category != "전체":
        mask &= frame["category"].eq(category)
    if query.strip():
        mask &= (frame["item"].str.contains(query.strip(), case=False, regex=False, na=False)
                 | frame["memo"].str.contains(query.strip(), case=False, regex=False, na=False))
    return frame.loc[mask.astype(bool), FIELDS].copy()


def add_expense(day, item, category, amount, memo):
    with closing(get_connection()) as conn:
        with conn:
            conn.execute("INSERT INTO expenses (spent_on,item,category,amount,memo,user_id) VALUES (?,?,?,?,?,?)",
                         (day.isoformat(), item.strip(), category, int(amount), memo.strip(), current_user_id()))


def delete_expense(record_id):
    with closing(get_connection()) as conn:
        with conn:
            conn.execute("DELETE FROM expenses WHERE id=? AND user_id=?", (int(record_id), current_user_id()))


def table_data(frame):
    return frame[["spent_on", "item", "category", "amount", "memo"]].rename(
        columns={"spent_on": "날짜", "item": "사용한 곳", "category": "종류", "amount": "금액(원)", "memo": "메모"})


def cards(frame):
    for row in frame.itertuples():
        st.markdown(f'<div class="entry"><div class="entry-main"><strong>{esc(row.item)}</strong><small>{esc(row.spent_on)} · {esc(row.category)}</small></div><b>{money(row.amount)}</b></div>', unsafe_allow_html=True)


def get_budget(month):
    with closing(get_connection()) as conn:
        row = conn.execute("SELECT amount FROM monthly_budgets WHERE user_id=? AND month=?",
                           (current_user_id(), month)).fetchone()
    return int(row[0]) if row else None


def save_budget(month, amount):
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month):
        raise ValueError("올바르지 않은 예산 월입니다.")
    if not isinstance(amount, int) or isinstance(amount, bool) or not 0 <= amount <= 1000000000:
        raise ValueError("예산은 0~10억 원의 정수로 입력하세요.")
    with closing(get_connection()) as conn:
        with conn:
            conn.execute("""INSERT INTO monthly_budgets(user_id,month,amount) VALUES (?,?,?)
                ON CONFLICT(user_id,month) DO UPDATE SET amount=excluded.amount""",
                (current_user_id(), month, amount))


def budget_numbers(budget, spent, today):
    days = calendar.monthrange(today.year, today.month)[1] - today.day + 1
    remaining = int(budget) - int(spent)
    return remaining, max(0, remaining) // days, days


def budget_panel(month, month_frame, today):
    try:
        budget = get_budget(month)
    except sqlite3.Error:
        st.error("예산을 불러오지 못했습니다. 잠시 후 다시 시도하세요.")
        return
    spent = int(month_frame["amount"].sum())
    if budget is not None:
        remaining, daily, days = budget_numbers(budget, spent, today)
        label = "이번 달 초과 금액" if remaining < 0 else "이번 달 남은 돈"
        state = "over" if remaining < 0 else ""
        st.markdown(f'<section class="budget-box {state}"><div class="budget-main"><small>{label}</small><strong>{money(abs(remaining))}</strong><span>월 예산 {money(budget)} · 사용 {money(spent)}</span></div><div class="budget-daily"><small>하루 사용 가능액</small><strong>{money(daily)}</strong><span>오늘 포함 {days}일 기준</span></div></section>', unsafe_allow_html=True)
        if remaining < 0:
            st.caption("예산을 초과했습니다. 하루 사용 가능액은 0원으로 표시합니다.")
        elif remaining == 0:
            st.caption("이번 달 예산을 모두 사용했습니다.")
    else:
        st.info("이번 달 예산을 설정하면 남은 돈과 하루 사용 가능액을 확인할 수 있습니다.")
    with st.popover("이번 달 예산 설정 / 변경", use_container_width=True):
        with st.form(f"budget_form_{current_user_id()}_{month}"):
            amount = st.number_input("월 예산 (원)", min_value=0, max_value=1000000000,
                                     value=budget if budget is not None else 300000, step=10000,
                                     key=f"budget_input_{current_user_id()}_{month}_{budget}")
            submitted = st.form_submit_button("예산 저장", type="primary", use_container_width=True)
        st.caption("오늘을 포함한 남은 일수 기준 · 월별 예산 저장")
        if submitted:
            try:
                with st.spinner("예산 저장 중…"):
                    save_budget(month, int(amount))
                st.session_state["flash"] = "이번 달 예산을 저장했습니다."
                st.rerun()
            except (sqlite3.Error, ValueError):
                st.error("예산을 저장하지 못했습니다. 다시 시도하세요.")


def summary(frame):
    total, count = int(frame["amount"].sum()), len(frame)
    avg = round(total / count) if count else 0
    st.markdown(f'<div class="stats"><div><small>총지출</small><strong>{money(total)}</strong></div><div><small>기록 수</small><strong>{count}건</strong></div><div><small>건당 평균</small><strong>{money(avg)}</strong></div></div>', unsafe_allow_html=True)


def chart(frame, kind="category"):
    if frame.empty:
        st.info("아직 기록이 없습니다.")
        return
    if kind != "category":
        monthly = frame.assign(month=pd.to_datetime(frame["spent_on"]).dt.strftime("%Y-%m")).groupby("month")["amount"].sum()
        st.dataframe(monthly.rename_axis("월").reset_index(name="금액(원)"), hide_index=True, use_container_width=True, height=245)
        return
    totals = frame.groupby("category", as_index=False)["amount"].sum().sort_values("amount", ascending=False)
    total = int(totals["amount"].sum())
    if total <= 0:
        st.info("표시할 지출 금액이 없습니다.")
        return
    pieces = totals.copy()
    palette = COLORS.copy()
    if len(pieces) > 3:
        pieces = pd.concat([pieces.head(2), pd.DataFrame([{"category": "나머지 합계", "amount": int(pieces.iloc[2:]["amount"].sum())}])], ignore_index=True)
        palette["나머지 합계"] = "#9117D0"
    fig = px.pie(pieces, names="category", values="amount", hole=.56,
                 color="category", color_discrete_map=palette)
    fig.update_traces(textinfo="none", sort=False,
                      marker=dict(line=dict(color="#FDFDFF", width=2)),
                      hovertemplate="%{label}<br>%{value:,.0f}원 · %{percent}<extra></extra>")
    fig.update_layout(height=205, margin=dict(t=8, b=8, l=8, r=8), showlegend=False,
                      paper_bgcolor="#FDFDFF", plot_bgcolor="#FDFDFF",
                      font=dict(color="#1E2433", size=14),
                      annotations=[dict(text="총지출", x=.5, y=.5, showarrow=False, font=dict(size=16, color="#1E2433"))])
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False})
    rows = []
    for row in pieces.itertuples():
        rows.append(f'<div class="pie-row"><span class="pie-name"><i style="background:{palette.get(row.category, "#9117D0")}"></i>{esc(row.category)}</span><strong>{money(row.amount)}</strong><span>{row.amount/total:.1%}</span></div>')
    st.markdown('<div class="pie-legend">'+''.join(rows)+'</div>', unsafe_allow_html=True)
    if len(totals) > 3:
        with st.popover("나머지 종류별 금액 보기", use_container_width=True):
            st.dataframe(totals.iloc[2:].rename(columns={"category":"종류", "amount":"금액(원)"}), hide_index=True, use_container_width=True, height=210)



st.markdown('''<style>
.stApp { background:#F7F8FA; color:#1E2433; }
.block-container { max-width:1140px; padding:4.5rem 2rem 1rem; }
h1,h2,h3 { color:#1E2433; letter-spacing:-.04em; }
h1 { font-size:28px !important; padding:.15rem 0 .35rem !important; margin:0 0 4px !important; line-height:1.4 !important; overflow:visible !important; }
h3 { font-size:17px !important; padding:0 !important; margin:0 0 12px !important; }
[data-testid="stSidebar"] { background:#FDFDFF; border-right:1px solid #E2E6F0; min-width:230px; max-width:270px; }
[data-testid="stSidebar"] .block-container { padding:1rem; }
[data-testid="stSidebarUserContent"] { padding-top:2rem !important; }
[data-testid="stSidebar"] [data-testid="stButton"] button { width:100%; min-height:62px; margin:3px 0; padding:14px 18px; justify-content:flex-start; border:0; border-radius:12px; }
[data-testid="stSidebar"] [data-testid="stButton"] button p { font-size:17px; font-weight:700; }
[data-testid="stSidebar"] button[kind="secondary"] { background:#F2F4F7; color:#303B50; }
button[kind="primary"],button[kind="primaryFormSubmit"] { background:#1751D0 !important; border-color:#1751D0 !important; color:white !important; }
.brand { font-size:21px; font-weight:850; margin:5px 0 24px; color:#1E2433; }
.subtitle { color:#505A74; font-size:13px; margin-bottom:16px; }
.stats { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin:14px 0 20px; }
.stats > div { padding:17px 20px; background:#FDFDFF; border:1px solid #E2E6F0; border-radius:14px; min-width:0; }
.stats small { display:block; color:#505A74; font-size:12px; }
.stats strong { display:block; font-size:clamp(20px,2.4vw,28px); margin-top:6px; letter-spacing:-.04em; overflow-wrap:anywhere; }
.entry { display:flex; justify-content:space-between; align-items:center; gap:10px; padding:13px 0; border-bottom:1px solid #E2E6F0; }
.entry-main { min-width:0; }.entry strong { font-size:14px; display:block; overflow-wrap:anywhere; }
.entry small { display:block; font-size:11px; color:#505A74; margin-top:4px; }.entry b { white-space:nowrap; font-size:14px; }
[data-testid="stForm"] { background:#FDFDFF; border-radius:14px; padding:18px; }
[data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] { color:#1E2433; }
button { touch-action:manipulation; }
[data-testid="stButton"] button,[data-testid="stFormSubmitButton"] button,[data-testid="stDownloadButton"] button { min-height:44px; border-radius:10px; }
input,textarea { font-size:16px !important; color:#1E2433 !important; -webkit-text-fill-color:#1E2433 !important; }
[data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"] > div { background:#FDFDFF !important; color:#1E2433 !important; }
[data-testid="stHeader"] { background:#F7F8FA; }
[data-testid="stCaptionContainer"] { color:#505A74; }
.pie-legend { background:#FDFDFF; border-radius:12px; padding:4px 12px; }
.pie-row { display:grid; grid-template-columns:minmax(0,1fr) auto 60px; gap:10px; align-items:center; min-height:42px; color:#1E2433; font-size:14px; }
.pie-row > span:last-child { text-align:right; color:#505A74; font-variant-numeric:tabular-nums; }
.pie-row strong { font-size:14px; font-variant-numeric:tabular-nums; }
.pie-name { display:flex; gap:8px; align-items:center; overflow-wrap:anywhere; }
.pie-name i { display:block; width:10px; height:10px; border-radius:50%; flex-shrink:0; }
[data-testid="stSpinner"] { padding:14px 16px; border:1px solid #D7E2FA; border-radius:12px; background:#EDF3FF; color:#1E2433; }
.budget-box { display:grid; grid-template-columns:1.3fr 1fr; gap:12px; background:#EDF3FF; border:1px solid #D7E2FA; padding:16px 18px; border-radius:14px; margin:8px 0; }
.budget-box.over { background:#FFF2F1; border-color:#E6C3C6; }
.budget-box small { display:block; font-size:12px; color:#505A74; }
.budget-box strong { display:block; font-size:27px; line-height:1.5; color:#1E2433; overflow-wrap:anywhere; }
.budget-box span { display:block; font-size:11px; color:#505A74; line-height:1.6; }
.budget-daily { border-left:1px solid #CDD3E0; padding-left:16px; }
@media(max-width:640px) {
 .budget-box { padding:12px; gap:8px; }
 .budget-box strong { font-size:21px; }
 .budget-daily { padding-left:10px; }
 .block-container { padding:4.25rem .9rem 1rem; }
 h1 { font-size:23px !important; }
 .stats { gap:6px; margin:10px 0 14px; }
 .stats > div { padding:12px 8px; border-radius:10px; }
 .stats strong { font-size:18px; } .stats small { font-size:11px; }
 [data-testid="stHorizontalBlock"] { flex-wrap:wrap !important; gap:12px !important; }
 [data-testid="stHorizontalBlock"] > [data-testid="stColumn"], [data-testid="stHorizontalBlock"] > [data-testid="column"] { flex:1 1 100% !important; min-width:0 !important; }
 [data-testid="stSidebar"] { min-width:230px; }
}
</style>''', unsafe_allow_html=True)

auth = st.session_state.get("auth")
if auth and auth.get("expires", 0) <= time.time():
    st.session_state.clear()
    auth = None
if not auth:
    login_screen()
    st.stop()

if "page" not in st.session_state:
    st.session_state["page"] = "홈"
with st.sidebar:
    st.markdown('<div class="brand">◈ 내 용돈 연구소</div>', unsafe_allow_html=True)
    for label in ["홈", "기록하기", "기록장", "분석"]:
        if st.button(label, key=f"menu_{label}", type="primary" if st.session_state["page"] == label else "secondary", use_container_width=True):
            st.session_state["page"] = label
            st.rerun()
    st.caption(f"로그인: {st.session_state['auth']['username']}")
    if st.button("로그아웃", key="logout", use_container_width=True):
        confirm_logout_dialog()
page = st.session_state["page"]
st.title({"홈": "내 용돈 연구소", "기록하기": "지출 기록하기", "기록장": "지출 기록장", "분석": "소비 분석"}[page])
if page == "홈":
    st.markdown('<div class="subtitle">지출 기록부터 소비 분석까지</div>', unsafe_allow_html=True)
if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"))
with st.spinner("기록 불러오는 중…"):
    try:
        df = load_data()
    except (sqlite3.Error, pd.errors.DatabaseError, ValueError) as exc:
        st.error("데이터베이스를 읽지 못했습니다. 기존 expenses.db를 백업한 뒤 테이블 구조와 저장 권한을 확인해 주세요.")
        st.stop()
invalid_count = int(df["spent_on"].isna().sum())
df = df.loc[df["spent_on"].notna(), FIELDS].copy()
if invalid_count:
    st.warning(f"날짜가 잘못된 {invalid_count}건은 표시에서 제외했습니다. 원본 기록은 삭제하지 않았습니다.")
today = date.today()
current_month = today.strftime("%Y-%m")
if page in ["홈", "기록장"]:
    earliest = pd.to_datetime(df["spent_on"], errors="coerce").min()
    start = min(pd.Period(earliest, freq="M"), pd.Period(current_month, freq="M") - 12) if pd.notna(earliest) else pd.Period(current_month, freq="M") - 12
    month_options = [str(p) for p in pd.period_range(start, current_month, freq="M")][::-1]
    if st.session_state.get("active_month") not in month_options:
        st.session_state["active_month"] = current_month
    nav_prev, nav_month, nav_next = st.columns([1, 3, 1])
    nav_prev.button("←", help="이전 달", on_click=move_month, args=(-1,), disabled=st.session_state["active_month"] == month_options[-1], use_container_width=True)
    nav_month.selectbox("조회 기준 월", month_options, format_func=month_name, key="active_month", label_visibility="collapsed")
    nav_next.button("→", help="다음 달", on_click=move_month, args=(1,), disabled=st.session_state["active_month"] == current_month, use_container_width=True)
    if st.session_state["active_month"] != current_month:
        st.button("이번 달로 돌아가기", on_click=move_month, kwargs={"reset": True})
active_month = st.session_state.get("active_month", current_month)
month_df = filter_records(df, month=active_month)

if page == "홈":
    if active_month == current_month:
        budget_panel(current_month, month_df, today)
    else:
        st.caption("마감된 월 · 해당 월 전체 기록 기준")
        past_budget = get_budget(active_month)
        if past_budget is not None:
            balance = past_budget - int(month_df["amount"].sum())
            st.metric("해당 월 예산 대비 잔액" if balance >= 0 else "해당 월 초과 지출", money(abs(balance)))
        else:
            st.caption("이 달에 설정된 예산은 없습니다.")
    summary(month_df)
    # One panel at a time avoids stacking full sections on narrow screens.
    home_mode = st.radio("보기", ["종류별 지출", "최근 기록"], horizontal=True, label_visibility="collapsed")
    if home_mode == "종류별 지출":
        chart(month_df)
    elif month_df.empty:
        st.info("선택한 달의 기록이 없습니다.")
    else:
        cards(month_df.head(4))
        st.caption("선택한 달의 최근 4건 · 전체 내역은 기록장에서 확인")

elif page == "기록하기":
    # Clear only after a successful transaction; errors retain the user's draft.
    if st.session_state.pop("reset_expense_form", False):
        for key in ("new_day", "new_item", "new_amount", "new_category", "new_memo"):
            st.session_state.pop(key, None)
    with st.form("expense_form", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            day = st.date_input("날짜", value=today, max_value=today, key="new_day")
            item = st.text_input("사용한 곳", placeholder="예: 점심 김밥", max_chars=100, key="new_item")
        with c2:
            amount = st.number_input("금액 (원)", min_value=1, max_value=100000000, value=3000, step=500, key="new_amount")
            category = st.selectbox("종류", CATEGORIES, key="new_category")
        memo = st.text_input("메모 · 선택", max_chars=500, key="new_memo")
        submitted = st.form_submit_button("저장하기", type="primary", use_container_width=True)
        if submitted:
            if not item.strip():
                st.error("사용한 곳을 입력해 주세요.")
            else:
                try:
                    with st.spinner("저장 중…"):
                        add_expense(day, item, category, amount, memo)
                    st.session_state["reset_expense_form"] = True
                    st.session_state["flash"] = f"저장했습니다 · {item.strip()} {money(amount)}"
                    st.rerun()
                except sqlite3.Error:
                    st.error("저장하지 못했습니다. 입력한 내용은 유지됩니다.")

elif page == "기록장":
    # One search field, optional filters, direct actions on each record.
    st.markdown("""<style>
    [data-testid="stVerticalBlockBorderWrapper"] {border-radius:14px;}
    .ledger-item {font-size:16px;font-weight:650;color:#17283b;overflow-wrap:anywhere;margin:0 0 5px;line-height:1.5;}
    .ledger-meta {font-size:13px;color:#64748b;line-height:1.6;overflow-wrap:anywhere;}
    .ledger-price {font-size:18px;font-weight:750;font-variant-numeric:tabular-nums;line-height:1.6;color:#17283b;}
    </style>""", unsafe_allow_html=True)
    query = st.text_input("기록 검색", placeholder="사용한 곳이나 메모로 검색", label_visibility="collapsed", key="ledger_query")
    with st.popover("종류 · 조회 범위", use_container_width=True):
        all_months = st.checkbox("전체 기간 보기", key="ledger_all_months")
        selected_month = "전체" if all_months else active_month
        selected_cat = st.selectbox("종류", ["전체"] + CATEGORIES, key="ledger_category")
        st.button("검색·필터 초기화", on_click=reset_ledger_filters, use_container_width=True)
    view = filter_records(df, selected_month, selected_cat, query)
    st.markdown(f'<div class="stats" style="grid-template-columns:repeat(2,minmax(0,1fr));margin:8px 0 16px"><div><small>조회된 기록</small><strong>{len(view):,}건</strong></div><div><small>총 지출</small><strong>{money(view["amount"].sum())}</strong></div></div>', unsafe_allow_html=True)
    selection_mode = st.session_state.get("ledger_selection_mode", False)
    if view.empty:
        st.info("조건에 맞는 기록이 없습니다. 검색어나 필터를 변경해 보세요." if not df.empty else "아직 기록이 없습니다. ‘기록하기’에서 첫 지출을 남겨 보세요.")
    else:
        per_page = 5
        page_count = (len(view) + per_page - 1) // per_page
        signature = (query, selected_month, selected_cat, tuple(int(i) for i in view["id"]))
        if st.session_state.get("ledger_signature") != signature:
            st.session_state["ledger_signature"] = signature
            st.session_state["ledger_page"] = 0
        index = min(max(0, st.session_state.get("ledger_page", 0)), page_count - 1)
        visible = view.iloc[index * per_page:(index + 1) * per_page]
        last_month = None
        for row in visible.itertuples():
            record_month = row.spent_on.strftime("%Y-%m")
            if selected_month == "전체" and record_month != last_month:
                st.markdown(f"**{month_name(record_month)}**")
                last_month = record_month
            with st.container(border=True):
                st.markdown(f'<div class="ledger-item">{html.escape(str(row.item))}</div><div class="ledger-meta">{row.spent_on:%Y.%m.%d} · {html.escape(str(row.category))}</div>', unsafe_allow_html=True)
                left, right = st.columns([2,1])
                left.markdown(f'<div class="ledger-price">{money(row.amount)}</div>', unsafe_allow_html=True)
                if selection_mode:
                    right.checkbox("선택", key=f"ledger_pick_{int(row.id)}")
                elif right.button("수정", key=f"ledger_edit_{int(row.id)}", use_container_width=True):
                    edit_record_dialog(int(row.id))
                if row.memo:
                    st.caption(str(row.memo))
        if page_count > 1:
            prev, label, nxt = st.columns([1,1,1])
            if prev.button("← 이전", disabled=index == 0, use_container_width=True):
                st.session_state["ledger_page"] = index - 1
                st.rerun()
            label.caption(f"{index + 1} / {page_count}")
            if nxt.button("다음 →", disabled=index == page_count - 1, use_container_width=True):
                st.session_state["ledger_page"] = index + 1
                st.rerun()
    st.divider()
    mode_col, danger_col = st.columns(2)
    mode_col.toggle("여러 건 선택", key="ledger_selection_mode")
    if danger_col.button("전체삭제", disabled=df.empty, use_container_width=True, help="필터와 관계없이 본인 기록 전체 삭제"):
        delete_records_dialog()
    if selection_mode and not view.empty:
        picked = [int(i) for i in view["id"] if st.session_state.get(f"ledger_pick_{int(i)}", False)]
        if st.button(f"선택한 {len(picked)}건 삭제", type="primary", disabled=not picked, use_container_width=True):
            delete_records_dialog(picked)

else:
    if df.empty:
        st.info("분석할 기록이 없습니다.")
    else:
        chart(df, kind="monthly")
