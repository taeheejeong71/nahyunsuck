import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

# ------------------------------------------------------------
# 올인원 생산성 대시보드
# Local JSON storage. For durable multi-user cloud storage,
# connect a database such as Supabase in a later version.
# ------------------------------------------------------------
APP_DIR = Path(__file__).parent
DATA_FILE = APP_DIR / "productivity_data.json"

st.set_page_config(
    page_title="Daily — 생산성 대시보드",
    page_icon="◫",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DEFAULT_DATA = {
    "tasks": [],
    "events": [],
    "focus_sessions": [],
}

def load_data():
    if not DATA_FILE.exists():
        return DEFAULT_DATA.copy()
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        for key, value in DEFAULT_DATA.items():
            data.setdefault(key, value.copy())
        return data
    except (json.JSONDecodeError, OSError):
        return DEFAULT_DATA.copy()

def save_data():
    temp_file = DATA_FILE.with_suffix(".tmp")
    with temp_file.open("w", encoding="utf-8") as f:
        json.dump(st.session_state.data, f, ensure_ascii=False, indent=2)
    temp_file.replace(DATA_FILE)

if "data" not in st.session_state:
    st.session_state.data = load_data()
if "timer_end" not in st.session_state:
    st.session_state.timer_end = None
if "timer_total" not in st.session_state:
    st.session_state.timer_total = 25 * 60
if "timer_running" not in st.session_state:
    st.session_state.timer_running = False
if "timer_mode" not in st.session_state:
    st.session_state.timer_mode = "집중"

data = st.session_state.data

# ----------------------------- Styling -----------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800;900&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
    .stApp { background: #f5f7ff; color: #202944; }
    .block-container { max-width: 1120px; padding: 1.2rem 1.35rem 3rem; }
    h1,h2,h3 { color:#202944; letter-spacing:-.04em; font-weight:800; }
    h1 { font-size:2rem !important; }
    h2 { font-size:1.45rem !important; }
    p, label, .stMarkdown { color:#34405a; }
    [data-testid="stSidebar"] { background:#fff; }
    .hero { background:linear-gradient(120deg,#e9f1ff,#f5eaff); border:1px solid #dce5ff; border-radius:22px; padding:24px; margin:8px 0 20px; }
    .hero-kicker { color:#58698e; font-size:.9rem; font-weight:700; }
    .hero-title { color:#202944; font-size:clamp(1.5rem,4vw,2.15rem); font-weight:900; margin:7px 0; line-height:1.3; }
    .hero-sub { color:#53617d; font-size:1rem; line-height:1.6; }
    .section-note,.small-muted { color:#687590; font-size:.95rem; line-height:1.6; }
    div[data-testid="stMetric"] { background:#fff; border:1px solid #e4e9f5; border-radius:18px; padding:16px; box-shadow:0 3px 12px #27385b0a; }
    div[data-testid="stMetricLabel"] { color:#66728d; font-size:.9rem; font-weight:700; }
    div[data-testid="stMetricValue"] { color:#202944; font-weight:900; }
    div[data-testid="stForm"], [data-testid="stExpander"] { background:#fff; border:1px solid #e4e9f5; border-radius:17px; }
    div.stButton > button, div.stFormSubmitButton > button { min-height:46px; border-radius:13px; font-weight:800; border:1px solid #dce3f2; }
    div.stButton > button[kind="primary"], div.stFormSubmitButton > button[kind="primary"] { background:#536dfe; border-color:#536dfe; }
    input, textarea, [data-baseweb="select"] { border-radius:12px !important; }
    [data-testid="stRadio"] label, [data-testid="stCheckbox"] label { font-weight:650; }
    .task-done { color:#98a2b7; text-decoration:line-through; }
    hr { border-color:#e3e8f2; }
    @media (max-width: 700px) {
      .block-container { padding: .7rem .75rem 2rem; }
      h1 { font-size:1.55rem !important; }
      h2 { font-size:1.2rem !important; }
      .hero { padding:18px 16px; border-radius:17px; }
      .hero-sub { font-size:.92rem; }
      div[data-testid="stMetric"] { padding:12px 10px; border-radius:14px; }
      div[data-testid="stMetricLabel"] { font-size:.78rem; }
      div[data-testid="stMetricValue"] { font-size:1.35rem; }
      div.stButton > button, div.stFormSubmitButton > button { min-height:48px; font-size:.95rem; }
      [data-testid="stHorizontalBlock"] { flex-wrap:wrap; gap:.55rem !important; }
      [data-testid="stHorizontalBlock"] > [data-testid="column"] { min-width: calc(50% - .3rem) !important; flex: 1 1 calc(50% - .3rem) !important; }
      [data-testid="stDataFrame"] { overflow-x:auto; }
    }
    @media (max-width: 430px) {
      [data-testid="stHorizontalBlock"] > [data-testid="column"] { min-width:100% !important; flex:1 1 100% !important; }
      div[data-testid="stMetric"] { padding:10px 12px; }
    }
</style>
""", unsafe_allow_html=True)

# ----------------------------- Helpers -----------------------------
def parse_date(value):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return date.today()

def fmt_minutes(minutes):
    hours = int(minutes) // 60
    mins = int(minutes) % 60
    return f"{hours}시간 {mins}분" if hours else f"{mins}분"

def add_task(title, due, priority, category, memo):
    data["tasks"].append({
        "id": str(time.time_ns()), "title": title.strip(),
        "due": due.isoformat(), "priority": priority,
        "category": category, "memo": memo.strip(),
        "done": False, "created": date.today().isoformat(),
        "completed": None,
    })
    save_data()

def add_event(title, event_date, start_time, end_time, memo):
    data["events"].append({
        "id": str(time.time_ns()), "title": title.strip(),
        "date": event_date.isoformat(), "start": str(start_time),
        "end": str(end_time), "memo": memo.strip(),
    })
    save_data()

def finish_task(task):
    task["done"] = not task["done"]
    task["completed"] = date.today().isoformat() if task["done"] else None
    save_data()

def delete_item(collection, item_id):
    data[collection] = [x for x in data[collection] if x["id"] != item_id]
    save_data()

today = date.today()
tasks = data["tasks"]
events = data["events"]
done_tasks = [t for t in tasks if t.get("done")]
open_tasks = [t for t in tasks if not t.get("done")]
today_tasks = [t for t in tasks if t.get("due") == today.isoformat()]
today_done = [t for t in today_tasks if t.get("done")]
today_events = sorted(
    [e for e in events if e.get("date") == today.isoformat()],
    key=lambda x: x.get("start", "")
)

# ----------------------------- 상단 메뉴 -----------------------------
st.markdown("<div style='font-size:1.65rem;font-weight:900;color:#263451;'>🌈 Daily <span style='font-size:.9rem;font-weight:600;color:#77839b;'>쉽고 편한 나의 하루 관리</span></div>", unsafe_allow_html=True)
page = st.radio(
    "메뉴",
    ["🏠 홈", "📝 할 일", "📅 일정", "⏱️ 집중", "🏆 통계"],
    horizontal=True,
    label_visibility="collapsed",
    key="main_navigation",
)
page = {"🏠 홈":"대시보드", "📝 할 일":"할 일 관리", "📅 일정":"일정 관리", "⏱️ 집중":"집중 타이머", "🏆 통계":"통계"}[page]
with st.expander("⚙️ 데이터 백업 / 저장 안내"):
    st.caption("내 기록은 앱 폴더의 productivity_data.json 파일에 저장됩니다. 다른 곳에 보관하려면 아래 백업을 내려받으세요.")
    backup = json.dumps(data, ensure_ascii=False, indent=2)
    st.download_button("⬇️ 내 데이터 백업하기", data=backup, file_name=f"daily_backup_{today.isoformat()}.json", mime="application/json", use_container_width=True)

# ----------------------------- Dashboard -----------------------------
if page == "대시보드":
    st.markdown(f"""
    <div class="hero">
      <div class="hero-kicker">{today.strftime('%Y년 %m월 %d일')} · DAILY OVERVIEW</div>
      <div class="hero-title">오늘 할 일, 하나씩 끝내봐요!</div>
      <div class="hero-sub">할 일을 적고, 일정을 확인하고, 집중 시간을 모아봐요.</div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("전체 할 일", f"{len(tasks)}개")
    c2.metric("완료한 할 일", f"{len(done_tasks)}개")
    c3.metric("오늘 남은 일", f"{len([t for t in today_tasks if not t.get('done')])}개")
    focus_today = sum(
        int(s.get("minutes", 0)) for s in data["focus_sessions"]
        if s.get("date") == today.isoformat()
    )
    c4.metric("오늘 집중 시간", fmt_minutes(focus_today))

    left, right = st.columns([1.15, 1])
    with left:
        st.subheader("📝 오늘 해야 할 일")
        if not today_tasks:
            st.info("오늘 마감인 할 일이 없습니다. 할 일 관리에서 새 업무를 추가해 보세요.")
        else:
            for task in sorted(today_tasks, key=lambda x: (x.get("done", False), x.get("priority", ""))):
                row = st.columns([0.08, 0.72, 0.20])
                checked = row[0].checkbox(
                    "완료", value=task.get("done", False),
                    key=f"dash_{task['id']}", label_visibility="collapsed"
                )
                if checked != task.get("done", False):
                    finish_task(task)
                    st.rerun()
                row[1].markdown(
                    f"<span class='{'task-done' if task.get('done') else ''}'>{task['title']}</span>",
                    unsafe_allow_html=True,
                )
                row[2].caption(task.get("priority", "보통"))
        st.subheader("📅 다가오는 일정")
        upcoming = sorted(
            [e for e in events if parse_date(e.get("date")) >= today],
            key=lambda x: (x.get("date", ""), x.get("start", ""))
        )[:5]
        if not upcoming:
            st.caption("등록된 일정이 없습니다.")
        for event in upcoming:
            st.markdown(
                f"**{event['date']}** · {event['start']}  {event['title']}"
            )
    with right:
        st.subheader("📈 이번 주 진행 상황")
        week_start = today - timedelta(days=today.weekday())
        week_days = [(week_start + timedelta(days=i)) for i in range(7)]
        week_data = []
        for d in week_days:
            completed = sum(
                1 for t in tasks
                if t.get("completed") == d.isoformat()
            )
            week_data.append({"요일": d.strftime("%a"), "완료한 일": completed})
        chart_df = pd.DataFrame(week_data).set_index("요일")
        st.bar_chart(chart_df, use_container_width=True, height=230)
        total_today = len(today_tasks)
        progress = len(today_done) / total_today if total_today else 0
        st.markdown("**오늘 할 일 달성률**")
        st.progress(progress)
        st.caption(f"{len(today_done)} / {total_today}개 완료")

    st.divider()
    st.subheader("➕ 할 일 빠르게 추가")
    with st.form("quick_task_form", clear_on_submit=True):
        q1, q2, q3 = st.columns([2, 1, 1])
        quick_title = q1.text_input("새 할 일", placeholder="예: 수행평가 자료 정리")
        quick_due = q2.date_input("언제까지 할까요?", value=today)
        quick_priority = q3.selectbox("중요도", ["높음", "보통", "낮음"])
        submitted = st.form_submit_button("할 일 추가", use_container_width=True)
        if submitted:
            if quick_title.strip():
                add_task(quick_title, quick_due, quick_priority, "개인", "")
                st.success("할 일을 추가했습니다.")
                st.rerun()
            else:
                st.warning("할 일 내용을 입력해 주세요.")

# ----------------------------- Tasks -----------------------------
elif page == "할 일 관리":
    st.title("📝 할 일 관리")
    st.markdown("<div class='section-note'>해야 할 일을 적고, 끝낸 일은 체크해 보세요!</div>", unsafe_allow_html=True)
    with st.expander("➕ 새 할 일 추가하기", expanded=not bool(tasks)):
        with st.form("add_task_form", clear_on_submit=True):
            title = st.text_input("무엇을 할까요?", placeholder="예: 영어 단어 30개 외우기")
            a, b, c = st.columns(3)
            due = a.date_input("언제까지 할까요?", value=today)
            priority = b.selectbox("중요도", ["높음", "보통", "낮음"])
            category = c.selectbox("종류", ["공부", "업무", "개인", "기타"])
            memo = st.text_area("메모 (선택)", placeholder="세부 내용이나 참고 사항")
            submitted = st.form_submit_button("✅ 할 일 저장하기", use_container_width=True)
            if submitted:
                if title.strip():
                    add_task(title, due, priority, category, memo)
                    st.success("할 일을 등록했습니다.")
                    st.rerun()
                else:
                    st.warning("제목을 입력해 주세요.")

    filter_value = st.segmented_control(
        "보기", ["전체", "진행 중", "완료"], default="전체"
    )
    filtered = tasks
    if filter_value == "진행 중":
        filtered = [t for t in tasks if not t.get("done")]
    elif filter_value == "완료":
        filtered = [t for t in tasks if t.get("done")]
    filtered = sorted(filtered, key=lambda x: (x.get("done", False), x.get("due", ""), {"높음": 0, "보통": 1, "낮음": 2}.get(x.get("priority"), 1)))
    if not filtered:
        st.info("표시할 할 일이 없습니다.")
    for task in filtered:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([0.07, 0.53, 0.20, 0.20])
            checked = c1.checkbox("완료", value=task.get("done", False), key=f"task_{task['id']}", label_visibility="collapsed")
            if checked != task.get("done", False):
                finish_task(task)
                st.rerun()
            c2.markdown(f"**{'~~' + task['title'] + '~~' if task.get('done') else task['title']}**")
            c2.caption(f"{task.get('category', '기타')} · 마감 {task.get('due', '-')}")
            priority_color = {"높음": "🔴", "보통": "🟡", "낮음": "🟢"}.get(task.get("priority"), "⚪")
            c3.write(f"{priority_color} {task.get('priority', '보통')}")
            if c4.button("삭제", key=f"del_task_{task['id']}"):
                delete_item("tasks", task["id"])
                st.rerun()
            if task.get("memo"):
                st.caption(task["memo"])

# ----------------------------- Calendar / Events -----------------------------
elif page == "일정 관리":
    st.title("📅 일정 관리")
    st.markdown("<div class='section-note'>약속이나 수업, 중요한 날짜를 잊지 않도록 적어두세요!</div>", unsafe_allow_html=True)
    with st.expander("➕ 새 일정 추가하기", expanded=not bool(events)):
        with st.form("add_event_form", clear_on_submit=True):
            event_title = st.text_input("무슨 일정인가요?", placeholder="예: 프로젝트 회의")
            a, b, c = st.columns(3)
            event_date = a.date_input("날짜", value=today)
            start_time = b.time_input("시작 시간", value=datetime.now().replace(hour=9, minute=0).time())
            end_time = c.time_input("종료 시간", value=datetime.now().replace(hour=10, minute=0).time())
            event_memo = st.text_area("메모 (선택)")
            submitted = st.form_submit_button("✅ 일정 저장하기", use_container_width=True)
            if submitted:
                if not event_title.strip():
                    st.warning("일정 이름을 입력해 주세요.")
                elif end_time <= start_time:
                    st.warning("종료 시간은 시작 시간보다 늦어야 합니다.")
                else:
                    add_event(event_title, event_date, start_time, end_time, event_memo)
                    st.success("일정을 등록했습니다.")
                    st.rerun()

    selected_month = st.date_input("일정 확인 기준일", value=today, key="event_month")
    month_events = sorted(
        [e for e in events if e.get("date", "").startswith(selected_month.strftime("%Y-%m"))],
        key=lambda x: (x.get("date", ""), x.get("start", ""))
    )
    st.subheader(selected_month.strftime("%Y년 %m월 일정"))
    if not month_events:
        st.info("이 달에 등록된 일정이 없습니다.")
    for event in month_events:
        with st.container(border=True):
            a, b = st.columns([0.82, 0.18])
            a.markdown(f"**{event['date']} · {event['title']}**")
            a.caption(f"{event['start']} – {event['end']}")
            if event.get("memo"):
                a.write(event["memo"])
            if b.button("삭제", key=f"del_event_{event['id']}"):
                delete_item("events", event["id"])
                st.rerun()

# ----------------------------- Focus timer -----------------------------
elif page == "집중 타이머":
    st.title("⏱️ 집중 타이머")
    st.markdown("<div class='section-note'>⏳ 정해진 시간 동안 한 가지 일만 해봐요. 끝나면 기록이 자동으로 쌓여요!</div>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1])
    with c1:
        mode = st.radio("타이머 모드", ["집중", "짧은 휴식", "긴 휴식"], horizontal=True)
        default_minutes = {"집중": 25, "짧은 휴식": 5, "긴 휴식": 15}[mode]
        minutes = st.number_input("시간 (분)", min_value=1, max_value=180, value=default_minutes, step=1)
        focus_label = st.text_input("집중할 작업", placeholder="예: 수학 문제 풀이")
        if st.session_state.timer_running and mode != st.session_state.timer_mode:
            st.info("실행 중인 타이머를 먼저 초기화한 뒤 모드를 변경해 주세요.")
        else:
            st.session_state.timer_mode = mode
        start_col, pause_col, reset_col = st.columns(3)
        if start_col.button("▶️ 시작하기", use_container_width=True, type="primary"):
            if not st.session_state.timer_running:
                if st.session_state.timer_end is None:
                    st.session_state.timer_total = int(minutes) * 60
                st.session_state.timer_end = time.time() + st.session_state.timer_total
                st.session_state.timer_running = True
                st.rerun()
        if pause_col.button("⏸️ 잠깐 멈추기", use_container_width=True):
            if st.session_state.timer_running:
                st.session_state.timer_total = max(0, int(st.session_state.timer_end - time.time()))
                st.session_state.timer_running = False
                st.session_state.timer_end = None
                st.rerun()
        if reset_col.button("🔄 처음부터", use_container_width=True):
            st.session_state.timer_running = False
            st.session_state.timer_end = None
            st.session_state.timer_total = int(minutes) * 60
            st.rerun()

    with c2:
        @st.fragment(run_every="1s")
        def timer_display():
            if st.session_state.timer_running and st.session_state.timer_end:
                remaining = max(0, int(st.session_state.timer_end - time.time()))
            else:
                remaining = int(st.session_state.timer_total)
            mm, ss = divmod(remaining, 60)
            st.markdown(
                f"<div style='background:#fff;border:1px solid #e7ebf2;border-radius:20px;padding:35px 20px;text-align:center;margin-top:12px;'>"
                f"<div style='color:#8490a3;font-weight:600;font-size:.9rem;'>{st.session_state.timer_mode}</div>"
                f"<div style='font-size:4.2rem;line-height:1.2;font-weight:800;letter-spacing:-.06em;color:#202b42;font-variant-numeric:tabular-nums;'>{mm:02d}:{ss:02d}</div>"
                f"<div style='color:#929bad;font-size:.82rem;margin-top:8px;'>{'집중 중입니다. 잠시 다른 일을 내려놓으세요.' if st.session_state.timer_running else '준비되면 시작 버튼을 눌러주세요.'}</div>"
                f"</div>", unsafe_allow_html=True
            )
            if st.session_state.timer_running and remaining <= 0:
                st.session_state.timer_running = False
                st.session_state.timer_end = None
                st.session_state.timer_total = 0
                if st.session_state.timer_mode == "집중":
                    data["focus_sessions"].append({
                        "date": today.isoformat(),
                        "minutes": int(minutes),
                        "label": focus_label.strip() or "집중 세션",
                        "created_at": datetime.now().isoformat(timespec="seconds"),
                    })
                    save_data()
                st.toast("타이머가 끝났습니다!")
                st.rerun()
        timer_display()

    st.caption("집중 모드가 완료되면 집중 시간이 통계에 자동 기록됩니다. 브라우저 탭을 닫으면 실행 중인 타이머는 유지되지 않을 수 있습니다.")

# ----------------------------- Statistics -----------------------------
elif page == "통계":
    st.title("🏆 나의 기록")
    st.markdown("<div class='section-note'>내가 얼마나 해냈는지 그래프로 확인해 봐요!</div>", unsafe_allow_html=True)
    start = today - timedelta(days=6)
    last7 = [(start + timedelta(days=i)) for i in range(7)]
    completed_by_day = []
    focus_by_day = []
    for d in last7:
        completed_by_day.append({
            "날짜": d.strftime("%m/%d"),
            "완료한 할 일": sum(1 for t in tasks if t.get("completed") == d.isoformat()),
        })
        focus_by_day.append({
            "날짜": d.strftime("%m/%d"),
            "집중 시간(분)": sum(int(s.get("minutes", 0)) for s in data["focus_sessions"] if s.get("date") == d.isoformat()),
        })
    total_focus = sum(int(s.get("minutes", 0)) for s in data["focus_sessions"])
    completion_rate = (len(done_tasks) / len(tasks) * 100) if tasks else 0
    a, b, c = st.columns(3)
    a.metric("전체 할 일 완료율", f"{completion_rate:.0f}%")
    b.metric("누적 집중 시간", fmt_minutes(total_focus))
    c.metric("누적 집중 세션", f"{len(data['focus_sessions'])}회")
    left, right = st.columns(2)
    with left:
        st.subheader("최근 7일 완료한 할 일")
        st.bar_chart(pd.DataFrame(completed_by_day).set_index("날짜"), height=270)
    with right:
        st.subheader("최근 7일 집중 시간")
        st.bar_chart(pd.DataFrame(focus_by_day).set_index("날짜"), height=270)
    st.subheader("최근 집중 기록")
    recent = sorted(data["focus_sessions"], key=lambda x: x.get("created_at", ""), reverse=True)[:10]
    if recent:
        st.dataframe(
            pd.DataFrame([{
                "날짜": x.get("date", ""),
                "작업": x.get("label", "집중 세션"),
                "집중 시간": f"{x.get('minutes', 0)}분",
            } for x in recent]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("아직 집중 기록이 없습니다. 집중 타이머를 사용해 보세요.")

st.caption("🌱 작은 실천이 모여 큰 변화가 돼요. · Daily")
