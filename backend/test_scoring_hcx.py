import requests
import json
import os
import re
from dotenv import load_dotenv
from transformers import PreTrainedTokenizerFast, BartForConditionalGeneration

load_dotenv()


# ============================================================
# HCX 설정
# ============================================================

HCX_API_KEY = os.getenv("CLOVA_API_KEY")
HCX_REQUEST_ID = os.getenv("CLOVA_REQUEST_ID")
HCX_ENDPOINT = os.getenv("CLOVA_ENDPOINT")


def call_hcx(prompt, max_tokens=800, temperature=0.2):
    """HCX-DASH-002 호출 기본 함수"""
    headers = {
        "Authorization": f"Bearer {HCX_API_KEY}",
        "X-NCP-CLOVASTUDIO-REQUEST-ID": HCX_REQUEST_ID,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    body = {
        "messages": [{"role": "user", "content": prompt}],
        "topP": 0.8,
        "topK": 0,
        "maxTokens": max_tokens,
        "temperature": temperature,
        "repeatPenalty": 5.0,
        "includeAiFilters": True
    }
    
    response = requests.post(HCX_ENDPOINT, headers=headers, json=body, timeout=30)
    
    if response.status_code != 200:
        raise Exception(f"HCX 호출 실패: {response.status_code}, {response.text}")
    
    return response.json()["result"]["message"]["content"]


def parse_json_safe(raw_text):
    """HCX 응답에서 JSON 안전 파싱 (response_format 강제 안 됨)"""
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"JSON 파싱 실패: {raw_text}")


# ============================================================
# KoBART 설정 (모듈 로드 시 한 번만 실행)
# ============================================================

print("KoBART 모델 로드 중... (첫 실행 시 약 500MB 다운로드)")
KOBART_MODEL_NAME = "gogamza/kobart-summarization"
kobart_tokenizer = PreTrainedTokenizerFast.from_pretrained(KOBART_MODEL_NAME)
kobart_model = BartForConditionalGeneration.from_pretrained(KOBART_MODEL_NAME)
print("KoBART 로드 완료\n")


def get_reference_summary(article_text):
    """KoBART로 정답 요약 생성 (기본)"""
    inputs = kobart_tokenizer(
        article_text,
        return_tensors="pt",
        max_length=1024,
        truncation=True
    )
    output = kobart_model.generate(
        **inputs,
        num_beams=4,
        max_length=200,
        min_length=50,
        no_repeat_ngram_size=3,
        early_stopping=True
    )
    return kobart_tokenizer.decode(output[0], skip_special_tokens=True)


def get_reference_summary_long(article_text):
    """KoBART로 더 긴 요약 (재시도용)"""
    inputs = kobart_tokenizer(
        article_text,
        return_tensors="pt",
        max_length=1024,
        truncation=True
    )
    output = kobart_model.generate(
        **inputs,
        num_beams=4,
        max_length=300,
        min_length=80,
        no_repeat_ngram_size=3,
        early_stopping=True
    )
    return kobart_tokenizer.decode(output[0], skip_special_tokens=True)


def extract_first_sentences(text, n=3):
    """원문 첫 N문장 추출 (KoBART 검증 실패 시 fallback)"""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    return " ".join(sentences[:n])


# ============================================================
# LLM 검증 함수 (HCX)
# ============================================================

