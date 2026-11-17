import html
import hashlib
import hmac
import secrets
import re
import time
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
    if not 10 <= len(password) <= 128:
        raise ValueError("비밀번호는 10~128자로 입력하세요.")
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


def login_screen():
    st.markdown('<h1>내 용돈 연구소</h1><div class="subtitle">지출 기록부터 소비 분석까지 · 나만의 용돈 관리</div>', unsafe_allow_html=True)
    mode = st.radio("시작하기", ["로그인", "회원가입"], horizontal=True, label_visibility="collapsed")
    if "auth_notice" in st.session_state:
        st.success(st.session_state.pop("auth_notice"))
    with st.form("auth_form", clear_on_submit=True):
        username = st.text_input("아이디", max_chars=32, placeholder="영문 소문자·숫자·밑줄, 3~32자")
        password = st.text_input("비밀번호", type="password", max_chars=128, placeholder="10자 이상")
        if mode == "회원가입":
            confirmation = st.text_input("비밀번호 확인", type="password", max_chars=128)
        submitted = st.form_submit_button(mode, type="primary", use_container_width=True)
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
    st.caption("계정별로 기록을 분리합니다. 공용 기기에서는 사용 후 로그아웃하세요.")
    with st.expander("계정·저장 안내"):
        st.caption("계정과 기록은 서버의 SQLite DB에 저장됩니다. 재배포·재시작 등으로 유실될 수 있습니다. 영구 운영에는 외부 DB 연결이 필요합니다. 비밀번호 재설정·이메일 인증은 제공하지 않으므로 다른 서비스와 다른 비밀번호를 사용하세요. 이전 공용 기록은 자동 배정하지 않고 DB에 그대로 보존합니다.")


