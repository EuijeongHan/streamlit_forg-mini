# foRG-mini

DART 공시 원문을 가져와 **phi-4-mini**(OpenRouter)로 요약하는 Streamlit 프로토타입.
포트폴리오 프로젝트 foRG의 미니버전.

## 구조

```
forg-mini/
├─ app.py                 # 홈: 회사 검색
├─ pages/
│  └─ 01_공시요약.py       # 공시 목록 → 본문 → 요약
├─ src/
│  ├─ dart.py             # DART API (corp_code, 공시검색, 본문추출)
│  └─ llm.py              # OpenRouter phi-4-mini 요약
├─ .streamlit/
│  └─ secrets.toml        # API 키 (커밋 금지)
├─ requirements.txt
└─ README.md
```

## 키 발급

- DART: https://opendart.fss.or.kr (무료)
- OpenRouter: https://openrouter.ai/keys (`microsoft/phi-4-mini-instruct` 사용)

## 로컬 실행

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # 키 입력
streamlit run app.py
```

## Streamlit Cloud 배포

1. GitHub 푸시 (secrets.toml 은 .gitignore 로 제외됨)
2. share.streamlit.io → 저장소 연결
3. App settings → Secrets 에 `DART_API_KEY`, `OPENROUTER_API_KEY` 입력
4. 모델은 OpenRouter에서 실행되므로 Cloud 1GB 메모리 한도와 무관

## 동작 흐름

```
회사명 → corp_code 매핑(corpCode.xml, 캐싱)
       → 공시검색(list.json)
       → 본문추출(document.xml ZIP → 텍스트)
       → phi-4-mini 요약(128K 컨텍스트, truncation 최소화)
       → 좌(요약)/우(원문) 출력
```

## 노트북 4-3 학습요소 반영

| 요소 | 위치 |
|------|------|
| secrets.toml 키 관리 | 전 페이지 `get_secret()` |
| @st.cache_data | dart.py, llm.py |
| st.session_state | 회사·본문·요약 유지 |
| columns / sidebar | app.py, 01_공시요약.py |
| pages/ 다중페이지 | pages/ |
| Cloud 배포 | OpenRouter로 메모리 제약 해소 |
