"""
Flask 메인 서버 (라우팅 전담)

1. 역할
    - 브라우저(index.html/script.js)와 백엔드 로직을 연결
    - 실제 AI 처리·추천 계산은 각 모듈에 위임하고, URL 라우팅과 요청/응답 처리만 담당

엔드포인트:
    GET  /                                  → index.html
    GET  /recommend?interests=경제,사회      → 추천 기사 반환
    GET  /article/<type>/<int:id>           → 기사 전문 반환
    GET  /mypage?email=...&year=2026        → 학습 날짜 목록 반환 (달력용)
    POST /word   { word, context? }         → 단어 뜻 (Groq)
    POST /score  { news, user_summary, email, article_title } → 요약 채점 + 학습 기록 저장
    POST /chat   { article, messages, is_first } → 챗봇 (업스테이지 Solar Pro 2)
    POST /register { email, password, name, gender, birth, education, interests } → 회원가입
    POST /login    { email, password }      → 로그인

필요한 .env 키:
    news_api          공공데이터포털 보도자료 API 키
    GROQ_API_KEY      Groq API 키
    CLOVA_API_KEY     Clova Studio Bearer 토큰 (nv-로 시작)
    CLOVA_REQUEST_ID  Clova Request ID
    CLOVA_ENDPOINT    Clova HCX 채팅 엔드포인트
    UPSTAGE_API_KEY   업스테이지 API 키
"""

from pathlib import Path
import sys
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

from recommend import get_recommendations, get_news_article, get_edunet_article
from test_scoring_hcx import get_reference_summary_with_validation, score_summary
from ai_client import call_ai
from prompt import (
    get_conversation_system_msg,
    get_question_system_prompt,
)
from database import init_db, register_user, login_user, save_study_log, get_study_dates

import schedule
import threading
import subprocess
import time

BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

# .env에서 API 키 로드
load_dotenv(dotenv_path=BASE_DIR / ".env")

app = Flask(__name__, static_folder=str(FRONTEND_DIR), template_folder=str(FRONTEND_DIR))
# 한글 깨지지 않도록
app.config["JSON_AS_ASCII"] = False
CORS(app)

# 앱 시작 시 DB 초기화 (users.db 없으면 자동 생성)
init_db()

# ============================================================
# 뉴스 자동 갱신 스케줄러 (매일 00:00)
# ============================================================

def update_news():
    """매일 자정에 뉴스 갱신 (fetch → clean → split → summarize)"""
    print("🔄 뉴스 자동 갱신 시작...")
    subprocess.run([sys.executable, str(BACKEND_DIR / "fetch_news.py")], cwd=str(BASE_DIR), check=False)
    subprocess.run([sys.executable, str(BACKEND_DIR / "news_cleaner.py")], cwd=str(BASE_DIR), check=False)
    subprocess.run([sys.executable, str(BACKEND_DIR / "paragraph_splitter.py")], cwd=str(BASE_DIR), check=False)
    subprocess.run([sys.executable, str(BACKEND_DIR / "summarize_news.py")], cwd=str(BASE_DIR), check=False)  # 정답 요약 사전 생성

    # 캐시 초기화 → 다음 추천 요청 시 새 파일 로드
    from recommend import _news_cache
    _news_cache.clear()
    print("✅ 뉴스 자동 갱신 완료")

def run_scheduler():
    """백그라운드에서 스케줄러 실행"""
    schedule.every().day.at("00:00").do(update_news)
    while True:
        schedule.run_pending()
        time.sleep(60)

# 서버 시작 시 백그라운드 스케줄러 실행
threading.Thread(target=run_scheduler, daemon=True).start()

# ============================================================
# 정적 파일 (index.html / script.js) 서빙
# ============================================================

@app.route("/")
def home():
    return send_from_directory(str(FRONTEND_DIR), "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(str(FRONTEND_DIR), path)


# ============================================================
# 회원가입 - POST /register
# ============================================================

@app.route("/register", methods=["POST"])
def register():
    data      = request.json or {}
    email     = data.get("email", "").strip()
    password  = data.get("password", "")
    name      = data.get("name", "").strip()
    gender    = data.get("gender", "")
    birth     = data.get("birth", "")
    education = data.get("education", "")
    interests = data.get("interests", [])  # 리스트로 받음 (예: ["경제", "사회"])

    if not email or not password or not name:
        return jsonify({"success": False, "error": "이메일, 비밀번호, 이름은 필수입니다."}), 400

    result = register_user(email, password, name, gender, birth, education, interests)
    return jsonify(result)


# ============================================================
# 로그인 - POST /login
# ============================================================

@app.route("/login", methods=["POST"])
def login():
    data     = request.json or {}
    email    = data.get("email", "").strip()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"success": False, "error": "이메일과 비밀번호를 입력해주세요."}), 400

    result = login_user(email, password)
    return jsonify(result)


# ============================================================
# 추천 기사 반환 - GET /recommend?interests
# ============================================================

