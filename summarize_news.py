"""
summarize_news.py — 뉴스 정답 요약 사전 생성

역할:
    news_data_paragraphs.json의 각 기사에 대해
    KoBART로 정답 요약 생성 + Clova HCX로 검증 후
    summary 필드로 저장.

    채점 시 KoBART + 검증 단계를 생략하고
    저장된 summary를 바로 사용해서 속도를 높임.

실행 방법:
    python summarize_news.py

실행 순서:
    fetch_news.py → news_cleaner.py → paragraph_splitter.py → summarize_news.py
"""

import json
import os
from dotenv import load_dotenv

load_dotenv()

def summarize_all():
    json_path = "data/news_data_paragraphs.json"

    if not os.path.exists(json_path):
        print("❌ news_data_paragraphs.json이 없습니다. paragraph_splitter.py를 먼저 실행하세요.")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        news_list = json.load(f)

    print(f"📰 총 {len(news_list)}건 요약 생성 시작...")

    # test_scoring_hcx.py의 함수 재사용
    from test_scoring_hcx import get_reference_summary_with_validation

    for i, news in enumerate(news_list):
        # 이미 summary가 있으면 건너뜀 (재실행 시 중복 방지)
        if news.get("summary"):
            print(f"[{i+1}/{len(news_list)}] 스킵 (이미 요약 있음): {news['title'][:30]}")
            continue

        try:
            contents = news.get("contents", "")
            if not contents:
                continue

            result = get_reference_summary_with_validation(contents)
            news["summary"] = result["summary"]
            print(f"[{i+1}/{len(news_list)}] 완료: {news['title'][:30]}")

        except Exception as e:
            print(f"[{i+1}/{len(news_list)}] 실패: {news['title'][:30]} — {e}")
            news["summary"] = ""

    # 결과 저장
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(news_list, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 요약 생성 완료! {json_path} 업데이트됨.")

if __name__ == "__main__":
    summarize_all()
