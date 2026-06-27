# 생각이음 (Saenggak-ieum)

> 시니어가 뉴스를 읽고, 요약하고, AI와 대화하며 문해력을 키우는 웹 서비스

**배포 URL:** https://edudata-ieum-production.up.railway.app

---

## 주요 기능

### 1. 맞춤형 뉴스 추천
- 사용자 관심사(예: "경제,IT과학")를 **SBERT**로 768차원 벡터로 변환
- **보도자료 3개**: `news_data_paragraphs.json`에서 불러온 기사 제목을 실시간 SBERT 임베딩 후 코사인 유사도 상위 3개 선택
- **에듀넷 2개**: 사전 계산된 `edunet_embeddings.npy` 재사용 → 코사인 유사도 상위 2개 선택
- 총 5개 추천 반환

### 2. 기사 본문 전문 제공
- **Clova Segmentation API** (`paragraph_splitter.py`)로 사전 처리된 문단 분리 본문 제공
- 모르는 단어 드래그 → **Groq (llama-3.3-70b)** 으로 시니어 친화 뜻 풀이

### 3. 요약 작성 및 채점
- 사용자 요약 제출
- **KoBART**로 정답 요약 사전 생성 + **Clova HCX**로 사실성 검증 (환각·누락·왜곡·의미보존 4축 평가)
- 채점 시 사전 생성된 요약 재사용 → KoBART 실행 생략으로 속도 향상
- **Clova HCX**로 사용자 요약 채점 (핵심사실 40점·인과관계 30점·완전성 20점·표현 10점)
- 잘한 점 → 아쉬운 점 → 격려 메시지 순으로 피드백 제공

### 4. AI 토론 (비판적 사고)
- 채점 완료 후 **업스테이지 Solar Pro 2**로 비판적 질문 3개 자동 생성
- 사용자 답변 → AI 피드백 반복 대화

---

## 파일 구조

```
edu_data/
│
├── think_ai.py           # Flask 메인 서버 (라우팅 전담, 매일 00:00 뉴스 자동 갱신 스케줄러 내장)
├── recommend.py          # 추천 로직 (SBERT 코사인 유사도, JSON 캐시 로드)
├── test_scoring_hcx.py   # 요약 채점 (KoBART 정답 요약 생성 + Clova HCX 검증·채점)
├── ai_client.py          # AI 엔진 통합 호출 (Groq / 업스테이지 / Clova / Gemini)
├── database.py           # SQLite DB 관리 (users, study_logs)
├── prompt.py             # AI 프롬프트 관리 (질문 생성·대화 규칙)
│
├── fetch_news.py         # 교육부 보도자료 API 호출 (350자 미만 필터링 포함)
├── news_cleaner.py       # 보도자료 특수문자·자음 제거
├── paragraph_splitter.py # Clova Segmentation API로 뉴스 문단 분리
├── summarize_news.py     # KoBART + Clova HCX로 정답 요약 사전 생성 (채점 속도 향상용)
├── embedding.py          # 에듀넷 SBERT 임베딩 사전 생성 (최초 1회, 350자 이하 필터링)
│
├── index.html            # 프론트엔드 화면
├── script.js             # 프론트엔드 동작 (API 요청, 달력, 단어장, localStorage 로그인 유지)
├── Procfile              # Railway 배포 시작 명령어
├── requirements.txt      # 패키지 목록
│
├── data/
│   ├── edunet_filtered.csv          # 필터링된 에듀넷 자료 (350자 이상)
│   ├── edunet_embeddings.npy        # 에듀넷 SBERT 임베딩 벡터 (사전 계산)
│   └── news_data_paragraphs.json    # 문단 분리 + 사전 요약 포함 보도자료
│
└── users.db              # SQLite DB (사용자 정보 + 학습 기록)
```

---

## AI 사용 현황

