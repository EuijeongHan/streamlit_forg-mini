"""
DART Open API 연동 모듈.

제공 기능
- get_corp_code_map(): 회사명 -> corp_code 매핑 (corpCode.xml ZIP 다운로드 후 파싱)
- search_company(): 회사명 부분일치 검색
- get_disclosure_list(): 회사별 최근 공시 목록 (list.json)
- get_document_text(): 공시 본문 원문 텍스트 (document.xml ZIP)

API Key는 https://opendart.fss.or.kr 에서 무료 발급.
"""

import io
import re
import zipfile
import xml.etree.ElementTree as ET

import requests
import streamlit as st

BASE = "https://opendart.fss.or.kr/api"


# ---------------------------------------------------------------------------
# 1. 회사명 -> corp_code 매핑
#    corpCode.xml 은 전체 기업 목록을 ZIP 으로 제공한다. 용량이 크고 자주
#    바뀌지 않으므로 캐싱한다. (노트북 8장: @st.cache_data 활용)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="기업 코드 목록을 불러오는 중...", ttl=60 * 60 * 24)
def get_corp_code_map(api_key: str) -> list[dict]:
    """전체 기업의 (corp_code, corp_name, stock_code) 목록을 반환."""
    url = f"{BASE}/corpCode.xml"
    resp = requests.get(url, params={"crtfc_key": api_key}, timeout=30)
    resp.raise_for_status()

    # 응답이 ZIP 인지 확인. 키가 틀리면 JSON 에러가 온다.
    if resp.headers.get("Content-Type", "").startswith("application/json"):
        raise RuntimeError(f"DART API 오류: {resp.json().get('message', resp.text)}")

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        xml_bytes = zf.read(zf.namelist()[0])

    root = ET.fromstring(xml_bytes)
    corps = []
    for node in root.iter("list"):
        corps.append(
            {
                "corp_code": (node.findtext("corp_code") or "").strip(),
                "corp_name": (node.findtext("corp_name") or "").strip(),
                "stock_code": (node.findtext("stock_code") or "").strip(),
            }
        )
    return corps


def search_company(api_key: str, keyword: str, listed_only: bool = True) -> list[dict]:
    """회사명에 keyword 가 포함된 기업 목록을 반환."""
    corps = get_corp_code_map(api_key)
    kw = keyword.strip()
    if not kw:
        return []
    results = [c for c in corps if kw in c["corp_name"]]
    if listed_only:
        # 상장사만: stock_code 가 존재 (비상장은 공란)
        results = [c for c in results if c["stock_code"]]
    # 이름이 키워드와 정확히 같으면 우선 정렬
    results.sort(key=lambda c: (c["corp_name"] != kw, len(c["corp_name"])))
    return results[:50]


# ---------------------------------------------------------------------------
# 2. 공시 목록 조회 (list.json)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="공시 목록을 불러오는 중...", ttl=60 * 30)
def get_disclosure_list(
    api_key: str,
    corp_code: str,
    bgn_de: str,
    end_de: str,
    page_count: int = 20,
) -> list[dict]:
    """
    기간 내 공시 목록을 반환.
    bgn_de, end_de 형식: 'YYYYMMDD'
    """
    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bgn_de": bgn_de,
        "end_de": end_de,
        "page_no": 1,
        "page_count": page_count,
    }
    resp = requests.get(f"{BASE}/list.json", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    status = data.get("status")
    if status == "013":  # 조회 결과 없음
        return []
    if status != "000":
        raise RuntimeError(f"DART 공시조회 오류 [{status}]: {data.get('message')}")

    return data.get("list", [])


# ---------------------------------------------------------------------------
# 3. 공시 본문 텍스트 추출 (document.xml)
#    rcept_no 로 원문 ZIP 을 받아 내부 XML 의 텍스트를 추출한다.
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="공시 본문을 불러오는 중...", ttl=60 * 30)
def get_document_text(api_key: str, rcept_no: str, max_chars: int = 50000) -> str:
    """접수번호(rcept_no)로 공시 원문 텍스트를 추출."""
    url = f"{BASE}/document.xml"
    resp = requests.get(url, params={"crtfc_key": api_key, "rcept_no": rcept_no}, timeout=60)
    resp.raise_for_status()

    if resp.headers.get("Content-Type", "").startswith("application/json"):
        raise RuntimeError(f"DART 본문조회 오류: {resp.json().get('message', resp.text)}")

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        # ZIP 안에 여러 XML 이 있을 수 있으므로 모두 합친다.
        raw = b""
        for name in zf.namelist():
            raw += zf.read(name)

    # DART 원문은 EUC-KR/CP949 인코딩인 경우가 많다.
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp949", errors="ignore")

    return _clean_xml_text(text)[:max_chars]

def _clean_xml_text(text: str) -> str:
    """XML/HTML 태그와 엔티티를 제거하고 본문 텍스트만 남긴다."""
    # 태그 제거
    text = re.sub(r"<[^>]+>", " ", text)
    # 흔한 엔티티 정리
    text = (
        text.replace("&nbsp;", " ")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
    )
    # 공백 정리
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    # CSS 잔여물만 제거 (본문은 보존)
    kept = []
    for ln in text.split("\n"):
        st = ln.strip()
        if "{" in st or "}" in st:
            continue
        if re.fullmatch(r"[a-zA-Z\-]+\s*:\s*[^;{}]*;?", st):
            continue
        kept.append(ln)
    text = "\n".join(kept)
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    return text.strip()