def validate_summary_with_llm(article, summary):
    """
    HCX로 정답 요약의 사실 일치성 검증.
    환각, 누락, 왜곡, 의미 보존 4축 평가.
    """
    prompt = f"""당신은 뉴스 요약의 사실 정확성을 검증하는 평가자입니다.
원본 기사와 자동 생성된 요약을 받아 요약이 사실에 충실한지 평가해주세요.

[원본 기사]
{article}

[자동 생성된 요약]
{summary}

[검증 기준]
1. 환각: 요약에 원문에 없는 정보가 추가되었는가?
2. 누락: 원문의 핵심 사실이 빠지지 않았는가?
3. 왜곡: 원문의 사실이 다르게 표현되었는가? (숫자, 인물, 결과 등)
4. 의미 보존: 원문의 핵심 의미가 그대로 전달되는가?

다음 JSON 형식으로만 응답하세요:
{{
  "is_faithful": true/false,
  "fabricated_info": ["원문에 없는 추가 정보 1~2가지, 없으면 빈 배열"],
  "missing_critical": ["빠진 핵심 정보 1~2가지, 없으면 빈 배열"],
  "distortions": ["왜곡된 정보 1~2가지, 없으면 빈 배열"],
  "overall_score": 1~10 정수,
  "explanation": "검증 결과 한 줄 설명"
}}

평가 기준:
- 9~10점: 완벽하게 사실에 충실함, 핵심 잘 보존
- 7~8점: 사실 충실하지만 일부 핵심 누락 또는 사소한 표현 차이
- 5~6점: 환각 또는 누락이 있어 주의 필요
- 1~4점: 심각한 왜곡 또는 환각, 사용 부적합

JSON 외 어떤 텍스트도 포함하지 마세요."""
    
    raw = call_hcx(prompt, max_tokens=600)
    
    try:
        result = parse_json_safe(raw)
    except (ValueError, json.JSONDecodeError):
        return {
            "is_faithful": False,
            "overall_score": 0,
            "recommendation": "fallback",
            "explanation": "LLM 응답 파싱 실패",
            "raw_response": raw
        }
    
    # 점수에 따라 추천 판단
    score = result.get("overall_score", 0)
    if score >= 7:
        result["recommendation"] = "use"
    elif score >= 5:
        result["recommendation"] = "warning"
    else:
        result["recommendation"] = "fallback"
    
    return result


def get_reference_summary_with_validation(article_text, max_retries=2):
    """
    KoBART 정답 요약 생성 + HCX 검증 + 자동 fallback.
    
    검증 실패 시:
    - 1차 fallback: 더 긴 요약으로 재시도
    - 2차 fallback: 원문 첫 3문장 추출
    """
    
    for attempt in range(max_retries):
        # KoBART 요약 생성
        if attempt == 0:
            summary = get_reference_summary(article_text)
        else:
            summary = get_reference_summary_long(article_text)
        
        # HCX 검증
        validation = validate_summary_with_llm(article_text, summary)
        
        if validation["recommendation"] == "use":
            return {
                "summary": summary,
                "source": "kobart",
                "attempt": attempt + 1,
                "validation": validation
            }
        elif validation["recommendation"] == "warning":
            print(f"[검증 경고] 점수 {validation['overall_score']}/10: {validation['explanation']}")
            return {
                "summary": summary,
                "source": "kobart_with_warning",
                "attempt": attempt + 1,
                "validation": validation
            }
        else:
            print(f"[검증 실패] 시도 {attempt+1} - 점수 {validation['overall_score']}/10")
            print(f"  → 환각: {validation.get('fabricated_info', [])}")
            print(f"  → 누락: {validation.get('missing_critical', [])}")
            print(f"  → 왜곡: {validation.get('distortions', [])}")
            
            if attempt < max_retries - 1:
                continue
    
    # 모든 KoBART 시도 실패 → 추출형 fallback
    print("[Fallback] 원문 첫 3문장 추출 사용")
    fallback_summary = extract_first_sentences(article_text, n=3)
    return {
        "summary": fallback_summary,
        "source": "fallback_extract",
        "attempt": max_retries,
        "validation": {
            "recommendation": "fallback",
            "explanation": "KoBART 검증 모두 실패 — 추출형 사용"
        }
    }


# ============================================================
# 채점 함수 (HCX)
# ============================================================

