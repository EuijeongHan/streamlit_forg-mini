"""
OpenRouter(phi-4-mini-instruct) 기반 공시 요약 모듈.

OpenRouter 는 OpenAI 호환 API 이므로 base_url 만 교체하면 된다.
모델을 로컬에 올리지 않으므로 Streamlit Cloud 메모리 한도(1GB) 문제가 없고,
phi-4-mini 는 128K 컨텍스트라 공시 본문을 거의 그대로 넣을 수 있다.

API Key 는 https://openrouter.ai/keys 에서 발급.
"""

import requests
import streamlit as st

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "microsoft/phi-4-mini-instruct"

SYSTEM_PROMPT = (
    "당신은 한국 기업 공시(DART) 분석 도우미입니다. "
    "주어진 공시 원문을 읽고, 투자자가 빠르게 이해할 수 있도록 핵심만 한국어로 요약합니다. "
    "원문에 없는 내용은 만들지 말고, 수치는 원문 그대로 인용하십시오."
)

USER_TEMPLATE = """다음은 '{corp_name}'의 공시 원문입니다.
공시 제목: {title}

아래 형식으로 요약하세요.

## 한 줄 요약
(공시의 핵심을 한 문장으로)

## 주요 내용
- (핵심 항목 3~5개, 수치 포함)

## 투자자 관점 시사점
- (1~2개. 원문 근거가 부족하면 '원문상 판단 근거 부족'이라고 표기)

---
공시 원문:
{body}
"""


@st.cache_data(show_spinner="phi-4-mini로 요약 중...", ttl=60 * 30)
def summarize_disclosure(
    api_key: str,
    corp_name: str,
    title: str,
    body: str,
    max_body_chars: int = 40000,
) -> str:
    """공시 본문을 phi-4-mini로 요약하여 마크다운 문자열을 반환."""
    body = (body or "").strip()
    if not body:
        return "본문 텍스트가 비어 있어 요약할 수 없습니다."

    prompt = USER_TEMPLATE.format(
        corp_name=corp_name,
        title=title,
        body=body[:max_body_chars],
    )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1000,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    resp = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f"OpenRouter 오류 [{resp.status_code}]: {resp.text[:300]}")

    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()
