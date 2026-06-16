"""
foRG-mini : DART 공시 본문 요약 프로토타입 (홈)

흐름:
  app.py (회사 검색) -> session_state 에 선택 회사 저장
  pages/01_공시요약.py (공시 목록 -> 본문 -> phi-4-mini 요약)
"""

import sys
from pathlib import Path

import streamlit as st

# src 모듈 import 경로 확보
sys.path.append(str(Path(__file__).parent))
from src.dart import search_company  # noqa: E402
from src.gate import require_password, remaining  # noqa: E402

st.set_page_config(page_title="foRG-mini | DART 공시 요약", layout="wide")

# 접근 제어: 비밀번호 게이트 (인증 전 콘텐츠 비표시)
require_password()
st.sidebar.caption(f"오늘 남은 호출: {remaining()}회")


# ---------------------------------------------------------------------------
# API Key 로드 (.streamlit/secrets.toml)
#   노트북 7장: secrets.toml 로 민감정보 분리 관리
# ---------------------------------------------------------------------------
def get_secret(name: str) -> str | None:
    try:
        return st.secrets[name]
    except (KeyError, FileNotFoundError):
        return None


DART_API_KEY = get_secret("DART_API_KEY")

# 사이드바
st.sidebar.title("foRG-mini")
st.sidebar.caption("DART 공시를 생성 AI가 요약하고, 검증 AI로 사실성까지 확인하는 도구")
st.sidebar.divider()
st.sidebar.markdown(
    "**사용 순서**\n"
    "1. 회사 검색·선택\n"
    "2. 좌측 `공시요약` 페이지 이동\n"
    "3. 공시 선택 → 요약 실행"
)
if DART_API_KEY:
    st.sidebar.success("DART API Key 로드됨")
else:
    st.sidebar.error("DART_API_KEY 없음 (secrets.toml 확인)")

# 최근 선택 회사 (재선택용)
if st.session_state.get("corp_history"):
    st.sidebar.divider()
    st.sidebar.markdown("**최근 선택**")
    for h in st.session_state.corp_history:
        if st.sidebar.button(h["corp_name"], key=f"hist_{h['corp_code']}", use_container_width=True):
            st.session_state.selected_corp = h
            st.rerun()


# 세션 상태 초기화 (노트북 2.3 / 3.2)
if "selected_corp" not in st.session_state:
    st.session_state.selected_corp = None
if "corp_history" not in st.session_state:
    st.session_state.corp_history = []  # 최근 선택 회사 (중복 없이 최신순)


st.title("📄 foRG-mini")
st.write("DART 공시 원문을 가져와 phi-4-mini로 요약하는 프로토타입입니다.")

if not DART_API_KEY:
    st.warning(
        "`.streamlit/secrets.toml`에 `DART_API_KEY`를 설정하세요.\n\n"
        "발급: https://opendart.fss.or.kr"
    )
    st.stop()

st.divider()
st.subheader("1. 회사 검색")

col_in, col_opt = st.columns([3, 1])
with col_in:
    keyword = st.text_input("회사명", placeholder="예: 삼성", key="search_kw")
with col_opt:
    listed_only = st.checkbox("상장사만", value=True)

if keyword:
    try:
        results = search_company(DART_API_KEY, keyword, listed_only=listed_only)
    except Exception as e:
        st.error(f"검색 실패: {e}")
        results = []

    if not results:
        st.info("검색 결과가 없습니다.")
    else:
        st.caption(f"{len(results)}건")
        for c in results:
            label = c["corp_name"]
            if c["stock_code"]:
                label += f"  ({c['stock_code']})"
            if st.button(label, key=c["corp_code"], use_container_width=True):
                st.session_state.selected_corp = c
                # 이력 갱신: 중복 제거 후 맨 앞에 추가, 최대 8개 유지
                hist = [h for h in st.session_state.corp_history if h["corp_code"] != c["corp_code"]]
                hist.insert(0, c)
                st.session_state.corp_history = hist[:8]
                st.success(f"선택됨: {c['corp_name']}")

# 현재 선택 상태 표시 (페이지 전환 후에도 유지됨)
st.divider()
if st.session_state.selected_corp:
    c = st.session_state.selected_corp
    st.info(
        f"선택된 회사: **{c['corp_name']}** "
        f"(corp_code: `{c['corp_code']}`)\n\n"
        "→ 좌측 사이드바의 **공시요약** 페이지로 이동하세요."
    )
else:
    st.caption("아직 선택된 회사가 없습니다.")
