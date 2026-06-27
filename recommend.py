"""
recommendaton algorithm

1. 역할
    1) 사용자 관심사를 SBERT로 임베딩
    2) 보도자료(실시간 API)와 에듀넷(사전 임베딩)에서 코사인 유사도 기반으로 기사를 추천
    3) 전문으로 반환

    * SBERT 모델과 edunet 데이터는 앱 시작 시 로드하고 그 뒤로는 재사용


2. 외부(think_ai.py)에서 사용하는 함수:
    get_recommendations(interests)  → 보도자료 3개 + edunet 2개 반환
    get_news_article(idx)           → 보도자료 전문 반환
    get_edunet_article(idx)         → 에듀넷 자료 전문 반환

3. 추천 알고리즘 흐름:
    1. 사용자 관심사 문자열 → SBERT 임베딩 → 벡터
    2. 보도자료: API로 받은 최신 뉴스를 실시간 임베딩 → 유사도 계산 → 상위 3개
    3. 에듀넷: 미리 저장된 임베딩(.npy) 재사용 → 유사도 계산 → 상위 2개
    4. 합쳐서 5개 반환
"""

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from fetch_news import get_clean_news
import json

# ============================================================
# 앱 시작 시 1회 로드
# ============================================================

print("Loading SBERT Model...")
_SBERT = SentenceTransformer("snunlp/KR-SBERT-V40K-klueNLI-augSTS")
print("Loading edunet Model...")

print("Loading edunet data...")
try:
    # edunet_filtered.csv: embedding.py 실행 시 생성된 필터링된 에듀넷 자료
    _EDUNET_DF   = pd.read_csv("data/edunet_filtered.csv", encoding="utf-8-sig").fillna("")
    # edunet_embeddings.npy: 각 에듀넷 자료의 SBERT 임베딩 벡터를 미리 계산해둔 파일
    _EDUNET_VECS = np.load("data/edunet_embeddings.npy")
    print(f"successfully loading edunet data ({len(_EDUNET_DF)}개)")

except FileNotFoundError:
    # embedding.py를 실행하지 않은 경우
    print("No edunet data. Run embedding.py first.")
    _EDUNET_DF   = pd.DataFrame()
    _EDUNET_VECS = np.array([])

# 보도자료는 요청마다 갱신 (실시간 API)
_news_cache: list = []


# ============================================================
# 내부 헬퍼
# ============================================================

def _refresh_news():
    """
    서버 시작 시 또는 자정 갱신 후 한 번만 로드.
    캐시가 이미 있으면 재사용.
    """
    global _news_cache

    # 이미 로드됐으면 재사용
    if _news_cache:
        return

    json_path = "data/news_data_paragraphs.json"
    try:
        import json as _json
        with open(json_path, 'r', encoding='utf-8') as f:
            _news_cache = _json.load(f)
        print(f"✅ 뉴스 캐시 로드 완료 ({len(_news_cache)}건)")
    except FileNotFoundError:
        print("⚠️ news_data_paragraphs.json 없음. API로 fallback.")
        _news_cache = get_clean_news()

def _recommend_news(interest_vec: np.ndarray, top_n: int = 3) -> list:
    """
    보도자료에서 유사도 상위 top_n개 반환.

    Algorithm:
    1. 각 보도자료의 "[부처명] 제목" 텍스트를 SBERT로 임베딩
    2. 사용자 관심사 벡터와의 코사인 유사도 계산
    3. 유사도 내림차순으로 정렬 후 상위 top_n개 선택

    Args:
        interest_vec: 사용자 관심사를 SBERT로 임베딩한 벡터 (shape: (1, 768))
        top_n: 반환할 기사 수 (기본값 3)
    Returns:
        [{ id, type, title, source, similarity }, ...]
        id -> _news_cache 리스트의 인덱스 / 기사 전문 요청 시 사용

    """
    if not _news_cache:
        return []

    # "[부처명] 제목"
    texts = [f"[{n['minister']}] {n['title']}" for n in _news_cache]
    vecs  = _SBERT.encode(texts)

    # 코사인 유사도
    sims  = cosine_similarity(interest_vec, vecs)[0]
    top_idx = np.argsort(sims)[::-1][:top_n]

    return [
        {
            "id":         int(idx),                     # 기사 전문 요청
            "type":       "news",                       # FE -> 보도자료/에듀넷 구분할 태그
            "title":      _news_cache[idx]["title"],
            "source":     _news_cache[idx]["minister"], # 발행부처
            "similarity": round(float(sims[idx]), 3),   # 소수점 처리(소수점 아리 3자리)
        }
        for idx in top_idx
    ]


