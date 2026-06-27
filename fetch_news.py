import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from dotenv import load_dotenv
from bs4 import BeautifulSoup

def text_cleaner(text):
    ### 본문에서 HTML 태그 제거
    if not text:
        return ""
    soup = BeautifulSoup(text, 'html.parser')
    return soup.get_text(strip=True)

def get_clean_news():
    load_dotenv()
    service_key = os.getenv('news_api')

    if not service_key:
        print("오류: .env 파일에 'news_api' 키가 설정되지 않았습니다.")
        return []

    today = datetime.now()
    yesterday = today - timedelta(days=1)
    start_date = yesterday.strftime('%Y%m%d')
    end_date = today.strftime('%Y%m%d')

    url = 'http://apis.data.go.kr/1371000/pressReleaseService/pressReleaseList' 
    params = {
        'serviceKey': service_key,
        'startDate': start_date,
        'endDate': end_date
    }

    response = requests.get(url, params=params)
    clean_news_list = []

    if response.status_code == 200:
        root = ET.fromstring(response.content)
        result_code = root.find('.//resultCode')
        
        if result_code is not None and result_code.text in ['0', '00']:
            items = root.findall('.//NewsItem')
            for item in items:
                raw_title = item.findtext('Title')
                raw_minister = item.findtext('MinisterCode')
                raw_contents = item.findtext('DataContents')
                
                cleaned_title = text_cleaner(raw_title)
                cleaned_minister = text_cleaner(raw_minister)
                cleaned_contents = text_cleaner(raw_contents)
                
                # ==========================================
                # [데이터 필터링 핵심 로직]
                # ==========================================
                
                # 1. 제목이 아예 없는 경우 제외
                if not cleaned_title:
                    continue
                    
                # 2. 본문 내용이 아예 없는 경우 제외
                if not cleaned_contents:
                    continue
                    
                # 3. 본문에서 '파일'/'붙임'을 언급하는 경우 제외 (내용이 어느 정도 있더라도 파일 내용을 확인할 수 없기 때문에...)
                if '파일' in cleaned_contents or '붙임' in cleaned_contents:
                    continue
                    
                if len(cleaned_contents) < 350:
                    ## 파일이 언급되어 있지 않아도 무의미한 내용만 있는 짧은 기사가 있기 때문에 이를 거르기 위해...
                    continue    
                # ==========================================
                
                clean_news_list.append({
                    'title': cleaned_title,
                    'minister': cleaned_minister if cleaned_minister else "부처미상",
                    'contents': cleaned_contents
                })
        else:
            print("API 호출은 성공했으나, 정상적인 데이터를 불러오지 못했습니다.")
    else:
        print(f"HTTP 요청 에러 발생: {response.status_code}")

    return clean_news_list

if __name__ == '__main__':
    import json
    news_list = get_clean_news()
    with open('./data/news_data.json', 'w', encoding='utf-8') as f:
        json.dump(news_list, f, ensure_ascii=False, indent=2)
    print(f"{len(news_list)}건의 뉴스를 ./data/news_data.json 파일에 저장했습니다.")