@app.route("/recommend", methods=["GET"])
def recommend():
    # URL에서 interests 파라미터 읽기
    interests = request.args.get("interests", "").strip()
    if not interests:
        return jsonify({"error": "interests 파라미터가 없습니다."}), 400

    try:
        results = get_recommendations(interests)
        return jsonify({"interests": interests, "recommendations": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# 전문 가져오기 - GET /article/<type>/<id>
# ============================================================

@app.route("/article/<article_type>/<int:article_id>", methods=["GET"])
def get_article(article_type: str, article_id: int):
    if article_type == "news":
        article = get_news_article(article_id)
    elif article_type == "edunet":
        article = get_edunet_article(article_id)
    else:
        return jsonify({"error": "type은 news 또는 edunet이어야 합니다."}), 400

    if not article:
        return jsonify({"error": "해당 기사를 찾을 수 없습니다."}), 404

    return jsonify(article)


# ============================================================
# 단어 뜻 - POST /word  — 단어 뜻 (Groq)
# ============================================================

@app.route("/word", methods=["POST"])
def word_definition():
    data    = request.json or {}
    word    = data.get("word", "").strip()
    context = data.get("context", "")

    if not word:
        return jsonify({"error": "word가 없습니다."}), 400

    # 시니어 눈높이에 맞는 한 문장 설명을 요청하는 프롬프트
    prompt = f"'{word}'라는 단어의 뜻을 시니어가 이해하기 쉽도록 한 문장으로 친절하게 설명해줘."
    if context:
        # 기사 문맥 함께 넘기기 (앞 300자)
        prompt += f"\n\n[문맥]\n{context}"

    try:
        resp   = call_ai(
            prompt=prompt,
            engine="groq",
            model="llama-3.3-70b-versatile",
            max_tokens=200,
        )
        answer = resp.choices[0].message.content
        return jsonify({"word": word, "definition": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# 요약 채점 (KoBART + Clova HCX) - POST /score
# ============================================================

@app.route("/score", methods=["POST"])
def score():
    data          = request.json or {}
    news_text     = data.get("news", "")
    user_summary  = data.get("user_summary", "")
    email         = data.get("email", "")           # 학습 기록 저장용
    article_title = data.get("article_title", "")   # 학습 기록 저장용
    pre_summary = data.get("pre_summary", "")  # 미리 생성된 요약 (프론트에서 전달)

    if not news_text or not user_summary:
        return jsonify({"error": "news와 user_summary가 모두 필요합니다."}), 400

    try:
        if pre_summary:
            # 미리 생성된 요약이 있으면 KoBART + 검증 생략
            ref_summary = pre_summary
        else:
            # 없으면 기존 방식으로 생성
            ref_data = get_reference_summary_with_validation(news_text)
            ref_summary = ref_data["summary"]

        result = score_summary(news_text, ref_summary, user_summary)

        if email:
            save_study_log(email, article_title, result.get("score", 0))

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# 챗봇 (Upstage) - POST /chat
# ============================================================

@app.route("/chat", methods=["POST"])
def chat():
    """
    is_first=true  → 기사 기반 초기 질문 3개 생성
    is_first=false → 대화 이어가기 (messages에 누적된 기록 사용)

    body:
    {
        "article":  "기사 본문 전체",
        "messages": [{"role": "user"/"assistant", "content": "..."}],
        "is_first": true / false
    }
    """
    data     = request.json or {}
    article  = data.get("article", "")
    messages = data.get("messages", [])
    is_first = data.get("is_first", False)

    if not article:
        return jsonify({"error": "article이 없습니다."}), 400

    try:
        if is_first:
            # 초기 질문 3개 생성
            full_messages = [
                {"role": "system", "content": get_question_system_prompt()},
                {"role": "user",   "content": f"[뉴스 전문]\n{article}\n\n위 뉴스를 읽고 시니어를 위한 질문 3개를 만들어주세요."},
            ]
        else:
            # 대화 이어가기 — 시스템 메시지에 기사 본문 포함
            system_msg = get_conversation_system_msg(questions="")
            system_msg += f"\n\n[현재 기사 본문]\n{article}"
            full_messages = [{"role": "system", "content": system_msg}] + messages

        resp   = call_ai(
            engine="upstage",
            messages=full_messages,
            # 챗봇에 사용되는 모델
            model="solar-pro2",
            max_tokens=1024,
        )
        answer = resp.choices[0].message.content
        return jsonify({"answer": answer})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# 마이페이지 달력 데이터 - GET /mypage?email=...&year=2026
# ============================================================

@app.route("/mypage", methods=["GET"])
def mypage():
    email = request.args.get("email", "").strip()
    year  = request.args.get("year", str(2026))

    if not email:
        return jsonify({"error": "email이 필요합니다."}), 400

    # 해당 연도에 학습한 날짜 목록 반환 (달력 색칠용)
    dates = get_study_dates(email, year)
    return jsonify({"study_dates": dates})


# ============================================================
# 서버 실행
# ============================================================

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)