def _recommend_edunet(interest_vec: np.ndarray, top_n: int = 2) -> list:
    """
    edunet에서 유사도 상위 top_n개 반환.

    Algorithm:
    1. 미리 저장된 edunet_embeddings.npy 로드 (앱 시작 시 1회)
    2. 사용자 관심사 벡터와의 코사인 유사도 계산
    3. 유사도 내림차순으로 정렬 후 상위 top_n개 선택

    Args:
        interest_vec: 사용자 관심사를 SBERT로 임베딩한 벡터 (shape: (1, 768))
        top_n: 반환할 자료 수 (기본값 2)
    Returns:
        [{ id, type, title, source, similarity }, ...]
        id -> _EDUNET_DF 데이터프레임의 행 인덱스 / 자료 전문 요청 시 사용
    """
    if _EDUNET_VECS.size == 0:
        # .npy 파일이 없는 경우
        return []

    # 미리 계산한 임베딩 재사용
    sims = cosine_similarity(interest_vec, _EDUNET_VECS)[0]
    top_idx = np.argsort(sims)[::-1][:top_n]

    return [
        {
            "id":         int(idx),                             # 자료 전문 요청
            "type":       "edunet",                             # FE -> 보도자료/에듀넷 태그
            "title":      _EDUNET_DF.iloc[idx].get("제목", ""),
            "source":     _EDUNET_DF.iloc[idx].get("과목", ""),  # 과목명
            "similarity": round(float(sims[idx]), 3),           # 소수점 처리(소수점 아래 3자리)
        }
        for idx in top_idx
    ]


# ============================================================
# 외부에서 사용하는 함수
# ============================================================

def get_recommendations(interests: str) -> list:
    """
    관심사 문자열을 받아 보도자료 3개 + edunet 2개를 반환.

    Args:
        interests: 쉼표 구분 문자열 = index.html의 관심사 값들이 넘어옴
    Returns:
        list of dict  (type / id / title / source / similarity)
    """
    # 매 요청마다 최신 보도자료로 갱신
    _refresh_news()

    # 유사도 계산하기 위한 단계 (텍스트 -> 숫자로)
    interest_vec = _SBERT.encode([interests])

    # 보도자료
    news_recs    = _recommend_news(interest_vec, top_n=3)
    edunet_recs  = _recommend_edunet(interest_vec, top_n=2)

    return news_recs + edunet_recs


def get_news_article(idx: int) -> dict:
    """
    캐시된 보도자료에서 인덱스 idx번 전문 반환.
    Loc: /article/edunet/<id>

    Args:
        idx: _news_cache 리스트의 인덱스 (추천 결과의 id 값)
    Returns:
        { type, title, source, content }
        기사를 찾을 수 없으면 빈 딕셔너리 {} 반환 (404 error)
    """
    if not _news_cache or idx >= len(_news_cache):
        return {}
    news = _news_cache[idx]

    # paragraphs['topicSeg']가 있으면 문단 나누기 적용
    paragraphs = news.get("paragraphs")
    if paragraphs and isinstance(paragraphs, dict) and paragraphs.get("topicSeg"):
        # topicSeg는 [[문장1, 문장2], [문장3]] 형태 → 문단별로 합치기
        content = "\n\n".join(
            " ".join(sentences) for sentences in paragraphs["topicSeg"]
        )
    else:
        content = news.get("contents", "")

    return {
        "type": "news",
        "title": news["title"],
        "source": news["minister"],
        "content": content,
        "summary": news.get("summary", ""), # 미리 생성된 요약
    }

def get_edunet_article(idx: int) -> dict:
    """
    edunet 데이터프레임에서 인덱스 idx번 전문 반환.
    Loc: /article/edunet/<id>

    Args:
        idx: _EDUNET_DF 데이터프레임의 행 인덱스 (추천 결과의 id 값)
    Returns:
        { type, title, source, content }
        자료를 찾을 수 없으면 빈 딕셔너리 {} 반환
    """
    if _EDUNET_DF.empty or idx >= len(_EDUNET_DF):
        return {}
    row = _EDUNET_DF.iloc[idx]
    return {
        "type":    "edunet",
        "title":   row.get("제목", ""),
        "source":  row.get("과목", ""),   # 과목명
        "content": row.get("정제본문", ""),   # 정제된 자료 전문
    }
