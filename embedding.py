import os
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

print("1. 원본 데이터 불러오기 및 필터링 중...")
try:
    df = pd.read_csv('data/edunet_data.csv', encoding='utf-8-sig')
except FileNotFoundError:
    print("❌ 'data/edunet_data.csv' 파일을 찾을 수 없습니다.")
    exit()

# 결측치 빈 문자열로 처리
df = df.fillna('')

# ★ 정제본문 길이가 350자 이하인 행 제거 (공백 제거 후 길이 측정)
original_len = len(df)
df = df[df['정제본문'].str.strip().str.len() > 350].reset_index(drop=True)

print(f"필터링 완료: 총 {original_len}개 중 350자 이하 데이터 {original_len - len(df)}개 제거.")
print(f"남은 유효 데이터 수: {len(df)}개")

if len(df) == 0:
    print("유효한 데이터가 없습니다. 프로그램을 종료합니다.")
    exit()

# 임베딩용 텍스트 리스트 만들기
combined_texts = []
for _, row in df.iterrows():
    subject = row.get('과목', '')
    title = row.get('제목', '')
    keyword = row.get('키워드', '')
    combined_texts.append(f"[{subject}] {title} (키워드: {keyword})")

print("\n2. AI 모델을 불러오고 데이터를 분석(벡터화)합니다... (시간이 소요됩니다)")
model = SentenceTransformer('snunlp/KR-SBERT-V40K-klueNLI-augSTS')
edunet_vecs = model.encode(combined_texts)

print("\n3. 분석 결과 저장 중...")
os.makedirs('data', exist_ok=True)

# ⭐️ 중요: 필터링되어 순서가 맞춰진 데이터프레임도 새로 저장해야 합니다.
df.to_csv('data/edunet_filtered.csv', index=False, encoding='utf-8-sig')
np.save('data/edunet_embeddings.npy', edunet_vecs)

print("✅ 성공! 'edunet_filtered.csv'와 'edunet_embeddings.npy'가 생성되었습니다.")
print("이제 추천 프로그램(2번 파일)을 실행할 수 있습니다.")
