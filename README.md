# foRG-mini

DART(금융감독원 전자공시) 공시 원문을 **생성 AI로 요약**하고, **생성에 쓰지 않은 다른 AI가 그 요약의 사실성을 검증**하는 Streamlit 앱.
포트폴리오 프로젝트 foRG의 미니버전으로, 단일 공시에 대한 "요약 → 독립 검증" 파이프라인을 다룬다.

## 핵심 특징

- **요약 생성 폴백 체인**: `gemini-2.5-flash → gpt-4o-mini → phi-4-mini` 순으로 시도. 앞선 모델이 실패(크레딧 부족·빈 응답 등)하면 다음 모델로 자동 전환.
- **LLM-as-Judge 사실성 검증**: 생성된 요약을 원문과 대조해 항목별로 채점(`supported` 여부, hallucination 탐지, 0–100 신뢰도, 판정).
- **독립 검증 보장**: 검증 모델은 **생성에 쓰인 provider와 다른 provider**를 우선 사용한다. 다른 provider가 모두 불가할 때만 같은 provider의 **상위 모델**(예: gemini-2.5-flash 생성 → gemini-2.5-pro 검증)로 차선 검증한다. 자기 출력을 자기가 채점하는 자기검증을 방지.
- **접근 제어**: 비밀번호 게이트 + 전역 일일 호출 제한(요약 1회/검증 2회 차감)으로 공개 배포 시 API 비용을 방어.
- 별도 프로젝트 **입찰메이트**(RAG·하이브리드 검색·LLM-as-Judge)에서 검증한 평가 파이프라인 역량을 금융 공시 도메인으로 옮긴 작업이다.

## 설계 의사결정 (왜 이렇게 만들었나)

- **경량 생성 + 강력 검증**: phi-4-mini(7B) 단독 요약은 한국어 표에서 단위 오류(예: '4,605주'를 '4,605조')와 원문에 없는 항목 생성(hallucination)이 잦았다. 검증 레이어로 이를 정량 측정하고, 생성 모델을 상향 + 프롬프트를 강화했다. 동일 공시(임원 지분변동 보고서) 기준 검증 신뢰도 점수가 phi-4-mini 50점(위험) → gemini-2.5-flash 100점(신뢰가능)으로 개선됐다(단일 공시 실측 예시이며 일반화된 벤치마크는 아님).
- **생성과 검증의 provider 분리**: 생성자와 검증자가 같은 모델이면 같은 약점을 공유해 오류를 못 잡는다. 그래서 검증은 항상 다른 provider를 우선하도록 설계했다.
- **정형 vs 비정형**: 본 앱은 `document.xml` 비정형 원문 요약 경로를 다룬다. 전환사채·유상증자 등 정형 API가 있는 공시 유형은 본체 foRG에서 필드 기반으로 처리한다.

## 데모


## 구조

```
forg-mini/
├─ app.py                 # 홈: 회사 검색(부분일치)·선택, 검색 이력, 비번 게이트
├─ pages/
│  └─ 01_공시요약.py       # 공시 목록 → 본문 → 요약 → 검증
├─ src/
│  ├─ dart.py             # DART API (corp_code, 공시검색, 본문추출)
│  ├─ llm.py              # 요약 생성/검증 폴백 체인, LLM-as-Judge
│  └─ gate.py             # 비밀번호 게이트 + 전역 일일 호출 제한
├─ .streamlit/
│  └─ secrets.toml        # API 키 (커밋 금지, .gitignore 처리)
├─ requirements.txt
└─ README.md
```

## 필요한 키 (secrets.toml)

```toml
DART_API_KEY       = "..."   # https://opendart.fss.or.kr (무료)
OPENROUTER_API_KEY = "..."   # https://openrouter.ai/keys (phi-4-mini, claude 검증용)
OPENAI_API_KEY     = "..."   # https://platform.openai.com/api-keys
GEMINI_API_KEY     = "..."   # https://aistudio.google.com/apikey
APP_PASSWORD       = "..."   # 앱 접근 비밀번호 (임의 지정)
```

생성·검증은 가용한 키만 사용한다. 일부 키만 있어도 폴백 체인이 가능한 모델로 동작한다.

## 로컬 실행

```bash
pip install -r requirements.txt
# .streamlit/secrets.toml 에 위 5개 키 입력
streamlit run app.py
```

## Streamlit Cloud 배포

1. GitHub 푸시 (`secrets.toml` 은 `.gitignore` 로 제외됨)
2. share.streamlit.io → 저장소 연결, main file `app.py`
3. App settings → Secrets 에 위 5개 키 입력
4. 모든 모델이 외부 API에서 실행되므로 Cloud 무료 1GB 메모리 한도와 무관

## 동작 흐름

```
회사명 → corp_code 매핑(corpCode.xml, 캐싱)
       → 공시검색(list.json)
       → 본문추출(document.xml ZIP → 텍스트 클린징)
       → 요약 생성(gemini → gpt-4o-mini → phi 폴백)
       → 사실성 검증(생성과 다른 provider로 항목별 채점)
       → 요약·검증 결과 + 원문 출력
```

## 한계

- 전역 호출 카운터는 앱 인스턴스 메모리 기반이라 재시작 시 리셋된다. 비밀번호 게이트가 1차 방벽이므로 실사용엔 충분하나, 영구 카운터가 필요하면 외부 저장소(예: PostgreSQL)가 필요하다.
- 검증의 "신뢰도 점수"는 LLM 판정값이며 절대적 정답이 아니다. 참고 지표로 사용한다.

## 노트북 4-3 학습요소 반영

| 요소 | 위치 |
|------|------|
| secrets.toml 키 관리 | 전 페이지 `get_secret()` |
| @st.cache_data | dart.py, llm.py |
| st.session_state | 회사·본문·요약·검증·검색이력 유지 |
| columns / sidebar | app.py, 01_공시요약.py |
| pages/ 다중페이지 | pages/ |
| Cloud 배포 | 외부 API로 메모리 제약 해소 |