| 기능 | AI | 모델 |
|------|-----|------|
| 단어 뜻 풀이 | Groq | llama-3.3-70b-versatile |
| 챗봇 질문 생성 / 대화 | 업스테이지 | Solar Pro 2 |
| 정답 요약 생성 | KoBART | gogamza/kobart-summarization |
| 정답 요약 검증 | Clova HCX | HCX-DASH-002 |
| 사용자 요약 채점 | Clova HCX | HCX-DASH-002 |
| 뉴스 문단 분리 | Clova | Segmentation API |

---

## 서버 API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/` | index.html 서빙 |
| GET | `/recommend?interests=경제,사회` | 추천 기사 5개 반환 |
| GET | `/article/<type>/<id>` | 기사 전문 반환 (type: news / edunet) |
| GET | `/mypage?email=...&year=...` | 학습 날짜 목록 (달력용) |
| POST | `/word` | 단어 뜻 풀이 (Groq) |
| POST | `/score` | 요약 채점 (KoBART + Clova HCX) |
| POST | `/chat` | 챗봇 대화 (업스테이지) |
| POST | `/register` | 회원가입 |
| POST | `/login` | 로그인 |

---

## 실행 방법

### 1. 패키지 설치

```bash
pip install -r requirements.txt
```

### 2. .env 파일 설정

```
news_api=공공데이터포털_보도자료_API_키
GROQ_API_KEY=Groq_API_키
UPSTAGE_API_KEY=업스테이지_API_키
CLOVA_API_KEY=Clova_Bearer_토큰 (Bearer 제외하고 입력)
CLOVA_REQUEST_ID=Clova_Request_ID
CLOVA_ENDPOINT=Clova_HCX_엔드포인트
```

### 3. 에듀넷 임베딩 생성 (최초 1회)

```bash
python embedding.py
```

### 4. 뉴스 데이터 준비 (매일 1회 / 서버에서는 자동 실행)

```bash
python fetch_news.py        # 어제~오늘 보도자료 수집 (350자 미만 필터링)
python news_cleaner.py      # 특수문자·자음 제거
python paragraph_splitter.py # Clova로 문단 분리 (약 3분 소요)
python summarize_news.py    # KoBART + Clova로 정답 요약 사전 생성
```

### 5. 서버 실행

```bash
python think_ai.py
```

브라우저에서 `http://127.0.0.1:5001` 접속

---

## 배포

**Railway Hobby 플랜** 사용 ($5/월)

- 매일 00:00 자동으로 뉴스 갱신 (`think_ai.py` 스케줄러 내장)
- Healthcheck Path: `/`, Timeout: 300초
- 환경변수: Railway 대시보드 Variables 탭에 설정


# 생각이음 — 프롬프트 정리

프롬프트는 `prompt.py`와 `test_scoring_hcx.py` 두 파일에 나뉘어 있음.

---

## 1. 초기 질문 생성 (`get_question_system_prompt`)
**위치:** `prompt.py` → `think_ai.py /chat (is_first=true)`  
**AI:** 업스테이지 Solar Pro 2  
**역할:** 기사 선택 후 자동으로 비판적 질문 3개 생성

### 시스템 프롬프트 핵심 규칙
- 50대 이상 시니어 대상 독서 지도사 역할
- 문해력 교육 정보(`literacy_information`) 참고
- 질문 3개만 출력 (인사말·마크다운·외국어 금지)
- 질문 유형이 서로 달라야 함

### 질문 구성 방식
| 번호 | 유형 |
|------|------|
| 1번 | 기사의 핵심 사실 확인 |
| 2번 | 내용 기반 깊이 있는 추론 |
| 3번 | 시니어의 삶·경험과 연결된 비판적 의견 |

---

## 2. 챗봇 대화 (`get_conversation_system_msg`)
**위치:** `prompt.py` → `think_ai.py /chat (is_first=false)`  
**AI:** 업스테이지 Solar Pro 2  
**역할:** 사용자 답변에 피드백 + 심화 질문으로 대화 이어가기

