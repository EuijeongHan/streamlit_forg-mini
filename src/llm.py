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
    "다음 규칙을 반드시 지키십시오: "
    "(1) 수치는 원문 그대로 인용하고 단위를 정확히 구분하라. "
    "주식 수는 '주', 금액은 '원'으로 표기하고, '조/억/만' 등으로 임의 변환하거나 단위를 바꾸지 마라. "
    "(예: 4,605주를 '4,605조'로, 240,000원을 '240만 원'으로 쓰지 마라) "
    "(2) 원문에 없는 항목명이나 표현을 만들지 마라('전환대상 주식' 같은 조어 금지). "
    "표에서 '-'로 표기된 항목은 '없음'을 의미하므로 발행/보유로 오인하지 마라. "
    "(3) 투자자 관점 시사점은 원문이 직접 제시한 사실에만 근거하고, 추측성 해석은 쓰지 마라."
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


GEN_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
GEN_OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def _gen_phi(api_key, sys_p, user_p):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": sys_p},
            {"role": "user", "content": user_p},
        ],
        "temperature": 0.2,
        "max_tokens": 1000,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    r = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def _gen_openai(api_key, sys_p, user_p):
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": sys_p},
            {"role": "user", "content": user_p},
        ],
        "temperature": 0.2,
        "max_tokens": 1000,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    r = requests.post(GEN_OPENAI_URL, json=payload, headers=headers, timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def _gen_gemini(api_key, sys_p, user_p):
    payload = {
        "contents": [{"parts": [{"text": sys_p + "\n\n" + user_p}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 2048,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    r = requests.post(GEN_GEMINI_URL, json=payload, headers=headers, timeout=120)
    r.raise_for_status()
    cand = r.json()["candidates"][0]
    parts = cand.get("content", {}).get("parts")
    if not parts:
        raise RuntimeError(f"Gemini 빈 응답 (finishReason={cand.get('finishReason')})")
    text = "".join(part.get("text", "") for part in parts)
    if not text.strip():
        raise RuntimeError(f"Gemini 텍스트 없음 (finishReason={cand.get('finishReason')})")
    return text.strip()


@st.cache_data(show_spinner="요약 생성 중...", ttl=60 * 30)
def summarize_disclosure(keys: dict, corp_name: str, title: str, body: str, max_body_chars: int = 40000):
    """공시 본문을 요약. gemini→gpt-4o-mini→phi-4-mini 순 폴백. (마크다운, provider) 반환."""
    body = (body or "").strip()
    if not body:
        return "본문 텍스트가 비어 있어 요약할 수 없습니다.", None

    user_p = USER_TEMPLATE.format(corp_name=corp_name, title=title, body=body[:max_body_chars])

    chain = [
        ("gemini-2.5-flash", keys.get("gemini"), _gen_gemini),
        ("gpt-4o-mini", keys.get("openai"), _gen_openai),
        ("phi-4-mini", keys.get("openrouter"), _gen_phi),
    ]

    errors = []
    for name, key, fn in chain:
        if not key:
            continue
        try:
            text = fn(key, SYSTEM_PROMPT, user_p)
            return text, name
        except Exception as e:
            errors.append(f"{name}: {str(e)[:150]}")
            continue

    return "요약 생성 실패: " + " / ".join(errors), None


# ─────────────────────────────────────────────────────────
# LLM-as-Judge: 요약 사실성(faithfulness) 검증 레이어
# 경량 생성(phi-4-mini) → 강력 모델(claude-sonnet-4.6) 채점
# ─────────────────────────────────────────────────────────

import json as _json

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

JUDGE_SYSTEM = (
    "당신은 금융 공시 요약의 사실성(faithfulness)을 엄격하게 검증하는 평가자입니다. "
    "요약문의 각 주장이 원문에 실제로 근거하는지 항목 단위로 판정합니다. "
    "다음을 특히 엄격히 적용하십시오: "
    "(1) 요약의 숫자가 원문에서 '어느 항목의 값'인지 정확히 대조하라. "
    "다른 항목의 수치를 가져왔으면 supported=false 로 판정하라. "
    "(예: 보통주 증감 수치를 신주인수권 발행 수량으로 잘못 기재한 경우 오류) "
    "(2) 원문에 명시적으로 존재하지 않는 행위(발행·증자·감자·합병 등)를 요약이 주장하면 "
    "반드시 hallucination 으로 분류하라. 원문의 '-'(없음) 표기를 발행으로 오인하지 마라. "
    "(3) '투자자 관점 시사점'처럼 원문이 직접 말하지 않은 추론·해석은 "
    "원문 근거가 없으면 supported=false 로 처리하라. "
    "반드시 지정된 JSON 형식으로만 응답하고, 그 외의 말은 하지 마십시오."
)

JUDGE_TEMPLATE = """다음은 공시 원문과 그에 대한 요약입니다.
요약의 각 주장이 원문에 근거하는지 검증하세요.

[원문]
{body}

[요약]
{summary}

아래 JSON 형식으로만 응답하세요 (마크다운 코드블록 없이):
{{
  "score": <0-100 정수, 원문에 근거한 주장의 비율>,
  "verdict": "<신뢰가능|주의|위험 중 하나>",
  "claims": [
    {{"text": "<요약 속 주장>", "supported": <true|false>, "note": "<근거 위치 또는 문제점>"}}
  ],
  "hallucinations": ["<원문에 없는데 요약에 등장한 내용>"]
}}
"""


def _parse_judge_json(raw: str) -> dict:
    raw = raw.replace("```json", "").replace("```", "").strip()
    return _json.loads(raw)


def _judge_openai(api_key, body, summary, model):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": JUDGE_TEMPLATE.format(body=body, summary=summary)},
        ],
        "temperature": 0,
        "max_tokens": 1500,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    r = requests.post(OPENAI_URL, json=payload, headers=headers, timeout=120)
    r.raise_for_status()
    return _parse_judge_json(r.json()["choices"][0]["message"]["content"])


def _judge_gemini(api_key, body, summary, model):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    prompt = JUDGE_SYSTEM + "\n\n" + JUDGE_TEMPLATE.format(body=body, summary=summary)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0,
            "maxOutputTokens": 4096,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    r = requests.post(url, json=payload, headers=headers, timeout=120)
    r.raise_for_status()
    cand = r.json()["candidates"][0]
    parts = cand.get("content", {}).get("parts")
    if not parts:
        raise RuntimeError(f"Gemini 빈 응답 (finishReason={cand.get('finishReason')})")
    txt = "".join(part.get("text", "") for part in parts)
    if not txt.strip():
        raise RuntimeError(f"Gemini 텍스트 없음 (finishReason={cand.get('finishReason')})")
    return _parse_judge_json(txt)


def _judge_claude(api_key, body, summary, model):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": JUDGE_TEMPLATE.format(body=body, summary=summary)},
        ],
        "temperature": 0,
        "max_tokens": 1500,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    r = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=120)
    r.raise_for_status()
    return _parse_judge_json(r.json()["choices"][0]["message"]["content"])


# provider별: (키이름, 헬퍼, 기본검증모델, 상위검증모델)
_JUDGE_PROVIDERS = {
    "openrouter": ("openrouter", _judge_claude, "anthropic/claude-sonnet-4.6", "anthropic/claude-sonnet-4.6"),
    "gemini": ("gemini", _judge_gemini, "gemini-2.5-flash", "gemini-2.5-pro"),
    "openai": ("openai", _judge_openai, "gpt-4o-mini", "gpt-4o"),
}

# 생성 provider 이름(문자열) → 검증 provider 키 매핑
_GEN_TO_PROVIDER = {
    "gemini-2.5-flash": "gemini",
    "gpt-4o-mini": "openai",
    "phi-4-mini": "openrouter",
}


@st.cache_data(show_spinner="요약 검증 중...", ttl=60 * 30)
def verify_summary(keys: dict, body: str, summary: str, max_body_chars: int = 40000, gen_provider: str = None) -> dict:
    """요약 사실성 검증. 생성과 다른 provider를 우선(독립 검증), 같은 provider만 가용하면 상위 모델로 차선 검증."""
    body = (body or "").strip()[:max_body_chars]
    summary = (summary or "").strip()
    if not body or not summary:
        return {"score": 0, "verdict": "검증불가", "claims": [], "hallucinations": [], "provider": None}

    # 생성에 쓴 provider 키 (예: "gemini-2.5-flash" → "gemini")
    p_gen = _GEN_TO_PROVIDER.get(gen_provider)

    # 검증 우선순위: claude > gemini > openai (정밀도 순)
    order = ["openrouter", "gemini", "openai"]

    chain = []  # (표시이름, 키, 헬퍼, 모델)
    # 1순위: 생성과 다른 provider들 (기본 모델)
    for pk in order:
        if pk == p_gen:
            continue
        keyname, fn, base_model, _top = _JUDGE_PROVIDERS[pk]
        key = keys.get(keyname)
        if key:
            chain.append((base_model, key, fn, base_model))
    # 2순위(차선): 생성과 같은 provider → 상위 모델
    if p_gen and p_gen in _JUDGE_PROVIDERS:
        keyname, fn, base_model, top_model = _JUDGE_PROVIDERS[p_gen]
        key = keys.get(keyname)
        if key and top_model != base_model:
            chain.append((top_model, key, fn, top_model))

    errors = []
    for name, key, fn, model in chain:
        try:
            result = fn(key, body, summary, model)
            result["provider"] = name
            return result
        except Exception as e:
            errors.append(f"{name}: {str(e)[:150]}")
            continue

    return {
        "score": None,
        "verdict": "검증실패",
        "claims": [],
        "hallucinations": [],
        "provider": None,
        "errors": errors,
    }