def score_summary(article_body, reference_summary, user_summary):
    """HCX로 사용자 요약 채점"""
    prompt = f"""당신은 70세 이하 한국 시니어 사용자의 뉴스 학습을 평가하는 도우미입니다.
사용자가 뉴스 기사를 읽고 자신의 말로 요약했습니다.
이 요약을 정답 요약과 비교하여 평가하고, 시니어 사용자에게 친화적인 메시지를 작성해주세요.

[평가 원칙]
1. 단어 일치가 아닌 의미 일치를 평가합니다.
2. 사용자가 일상어·구어체로 표현한 것은 감점 대상이 아닙니다.
3. 원본 기사를 우선 기준으로, 정답 요약은 참고로만 활용하세요.

[시니어 친화 메시지 작성 원칙]
- 점수보다 격려와 인정을 먼저 전달
- "어르신" 같은 호칭 금지, 자연스러운 존댓말
- 부족한 점은 다음 학습으로 자연스럽게 이어지는 형태로 표현
- 숫자보다 느낌 중심
- 위압적이지 않게, 어린아이 대하듯 하지 않게
- next_step은 관련 기사 추천 안내. 잘한 경우 자신감 있게, 부족한 경우 부담 없이.
- good_points와 missing의 모든 문장은 반드시 모두 ~습니다. 체로 끝나야 함(~않음, ~없음 등 반말체 금지)

[원본 기사]
{article_body}

[참고용 정답 요약]
{reference_summary}

[사용자 요약]
{user_summary}

다음 JSON 형식으로만 응답:
{{
  "score": 0~100 정수,
  "score_breakdown": {{
    "core_facts": 0~40,
    "causation": 0~30,
    "completeness": 0~20,
    "expression": 0~10
  }},
  "strengths": ["기술적 분석용 잘한 점 1~2가지"],
  "missing": ["기술적 분석용 빠진 점 1~2가지, 없으면 빈 배열"],
  "display": {{
    "stars": 1~5 정수 (점수: 90+→5, 75+→4, 60+→3, 40+→2, 미만→1),
    "headline": "시니어 화면 첫 줄 (격려 톤, 25자 내외)",
    "good_points": ["시니어 친화 표현 잘한 점 1~2가지 (각 30자 내외)"],
    "next_step": "관련 기사 추천 안내 한 줄 (40자 내외)",
    "encouragement": "마무리 격려 한 문장 (40자 내외)"
  }}
}}

JSON 외 어떤 텍스트도 포함하지 마세요."""
    
    raw = call_hcx(prompt, max_tokens=800)
    return parse_json_safe(raw)


# ============================================================
# 메인 실행
# ============================================================

if __name__ == "__main__":
    article = """미국 항공우주국(NASA)은 제임스 웹 우주망원경이 우주 탄생 직후의 
은하들을 관측한 새 결과를 발표했다. 이번 관측에서는 적색편이 값이 14를 넘는 
은하가 다수 포착되어, 빅뱅 이후 약 3억 년 무렵의 우주 모습을 보여준다는 평가다.
연구진은 초기 우주에서도 이미 별과 가스가 빠르게 모여 은하 구조를 이루고 있었다는 
사실이 확인됐다고 전했다. 특히 일부 은하는 예상보다 훨씬 밝아, 기존 우주론 모델로 
설명하기 어렵다는 분석도 나온다."""
    
    user_summary = """제임스 웹이라는 망원경이 130억 년 전 우주를 봤는데, 그때도 
이미 별이 모여 있었대요. 너무 일찍 만들어진 것 같아서 과학자들도 놀랐다고 합니다."""
    
    # ============ 1단계 — 정답 요약 + HCX 검증 ============
    print("=" * 60)
    print("1단계: KoBART 정답 요약 + HCX 검증")
    print("=" * 60)
    summary_result = get_reference_summary_with_validation(article)
    
    print(f"\n[정답 요약 (출처: {summary_result['source']})]")
    print(summary_result["summary"])
    
    val = summary_result["validation"]
    print(f"\n[HCX 검증 결과]")
    print(f"  - 점수: {val.get('overall_score', 'N/A')}/10")
    print(f"  - 판단: {val['recommendation']}")
    print(f"  - 설명: {val.get('explanation', '')}")
    
    if val.get("fabricated_info"):
        print(f"  - 환각 의심: {val['fabricated_info']}")
    if val.get("missing_critical"):
        print(f"  - 핵심 누락: {val['missing_critical']}")
    if val.get("distortions"):
        print(f"  - 왜곡: {val['distortions']}")
    
    # ============ 2단계 — 사용자 요약 채점 ============
    print("\n" + "=" * 60)
    print("2단계: HCX로 사용자 요약 채점")
    print("=" * 60)
    result = score_summary(article, summary_result["summary"], user_summary)
    
    # ============ 결과 출력 ============
    print("\n" + "=" * 60)
    print("내부 데이터")
    print("=" * 60)
    print(f"점수: {result['score']}")
    print(f"세부 채점: {json.dumps(result['score_breakdown'], ensure_ascii=False)}")
    print(f"잘한 점: {result['strengths']}")
    print(f"빠진 점: {result['missing']}")
    
    print("\n" + "=" * 60)
    print("시니어 화면")
    print("=" * 60)
    display = result['display']
    print(f"\n  {display['headline']}")
    print(f"  {'⭐' * display['stars']}\n")
    print("  이런 점이 좋았어요:")
    for point in display['good_points']:
        print(f"    ✨ {point}")
    print(f"\n  {display['next_step']}")
    print(f"    [관련 기사 보기 →]")
    print(f"\n  {display['encouragement']}\n")