### 대화 규칙
1. 사실 관계가 틀린 경우 "하지만 기사에서는~"으로 부드럽게 바로잡기 (무조건 칭찬 금지)
2. 피드백 후 심화 질문 1개 필수 (한 번에 하나씩만)
3. 마크다운 문법 절대 금지 (평문 줄글만)
4. 외국어 절대 금지 (순수 한국어만)
5. 친절한 존댓말 (~요, ~습니까?)

---

## 3. 단어 뜻 풀이
**위치:** `think_ai.py /word`  
**AI:** Groq llama-3.3-70b  
**역할:** 드래그한 단어를 시니어 눈높이로 한 문장 설명

# 프롬프트 구조
```
'{word}'라는 단어의 뜻을 시니어가 이해하기 쉽도록 한 문장으로 친절하게 설명해줘.

[문맥]
{기사 앞부분 300자}
```

---

## 4. 정답 요약 검증 (`validate_summary_with_llm`)
**위치:** `test_scoring_hcx.py`  
**AI:** Clova HCX-DASH-002  
**역할:** KoBART가 생성한 정답 요약의 사실 일치성 검증

### 검증 4축
| 축 | 설명 |
|----|------|
| 환각 | 원문에 없는 정보가 추가됐는가 |
| 누락 | 핵심 사실이 빠졌는가 |
| 왜곡 | 숫자·인물·결과가 다르게 표현됐는가 |
| 의미 보존 | 핵심 의미가 그대로 전달되는가 |

### 점수 기준 및 처리
| 점수 | 판단 | 처리 |
|------|------|------|
| 7~10 | use | 그대로 사용 |
| 5~6 | warning | 경고 로그 후 사용 |
| 1~4 | fallback | 더 긴 요약으로 재시도 → 원문 첫 3문장 추출 |

---

## 5. 사용자 요약 채점 (`score_summary`)
**위치:** `test_scoring_hcx.py`  
**AI:** Clova HCX-DASH-002  
**역할:** 사용자 요약을 정답 요약과 비교 채점

### 채점 기준
| 항목 | 배점 |
|------|------|
| 핵심 사실 (core_facts) | 40점 |
| 인과관계 (causation) | 30점 |
| 완전성 (completeness) | 20점 |
| 표현 (expression) | 10점 |

### 피드백 작성 원칙
- 점수보다 격려와 인정 먼저
- "어르신" 호칭 금지, 자연스러운 존댓말
- 부족한 점은 다음 학습으로 자연스럽게 이어지는 형태
- good_points와 missing 모두 ~습니다. 체로 통일 (반말체 금지)
- next_step은 관련 기사 추천 안내

### 반환 구조
```json
{
  "score": 75,
  "score_breakdown": { "core_facts": 30, "causation": 25, "completeness": 15, "expression": 5 },
  "strengths": ["기술적 분석용 잘한 점"],
  "missing": ["기술적 분석용 빠진 점"],
  "display": {
    "stars": 4,
    "headline": "시니어 화면 첫 줄",
    "good_points": ["잘하신 점 1~2가지"],
    "next_step": "관련 기사 추천 한 줄",
    "encouragement": "마무리 격려 한 문장"
  }
}
```

---

## 문해력 교육 정보 (`literacy_information`)
**위치:** `prompt.py`  
**사용처:** 초기 질문 생성 + 챗봇 대화 프롬프트에 공통 참조

국어과 교육과정 기반 문해력 개념 정의. 이해하기(읽기)·표현하기(쓰기)·언어지식·태도 4가지 영역으로 구성. AI가 질문을 생성하거나 대화를 이어갈 때 문해력 교육 목표에 맞게 유도하기 위한 참고 자료로 사용됨.


## 팀원 소개

| 이름 | 역할 | 
| :--- | :--- |
| **김현수** | 데이터 수집 및 모델링 | 
| **이근하** | 서비스 기획 및 데이터 분석 | 
| **임수빈** | 코드 통합 및 디자인 | 