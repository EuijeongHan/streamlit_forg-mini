"""
접근 제어 + 전역 일일 호출 제한 모듈.

- 비밀번호 게이트: st.secrets["APP_PASSWORD"] 와 일치해야 진입.
- 전역 카운터: @st.cache_resource 로 앱 인스턴스 전역 공유.
  모든 세션의 호출을 합산하며, 날짜가 바뀌면 자동으로 0 으로 리셋.
  (앱 재시작 시에도 리셋되지만, 비밀번호 게이트가 1차 방벽이므로 충분.)
"""
from datetime import date
import streamlit as st

# 일일 전역 호출 상한 (요약/검증 합산). 필요시 조정.
DAILY_LIMIT = 50


@st.cache_resource
def _global_counter() -> dict:
    """앱 전역에서 공유되는 단일 카운터 dict."""
    return {"date": date.today().isoformat(), "count": 0}


def require_password() -> None:
    """비밀번호 인증. 통과하지 못하면 st.stop() 으로 차단."""
    if st.session_state.get("authed"):
        return

    real = st.secrets.get("APP_PASSWORD", "")
    if not real:
        st.error("APP_PASSWORD 가 secrets 에 설정되지 않았습니다.")
        st.stop()

    pw = st.text_input("🔒 접근 비밀번호", type="password")
    if not pw:
        st.info("비밀번호를 입력하면 이용할 수 있습니다.")
        st.stop()
    if pw != real:
        st.error("비밀번호가 일치하지 않습니다.")
        st.stop()

    st.session_state.authed = True
    st.rerun()


def check_and_consume(n: int = 1) -> bool:
    """
    호출 가능하면 카운터를 n 만큼 올리고 True, 한도 초과면 False.
    날짜가 바뀌면 카운터를 리셋한다.
    """
    c = _global_counter()
    today = date.today().isoformat()
    if c["date"] != today:
        c["date"] = today
        c["count"] = 0

    if c["count"] + n > DAILY_LIMIT:
        return False
    c["count"] += n
    return True


def remaining() -> int:
    """오늘 남은 호출 횟수."""
    c = _global_counter()
    today = date.today().isoformat()
    if c["date"] != today:
        return DAILY_LIMIT
    return max(0, DAILY_LIMIT - c["count"])
