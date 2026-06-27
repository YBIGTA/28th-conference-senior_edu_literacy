"""
AI 엔진 호출

1. 역할 :
    Groq, 업스테이지, Clova, Gemini 4가지 AI 엔진 -> call_ai() 함수로 호출
    엔진 변경 희망시 think_ai.py에서 engine = "(수정)"

    * 호출시 방식
    - Clova는 전용 SDK가 없어서 requests로 직접 호출
    - Groq, 업스테이지, Gemini는 각자 SDK 제공

2. 기능별 엔진
    단어 뜻 풀이 (/word)  → engine="groq" (속도 중시)
    챗봇 대화   (/chat)  → engine="upstage"  (한국어 처리 중시)
    채점        (/score) → Clova HCX 직접 호출 (test_scoring_hcx.py에서 처리)
"""
import os
import requests
from google import genai
from dotenv import load_dotenv
from openai import OpenAI
import uuid

load_dotenv()

# ============================================================
# Groq 호출 함수
# ============================================================
def get_groq_client():
    """ Groq API Client 생성"""
    return OpenAI(
        api_key=os.environ.get("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    )

# ============================================================
# Upstage 호출 함수
# ============================================================
def get_upstage_client():
    """
    Upstage API Client 생성
    - model : Solar / 한국어 특화 / 31B 파라미터.
    - OpenAI 호환 API라 get_groq_client()와 코드 구조가 완전히 동일.
    """
    # 업스테이지는 OpenAI 호환 API라 구조가 Groq과 동일
    return OpenAI(
        api_key=os.environ.get("UPSTAGE_API_KEY"),
        base_url="https://api.upstage.ai/v1",
    )

# ============================================================
# Clova 호출 함수
# ============================================================
def call_clova_gpt(prompt, max_tokens=2048, temperature=0.7, system_msg=None, stream=False):
    """
    Clova HCX 함수 호출
    - clova는 네이버가 독자적으로 만든 거라서 requests 활용해서 직접 HTTP 요청을 보내야 함.
    - test_scoring_hcx.py의 call_hcx()와 별개
    - conversation.py 등 CLI(Command Line Interface - 터미널에서 명령어로 실행하는 프로그램) 도구에서 Cloa 엔진 선택시 사용

    Args:
        prompt:      사용자 메시지 텍스트
        max_tokens:  최대 출력 토큰 수
        temperature: 창의성 조절 (0~1, 높을수록 다양한 응답)
        system_msg:  시스템 메시지 (AI 역할·규칙 지정)
        stream:      스트리밍 모드 여부 (True면 실시간 출력)
    Returns:
        응답 JSON 딕셔너리 (stream=False 시)
        None (stream=True 시, 결과를 print로 출력)
    """
    url = "https://clovastudio.stream.ntruss.com/v3/chat-completions/HCX-007"
    bearer_token = os.environ.get("CLOVA_API_KEY")

    # Request ID가 없으면 UUID로 자동 생성 (Clova API 필수 헤더)
    request_id = os.environ.get("CLOVA_REQUEST_ID") or str(uuid.uuid4()).replace('-', '')
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "X-NCP-CLOVASTUDIO-REQUEST-ID": request_id,
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "text/event-stream" if stream else "application/json"
    }

    # 시스템 메시지가 있으면 messages 배열 맨 앞에 추가
    messages = []
    if system_msg:
        messages.append({"role": "system", "content": system_msg})
    messages.append({"role": "user", "content": prompt})
    data = {
        "messages": messages,
        "maxCompletionTokens": max_tokens,
        "temperature": temperature,
        "topP": 0.8,
        "topK": 0,
        "repetitionPenalty": 1.1, # 동일 표현 반복 방지
        "seed": 0,
        "includeAiFilters": True  # 유해 콘텐츠 필터 활성화
    }

    if stream:
        # 스트리밍: 응답이 올 때마다 한 줄씩 실시간 출력
        with requests.post(url, headers=headers, json=data, stream=True) as r:
            for line in r.iter_lines():
                if line:
                    print(line.decode("utf-8"))
        return None
    else:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()

# ============================================================
# Gemini 호출 함수
# ============================================================
def call_gemini(prompt, max_tokens=1024, temperature=0.7):
    """
    Google Gemini 모델 호출.
    - HTTP에 요청을 보내는 건 맞는데, 직접 requests 쓰는 게 아니라 Google이 만든 SDK(google-genai)가 내부적으로 요청을 대신 보내줌
        - 위에서 moule 미리 깔아두기 필요
    - 현재는 call_ai(engine="gemini")로만 사용 가능.
    - messages 형식을 지원하지 않아 텍스트 prompt만 받음.

    Args:
        prompt:      사용자 프롬프트 텍스트
        max_tokens:  최대 출력 토큰 수 (Gemini SDK에서는 직접 제어 안 됨)
        temperature: 창의성 조절
    Returns:
        응답 텍스트 문자열
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY가 .env에 없습니다.")
    client = genai.Client(api_key=api_key)
    model_name = "gemini-2.5-flash"
    if not prompt:
        prompt = "(질문을 생성할 뉴스 전문이 없습니다.)"
    response = client.models.generate_content(
        model=model_name,
        contents=prompt
    ).text
    return response

# ============================================================
# 통합 호출 함수 - 외부에서 사용할 함수
# ============================================================
def call_ai(prompt=None, engine="groq", messages=None, **kwargs):
    """
    AI 엔진을 선택해서 호출

    Args:
        prompt:   단일 텍스트 프롬프트 (messages 없을 때 사용)
        engine:   사용할 AI 엔진 ("groq" / "upstage" / "clova" / "gemini")
        messages: 대화 기록 리스트 [{"role": "...", "content": "..."}]
                  prompt보다 messages가 우선 적용됨
        **kwargs: 추가 옵션
                  - model: 모델명 (기본값은 엔진별로 다름)
                  - max_tokens: 최대 출력 토큰 수 (기본 1024)
                  - temperature: 창의성 조절 (기본 0.7)
                  - stream: 스트리밍 여부 (Clova만 지원, 기본 False)
    Returns:
        Groq/업스테이지: OpenAI ChatCompletion 객체
                         → resp.choices[0].message.content 로 텍스트 추출
        Clova:           응답 JSON 딕셔너리
                         → resp["result"]["message"]["content"] 로 텍스트 추출
        Gemini:          응답 텍스트 문자열 (이미 추출된 상태)
    """
    # ── Groq ──────────────────────────────────────────────────
    # /word
    if engine == "groq":
        client = get_groq_client()
        if messages is not None:
            use_messages = messages
        elif prompt is not None:
            use_messages = [{"role": "user", "content": prompt}]
        else:
            raise ValueError("Either prompt or messages must be provided for groq.")
        return client.chat.completions.create(
            model=kwargs.get("model", "llama-3.3-70b-versatile"),
            messages=use_messages,
            max_tokens=kwargs.get("max_tokens", 1024),
            temperature=kwargs.get("temperature", 0.7),
        )

    # ── 업스테이지 (OpenAI 호환, Groq과 구조 동일) ────────────
    # /chat
    elif engine == "upstage":
        client = get_upstage_client()
        if messages is not None:
            use_messages = messages
        elif prompt is not None:
            use_messages = [{"role": "user", "content": prompt}]
        else:
            raise ValueError("Either prompt or messages must be provided for upstage.")
        return client.chat.completions.create(
            # 업스테이지 Solar 모델 (한국어 성능 우수)
            model=kwargs.get("model", "solar-pro2"),
            messages=use_messages,
            max_tokens=kwargs.get("max_tokens", 1024),
            temperature=kwargs.get("temperature", 0.7),
        )

    # ── Clova ─────────────────────────────────────────────────
    # CLI 도구
    # /score는 test_scoring.py의 call_hcx()를 직접 사용
    elif engine == "clova":
        # messages[0]이 system이면 분리해서 call_clova_gpt의 system_msg로 전달
        system_msg = None
        if messages and len(messages) > 0 and messages[0].get("role") == "system":
            system_msg = messages[0]["content"]
            user_prompt = messages[1]["content"] if len(messages) > 1 else prompt
        else:
            user_prompt = prompt
        return call_clova_gpt(
            user_prompt,
            max_tokens=kwargs.get("max_tokens", 2048),
            temperature=kwargs.get("temperature", 0.7),
            system_msg=system_msg,
            stream=kwargs.get("stream", False)
        )

    # ── Gemini ────────────────────────────────────────────────
    # CLI 도구
    elif engine == "gemini":
        if messages:
            prompt_text = "\n".join([m["content"] for m in messages if "content" in m])
        else:
            prompt_text = prompt
        return call_gemini(
            prompt_text,
            max_tokens=kwargs.get("max_tokens", 1024),
            temperature=kwargs.get("temperature", 0.7),
        )

    else:
        raise ValueError(f"Unknown engine: {engine}")
