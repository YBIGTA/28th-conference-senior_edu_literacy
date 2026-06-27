import json
import re
import os

def is_single_consonant(text):
    # 한글 자음 한 글자인지 확인 (예: ㅇ, ㄱ, ㄴ 등)
    return bool(re.fullmatch(r'[ㄱ-ㅎ]', text.strip()))

def split_by_special(text):
    # 더 이상 사용하지 않음 (문단 분리 X, 특수문자 삭제만)
    return [text]

def clean_news():
    input_path = os.path.join('data', 'news_data.json')
    output_path = os.path.join('data', 'news_data_cleaned.json')
    with open(input_path, 'r', encoding='utf-8') as f:
        news_list = json.load(f)
    cleaned_list = []
    # 자음 한 글자(ㄱ-ㅎ)와 특수문자(※◆▶◀■●△▲▼▽) 모두 삭제
    consonant_pattern = r'[ㄱ-ㅎ]'
    special_pattern = r'[※◆▶◀■●△▲▼▽]'
    for news in news_list:
        contents = news.get('contents', '')

        # 본문 내 자음 한 글자와 특수문자 모두 삭제
        cleaned = re.sub(consonant_pattern, '', contents)
        cleaned = re.sub(special_pattern, '', cleaned)

        # 줄바꿈(\n)은 그대로 유지
        news_copy = dict(news)

        news_copy['contents'] = cleaned
        cleaned_list.append(news_copy)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(cleaned_list, f, ensure_ascii=False, indent=2)
    print(f"정제 완료! {output_path}에 저장됨. (contents 필드 확인)")

if __name__ == "__main__":
    clean_news()