def load_data():
    with closing(get_connection()) as conn:
        frame = pd.read_sql_query("SELECT id, spent_on, item, category, amount, memo FROM expenses WHERE user_id=? ORDER BY spent_on DESC, id DESC", conn, params=(current_user_id(),))
    frame = frame.reindex(columns=FIELDS)
    frame["spent_on"] = pd.to_datetime(frame["spent_on"], errors="coerce").dt.date
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce").fillna(0).astype("int64")
    for col in ["item", "category", "memo"]:
        frame[col] = frame[col].fillna("").astype(str)
    return frame


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
        with st.expander("나머지 종류별 금액 보기"):
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
@media(max-width:640px) {
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
        logout()
    with st.expander("저장 안내"):
        st.caption("내 계정의 기록만 표시합니다. 서버 재시작·재배포로 계정과 DB가 사라질 수 있으니 CSV로 별도 보관하세요. 이전 공용 기록은 DB에 보존하며 자동 배정하지 않습니다.")
page = st.session_state["page"]
st.title({"홈": "내 용돈 연구소", "기록하기": "지출 기록하기", "기록장": "지출 기록장", "분석": "소비 분석"}[page])
st.markdown('<div class="subtitle">지출 기록부터 소비 분석까지 · 나만의 용돈 관리</div>', unsafe_allow_html=True)
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
month_df = filter_records(df, month=current_month)

if page == "홈":
    st.caption(f"{today.year}년 {today.month}월 · 오늘까지 입력한 기록")
    summary(month_df)
    # One panel at a time avoids stacking full sections on narrow screens.
    home_mode = st.radio("보기", ["종류별 지출", "최근 기록"], horizontal=True, label_visibility="collapsed")
    if home_mode == "종류별 지출":
        chart(month_df)
    elif df.empty:
        st.info("아직 기록이 없습니다. 왼쪽 메뉴의 ‘기록하기’에서 시작하세요.")
    else:
        cards(df.head(4))
        st.caption("최근 4건 · 전체 내역은 기록장에서 확인")

elif page == "기록하기":
    with st.form("expense_form", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            day = st.date_input("날짜", value=today, max_value=today)
            item = st.text_input("사용한 곳", placeholder="예: 점심 김밥", max_chars=100)
        with c2:
            amount = st.number_input("금액 (원)", min_value=1, max_value=100000000, value=3000, step=500)
            category = st.selectbox("종류", CATEGORIES)
        memo = st.text_input("메모 · 선택", max_chars=500)
        submitted = st.form_submit_button("저장하기", type="primary", use_container_width=True)
        if submitted:
            if not item.strip():
                st.error("사용한 곳을 입력해 주세요.")
            else:
                try:
                    with st.spinner("저장 중…"):
                        add_expense(day, item, category, amount, memo)
                    st.session_state["flash"] = f"저장했습니다 · {item.strip()} {money(amount)}"
                    st.rerun()
                except sqlite3.Error:
                    st.error("저장하지 못했습니다. 입력한 내용은 유지됩니다.")
    st.caption("저장 후 입력 내용은 유지됩니다. 완료 알림을 확인해 중복 저장을 피하세요.")

elif page == "기록장":
    months = sorted(pd.to_datetime(df["spent_on"], errors="coerce").dt.strftime("%Y-%m").dropna().unique().tolist(), reverse=True)
    c1, c2, c3 = st.columns([1, 1, 1.5])
    selected_month = c1.selectbox("월", ["전체"] + months)
    selected_cat = c2.selectbox("종류", ["전체"] + CATEGORIES)
    query = c3.text_input("검색", placeholder="사용한 곳 / 메모")
    view = filter_records(df, selected_month, selected_cat, query)
    st.caption(f"{len(view)}건 · 합계 {money(view['amount'].sum())}")
    if view.empty:
        st.info("표시할 기록이 없습니다.")
    else:
        mode = st.radio("보기", ["카드", "표"], horizontal=True, label_visibility="collapsed")
        if mode == "카드":
            page_count = (len(view) + 3) // 4
            number = st.selectbox("페이지 · 4건씩", range(1, page_count + 1), format_func=lambda n: f"{n} / {page_count}")
            cards(view.iloc[(number - 1) * 4:number * 4])
        else:
            st.dataframe(table_data(view), hide_index=True, use_container_width=True, height=245)
        with st.expander("다운로드 / 삭제"):
            exported = table_data(view).copy()
            for col in ["사용한 곳", "종류", "메모"]:
                exported[col] = exported[col].map(lambda v: "'" + str(v) if str(v).lstrip().startswith(("=", "+", "-", "@")) else v)
            st.download_button("CSV 다운로드", exported.to_csv(index=False).encode("utf-8-sig"), file_name=f"expenses_{today}.csv", mime="text/csv", use_container_width=True)
            labels = {int(r.id): f"#{r.id} · {r.item} · {money(r.amount)}" for r in view.itertuples()}
            rid = st.selectbox("삭제할 기록", list(labels), format_func=lambda v: labels[v])
            confirm = st.checkbox("이 기록을 삭제합니다. 되돌릴 수 없습니다.", key=f"delete_confirm_{rid}")
            if st.button("선택 기록 삭제", disabled=not confirm, use_container_width=True):
                try:
                    with st.spinner("삭제 중…"):
                        delete_expense(rid)
                    st.session_state["flash"] = "기록을 삭제했습니다."
                    st.rerun()
                except sqlite3.Error:
                    st.error("삭제하지 못했습니다. 잠시 후 다시 시도해 주세요.")

else:
    analysis_mode = st.radio("분석 항목", ["월별 지출", "종류별 지출", "다음 달 예상"], horizontal=True, label_visibility="collapsed")
    if df.empty:
        st.info("분석할 기록이 없습니다.")
    elif analysis_mode == "종류별 지출":
        chart(df)
        with st.expander("금액 표 보기"):
            st.dataframe(df.groupby("category")["amount"].sum().rename_axis("종류").reset_index(name="금액(원)"), hide_index=True, use_container_width=True, height=230)
    elif analysis_mode == "월별 지출":
        chart(df, kind="monthly")
        st.caption("이번 달은 오늘까지의 기록입니다. 기록이 없는 달은 생략합니다.")
    else:
        monthly = df.assign(month=pd.to_datetime(df["spent_on"]).dt.strftime("%Y-%m")).groupby("month")["amount"].sum()
        previous = pd.Period(current_month, freq="M") - 1
        keys = [str(previous - i) for i in range(2, -1, -1)]
        recent = monthly.reindex(keys).dropna()
        if recent.empty:
            st.info("직전 3개월의 기록이 없어 아직 예상할 수 없습니다.")
        else:
            prediction = int(round(recent.mean()))
            st.metric("다음 달 예상 지출", money(prediction))
            st.caption(f"직전 3개월 중 기록이 있는 {len(recent)}개월 평균입니다. 진행 중인 이번 달은 제외합니다. 기록 누락에 따라 실제와 다를 수 있습니다.")
            goal = st.number_input("목표 금액 (원) · 저장되지 않는 계산기", min_value=0, max_value=1000000000, value=min(1000000000, int(prediction * .9)), step=1000)
            if goal < prediction:
                st.success(f"평균보다 {money(prediction-goal)} 줄이는 목표입니다.")
            else:
                st.info("필요한 지출을 고려해 목표를 조정하세요.")
