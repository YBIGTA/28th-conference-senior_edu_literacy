# -*- coding: utf-8 -*-
import json
import os
import http.client
from dotenv import load_dotenv

# .env 파일 읽기
load_dotenv()

class CompletionExecutor:
    def __init__(self, host, api_key, request_id):
        self._host = host
        self._api_key = api_key
        self._request_id = request_id

    def _send_request(self, completion_request):
        headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'Authorization': self._api_key,
            'X-NCP-CLOVASTUDIO-REQUEST-ID': self._request_id
        }
        conn = http.client.HTTPSConnection(self._host)
        conn.request('POST', '/v1/api-tools/segmentation', json.dumps(completion_request), headers)
        response = conn.getresponse()
        result = json.loads(response.read().decode(encoding='utf-8'))
        # print('CLOVA 응답:', result)
        conn.close()
        return result

    def execute(self, completion_request):
        res = self._send_request(completion_request)
        if res['status']['code'] == '20000':
            return res['result']
        else:
            return 'Error'

def split_paragraphs(news_data_path, output_path, clova_api_key, request_id):
    with open(news_data_path, 'r', encoding='utf-8') as f:
        news_list = json.load(f)

    # 💡 주의: 여기서 'Bearer '를 붙여주고 있습니다. 
    # 따라서 .env 파일의 키 값에는 Bearer라는 단어가 없어야 합니다!
    executor = CompletionExecutor(
        host='clovastudio.stream.ntruss.com',
        api_key=f'Bearer {clova_api_key}', 
        request_id=request_id
    )

    results = []
    for news in news_list:
        text = news['contents']
        request_data = {
            "postProcessMaxSize": 1000,
            "alpha": 0.0,
            "segCnt": -1,
            "postProcessMinSize": 300,
            "text": text,
            "postProcess": False
        }
        split_result = executor.execute(request_data)
        
        if split_result == 'Error':
            print(f'문단 분리 실패: {news["title"]}')
            # print('요청 데이터:', request_data)
            
        news_with_paragraphs = news.copy()
        news_with_paragraphs['paragraphs'] = split_result if split_result != 'Error' else []
        results.append(news_with_paragraphs)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"문단 분리 결과를 {output_path}에 저장했습니다. 총 {len(results)}건.")

if __name__ == '__main__':
    # 👈 os.getenv를 이용해 .env에서 키를 확실히 가져오도록 수정
    CLOVA_API_KEY = os.getenv('CLOVA_API_KEY')
    REQUEST_ID = os.getenv('CLOVA_REQUEST_ID')

    # 키가 제대로 안 불려왔을 때 에러를 띄워주는 안전장치
    if not CLOVA_API_KEY:
        print("🚨 에러: .env 파일에서 CLOVA_API_KEY를 찾을 수 없습니다!")
        exit(1)

    data_dir = 'data'
    news_json_path = os.path.join(data_dir, 'news_data_cleaned.json')
    para_json_path = os.path.join(data_dir, 'news_data_paragraphs.json')
    
    split_paragraphs(news_json_path, para_json_path, CLOVA_API_KEY, REQUEST_ID)