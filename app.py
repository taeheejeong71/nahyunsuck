import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# ------------------------------------------------------------
# 기본 설정
# ------------------------------------------------------------
st.set_page_config(
    page_title="내 용돈 연구소",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DB_PATH = Path(__file__).with_name("expenses.db")
CATEGORIES = ["식비", "간식", "교통", "쇼핑", "문화·취미", "학용품", "기타"]
COLORS = {
    "식비": "#FF9F68",
    "간식": "#FFD166",
    "교통": "#6C9EFF",
    "쇼핑": "#B69CFF",
    "문화·취미": "#62CDB5",
    "학용품": "#F28FB3",
    "기타": "#AAB4C3",
}


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            spent_on TEXT NOT NULL,
            item TEXT NOT NULL,
            category TEXT NOT NULL,
            amount INTEGER NOT NULL CHECK(amount > 0),
            memo TEXT DEFAULT ''
        )
        """
    )
    conn.commit()
    return conn


def load_data():
    with get_connection() as conn:
        df = pd.read_sql_query(
            "SELECT id, spent_on, item, category, amount, memo FROM expenses ORDER BY spent_on DESC, id DESC",
            conn,
        )
    if not df.empty:
        df["spent_on"] = pd.to_datetime(df["spent_on"]).dt.date
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0).astype(int)
    return df


def money(value):
    return f"{int(value):,}원"


def month_start(d):
    return d.replace(day=1)


# ------------------------------------------------------------
# 보기 쉬운 화면 디자인
# ------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
    .stApp { background: #F5F7FB; }
    .block-container { max-width: 1120px; padding-top: 1.4rem; padding-bottom: 3rem; }
    h1, h2, h3 { color: #17233B; letter-spacing: -0.04em; }
    .hero {
        background: linear-gradient(120deg, #355CDE, #6B83F2);
        color: white; padding: 25px 27px; border-radius: 22px;
        margin-bottom: 18px;
    }
    .hero h1 { color: white; font-size: clamp(1.65rem, 4vw, 2.35rem); margin: 0 0 7px 0; }
    .hero p { color: #EEF1FF; margin: 0; font-size: 1rem; }
    .small-note { color: #65718A; font-size: .9rem; }
    div[data-testid="stMetric"] {
        background: white; padding: 17px 18px; border: 1px solid #E7EBF3;
        border-radius: 17px; box-shadow: 0 3px 12px rgba(30,50,90,.04);
    }
    div[data-testid="stMetricLabel"] { color: #66728A; }
    div[data-testid="stMetricValue"] { color: #17233B; }
    div.stButton > button {
        border-radius: 12px; min-height: 2.8rem; font-weight: 700;
    }
    div[data-testid="stForm"] {
        background: white; border: 1px solid #E7EBF3; border-radius: 18px;
        padding: 18px;
    }
    section[data-testid="stSidebar"] { background: #FFFFFF; }
    /* 모바일: 손가락으로 누르기 쉽고 화면을 덜 답답하게 */
    button, [role="button"] { touch-action: manipulation; }
    @media (max-width: 768px) {
        .block-container { padding: .8rem .7rem 2.5rem .7rem; max-width: 100%; }
        .hero { padding: 21px 17px; border-radius: 17px; margin-bottom: 14px; }
        .hero p { font-size: .95rem; line-height: 1.5; }
        h1 { font-size: 1.65rem !important; }
        h2 { font-size: 1.35rem !important; }
        h3 { font-size: 1.15rem !important; }

        /* 좁은 화면에서는 두 칸 영역을 세로로 배치 */
        div[data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
            gap: .65rem !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
            flex: 1 1 100% !important;
            min-width: 100% !important;
        }

        /* 탭은 가로로 넘겨 볼 수 있게 */
        div[data-testid="stTabs"] [role="tablist"] {
            gap: 5px; overflow-x: auto; flex-wrap: nowrap;
            scrollbar-width: thin; padding-bottom: 5px;
        }
        div[data-testid="stTabs"] button[role="tab"] {
            min-height: 48px; min-width: max-content;
            padding: 10px 13px; font-size: 14px;
        }

        /* 버튼과 입력창 터치 영역 확대 */
        div.stButton > button,
        div[data-testid="stFormSubmitButton"] > button {
            min-height: 54px !important; width: 100%;
            border-radius: 14px; font-size: 16px !important;
            font-weight: 800; padding: 12px 16px;
        }
        input, textarea, [data-baseweb="select"] > div {
            min-height: 49px !important; font-size: 16px !important;
        }
        div[data-testid="stNumberInput"] button,
        div[data-testid="stDateInput"] button {
            min-width: 46px !important; min-height: 46px !important;
        }
        label, [data-testid="stWidgetLabel"] {
            font-size: 15px !important; font-weight: 700 !important;
        }
        div[data-testid="stMetric"] { padding: 14px; border-radius: 15px; }
        [data-testid="stDataFrame"] { font-size: 12px; overflow-x: auto; }
        div[data-testid="stExpander"] summary { min-height: 52px; align-items: center; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>💰 내 용돈 연구소</h1>
      <p>돈을 어디에 썼는지 기록하고, 다음 달 지출도 미리 살펴봐요!</p>
    </div>
    """,
    unsafe_allow_html=True,
)

