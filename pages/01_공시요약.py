"""
공시요약 페이지

홈에서 선택한 회사(session_state.selected_corp)의 공시 목록을 조회하고,
선택한 공시의 본문을 가져와 phi-4-mini로 요약한다.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))
from src.dart import get_disclosure_list, get_document_text  # noqa: E402
from src.llm import summarize_disclosure  # noqa: E402

st.set_page_config(page_title="공시요약 | foRG-mini", layout="wide")


def get_secret(name: str) -> str | None:
    try:
        return st.secrets[name]
    except (KeyError, FileNotFoundError):
        return None


DART_API_KEY = get_secret("DART_API_KEY")
OPENROUTER_API_KEY = get_secret("OPENROUTER_API_KEY")

st.title("🧾 공시 요약")

# 가드: 회사 미선택 / 키 누락
corp = st.session_state.get("selected_corp")
if not corp:
    st.warning("먼저 홈 페이지에서 회사를 검색·선택하세요.")
    st.stop()
if not DART_API_KEY:
    st.error("DART_API_KEY 가 없습니다. secrets.toml 을 확인하세요.")
    st.stop()
if not OPENROUTER_API_KEY:
    st.error("OPENROUTER_API_KEY 가 없습니다. secrets.toml 을 확인하세요.")
    st.stop()

st.info(f"선택 회사: **{corp['corp_name']}** (`{corp['corp_code']}`)")

# ---------------------------------------------------------------------------
# 1. 조회 기간 설정
# ---------------------------------------------------------------------------
st.subheader("1. 공시 목록")
col1, col2, col3 = st.columns(3)
with col1:
    end_d = st.date_input("종료일", value=date.today())
with col2:
    bgn_d = st.date_input("시작일", value=date.today() - timedelta(days=90))
with col3:
    page_count = st.slider("최대 건수", 5, 50, 20)

disclosures = []
try:
    disclosures = get_disclosure_list(
        DART_API_KEY,
        corp["corp_code"],
        bgn_d.strftime("%Y%m%d"),
        end_d.strftime("%Y%m%d"),
        page_count=page_count,
    )
except Exception as e:
    st.error(f"공시 목록 조회 실패: {e}")

if not disclosures:
    st.info("해당 기간에 공시가 없습니다. 기간을 넓혀보세요.")
    st.stop()

# 공시 선택 (제목 + 날짜)
options = {
    f"[{d['rcept_dt']}] {d['report_nm']}": d for d in disclosures
}
choice = st.selectbox("공시 선택", list(options.keys()))
selected = options[choice]

# ---------------------------------------------------------------------------
# 2. 본문 + 요약
# ---------------------------------------------------------------------------
st.subheader("2. 본문 & 요약")

if st.button("📥 본문 가져오기 + 요약", type="primary"):
    try:
        body = get_document_text(DART_API_KEY, selected["rcept_no"])
    except Exception as e:
        st.error(f"본문 조회 실패: {e}")
        st.stop()

    # 세션에 저장 (재실행돼도 유지)
    st.session_state.last_body = body
    st.session_state.last_title = selected["report_nm"]

    try:
        summary = summarize_disclosure(
            OPENROUTER_API_KEY,
            corp["corp_name"],
            selected["report_nm"],
            body,
        )
        st.session_state.last_summary = summary
    except Exception as e:
        st.error(f"요약 실패: {e}")
        st.session_state.last_summary = None

# 결과 출력 (좌: 요약 / 우: 원문) — 노트북 2.3 컬럼 레이아웃
if st.session_state.get("last_summary"):
    left, right = st.columns([1, 1])
    with left:
        st.markdown("#### ✨ phi-4-mini 요약")
        st.markdown(st.session_state.last_summary)
    with right:
        st.markdown("#### 📄 원문 (앞부분)")
        st.text_area(
            "원문",
            (st.session_state.get("last_body") or "")[:5000],
            height=500,
            label_visibility="collapsed",
        )

    dart_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={selected['rcept_no']}"
    st.caption(f"원문 전체 보기: {dart_url}")