df = load_data()
today = date.today()
current_month = today.strftime("%Y-%m")

# 탭을 사용해 휴대폰에서도 메뉴를 쉽게 찾도록 구성
tab_home, tab_add, tab_history, tab_insight = st.tabs(
    ["🏠 한눈에 보기", "➕ 지출 기록", "📒 기록장", "🔎 소비 분석"]
)

# ------------------------------------------------------------
# 지출 추가
# ------------------------------------------------------------
with tab_add:
    st.subheader("새로운 지출 기록하기")
    st.caption("오늘 쓴 돈을 간단히 적어 보세요. 모르는 항목은 '기타'를 선택하면 돼요.")
    with st.form("expense_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            spent_on = st.date_input("📅 언제 썼나요?", value=today, max_value=today)
            item = st.text_input("🛍️ 무엇을 샀나요?", placeholder="예: 김밥, 버스비, 공책")
            category = st.selectbox("🏷️ 어떤 종류인가요?", CATEGORIES)
        with col2:
            amount = st.number_input("💵 얼마를 썼나요? (원)", min_value=1, max_value=100000000, value=3000, step=500)
            memo = st.text_input("📝 메모 (선택)", placeholder="예: 친구와 점심")
            st.write("")
            st.write("")
            submitted = st.form_submit_button("기록 저장하기 ✅", use_container_width=True, type="primary")

        if submitted:
            if not item.strip():
                st.error("무엇을 샀는지 한 글자 이상 적어 주세요!")
            else:
                with get_connection() as conn:
                    conn.execute(
                        "INSERT INTO expenses (spent_on, item, category, amount, memo) VALUES (?, ?, ?, ?, ?)",
                        (spent_on.isoformat(), item.strip(), category, int(amount), memo.strip()),
                    )
                    conn.commit()
                st.success(f"{item.strip()} 지출 {money(amount)}을(를) 저장했어요!")
                st.rerun()

# ------------------------------------------------------------
# 대시보드
# ------------------------------------------------------------
with tab_home:
    st.subheader("이번 달 용돈 성적표")
    month_df = df[df["spent_on"].apply(lambda x: x.strftime("%Y-%m") == current_month)] if not df.empty else df
    total = int(month_df["amount"].sum()) if not month_df.empty else 0
    count = len(month_df)
    avg = round(total / count) if count else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("이번 달 총지출", money(total))
    c2.metric("기록한 횟수", f"{count}번")
    c3.metric("한 번 쓸 때 평균", money(avg))

    st.markdown("### 🧭 이번 달 돈 사용 지도")
    if month_df.empty:
        st.info("아직 이번 달 기록이 없어요. '지출 기록'에서 첫 지출을 추가해 보세요!")
    else:
        by_cat = month_df.groupby("category", as_index=False)["amount"].sum().sort_values("amount", ascending=False)
        left, right = st.columns([1.15, 1])
        with left:
            fig = px.pie(
                by_cat, names="category", values="amount", hole=.55,
                color="category", color_discrete_map=COLORS,
            )
            fig.update_layout(
                margin=dict(t=10, b=10, l=5, r=5), height=300,
                legend_title_text="", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Noto Sans KR"),
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        with right:
            st.write("**어디에 가장 많이 썼을까요?**")
            for _, row in by_cat.iterrows():
                ratio = row["amount"] / total if total else 0
                st.write(f"{row['category']} · {money(row['amount'])} ({ratio:.0%})")
                st.progress(float(ratio))
        biggest = by_cat.iloc[0]
        st.success(f"이번 달에는 **{biggest['category']}**에 가장 많이 썼어요. ({money(biggest['amount'])})")

    st.markdown("### 💡 이번 달 작은 팁")
    if total == 0:
        st.write("지출을 기록하면 나에게 맞는 소비 팁이 여기에 나타나요.")
    elif count >= 3:
        top_category = month_df.groupby("category")["amount"].sum().idxmax()
        st.write(f"'{top_category}' 지출을 한 번 살펴보세요. 꼭 필요한 소비였는지 돌아보면 다음 달 계획에 도움이 돼요.")
    else:
        st.write("기록이 조금 더 쌓이면 소비 습관을 더 정확하게 살펴볼 수 있어요.")

# ------------------------------------------------------------
# 전체 기록 및 삭제
# ------------------------------------------------------------
with tab_history:
    st.subheader("내 지출 기록장")
    if df.empty:
        st.info("아직 저장된 기록이 없어요. 지출을 추가하면 이곳에 모여요.")
    else:
        filter_months = sorted({d.strftime("%Y-%m") for d in df["spent_on"]}, reverse=True)
        selected_month = st.selectbox("보고 싶은 달을 골라요", ["전체 보기"] + filter_months)
        view_df = df.copy()
        if selected_month != "전체 보기":
            view_df = view_df[view_df["spent_on"].apply(lambda x: x.strftime("%Y-%m") == selected_month)]
        show_df = view_df[["spent_on", "item", "category", "amount", "memo"]].copy()
        show_df.columns = ["날짜", "사용한 곳", "종류", "금액(원)", "메모"]
        st.dataframe(show_df, use_container_width=True, hide_index=True)
        st.caption(f"총 {len(view_df)}개의 기록 · 합계 {money(view_df['amount'].sum())}")

        with st.expander("잘못 입력한 기록 삭제하기"):
            options = {
                f"{row.spent_on} · {row.item} · {money(row.amount)}": int(row.id)
                for row in view_df.itertuples()
            }
            selected_label = st.selectbox("삭제할 기록을 선택하세요", list(options.keys()))
            if st.button("선택한 기록 삭제", type="secondary"):
                with get_connection() as conn:
                    conn.execute("DELETE FROM expenses WHERE id = ?", (options[selected_label],))
                    conn.commit()
                st.success("기록을 삭제했어요.")
                st.rerun()

# ------------------------------------------------------------
# 분석 및 다음 달 예측
# ------------------------------------------------------------
with tab_insight:
    st.subheader("소비 습관 탐정 🔎")
    st.caption("기록된 지출을 바탕으로 간단한 통계와 다음 달 예상 금액을 계산해요.")
    if df.empty:
        st.info("분석하려면 먼저 지출을 3번 이상 기록해 주세요.")
    else:
        monthly = df.copy()
        monthly["month"] = monthly["spent_on"].apply(lambda x: x.strftime("%Y-%m"))
        monthly_totals = monthly.groupby("month")["amount"].sum().sort_index()
        all_months = pd.period_range(
            start=pd.Period(monthly["month"].min(), freq="M"),
            end=pd.Period(today.strftime("%Y-%m"), freq="M"),
            freq="M",
        ).astype(str)
        monthly_totals = monthly_totals.reindex(all_months, fill_value=0)
        recent = monthly_totals.tail(3)
        prediction = int(round(recent.mean())) if len(recent) else 0

        st.markdown("### 🔮 다음 달 예상 지출")
        p1, p2 = st.columns(2)
        p1.metric("다음 달 예상", money(prediction))
        p2.metric("예측에 사용한 기간", f"최근 {len(recent)}개월")
        st.caption("예측 방법: 최근 최대 3개월의 월별 지출 평균이에요. 미래 지출을 보장하는 값이 아니라 참고용이에요.")

        chart_df = monthly_totals.reset_index()
        chart_df.columns = ["월", "지출"]
        fig = px.bar(chart_df, x="월", y="지출", text_auto=".2s")
        fig.update_traces(marker_color="#6C83EA")
        fig.update_layout(
            height=300, margin=dict(t=15, b=10, l=5, r=5),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            yaxis_title="지출 금액 (원)", xaxis_title="월",
            font=dict(family="Noto Sans KR"),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        st.markdown("### 📌 내가 자주 쓰는 곳")
        cat_totals = df.groupby("category")["amount"].sum().sort_values(ascending=False)
        for cat, value in cat_totals.head(3).items():
            st.write(f"- **{cat}**: {money(value)}")

        st.markdown("### 🎯 다음 달 목표 세우기")
        default_goal = max(0, int(prediction * 0.9))
        goal = st.number_input("다음 달 지출 목표 (원)", min_value=0, value=default_goal, step=1000)
        if prediction > 0:
            if goal < prediction:
                st.success(f"최근 평균보다 {money(prediction - goal)} 아껴 쓰는 목표예요. 할 수 있어요! 💪")
            elif goal == prediction:
                st.info("최근 평균을 유지하는 목표예요.")
            else:
                st.info("목표 금액이 최근 평균보다 높아요. 필요한 지출인지 확인해 보세요.")

st.divider()
st.caption("🔒 데이터 안내: 지출 기록은 이 앱이 실행되는 환경의 expenses.db 파일에 저장돼요. 배포 환경이 초기화되거나 파일이 사라지면 기록도 사라질 수 있으니 중요한 데이터는 따로 보관하세요.")
st.caption("내 용돈 연구소 · 나의 소비를 알고, 더 똑똑하게 사용하기!")
