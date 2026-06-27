"""
database.py — PostgreSQL DB 관리 모듈

1. 역할
    - 사용자 정보(users)와 학습 기록(study_logs)을 PostgreSQL DB에 저장·조회
    - Flask 서버(think_ai.py)에서 회원가입/로그인/채점/마이페이지 시 호출됨

연결 방식:
    - Railway PostgreSQL 플러그인 사용
    - 환경변수 DATABASE_URL (Railway가 자동 주입) 또는 .env에 직접 설정

테이블 구조:
    users:
        id         SERIAL   기본키, 자동 증가
        email      TEXT     이메일 (아이디, 중복 불가)
        password   TEXT     bcrypt 암호화된 비밀번호
        name       TEXT     이름
        gender     TEXT     성별
        birth      TEXT     생년월일
        education  TEXT     최종 학력
        interests  TEXT     관심사 (쉼표 구분 문자열, 예: "경제,사회")
        created_at TEXT     가입일시

    study_logs (학습 기록):
        id            SERIAL  기본키, 자동 증가
        email         TEXT    사용자 이메일 (users.email 참조)
        study_date    TEXT    학습 날짜 (예: "2026-05-29")
        article_title TEXT    읽은 기사 제목
        score         INTEGER 채점 점수 (0~100)
        created_at    TEXT    기록 생성일시
"""

import os
import bcrypt
import psycopg2
import psycopg2.extras
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def get_conn():
    """PostgreSQL 연결 반환 (Railway DATABASE_URL 사용)"""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise Exception("DATABASE_URL 환경변수가 설정되지 않았습니다.")
    # psycopg2는 postgres:// 를 postgresql:// 로 바꿔야 함
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(database_url)


# ============================================================
# DB 초기화 — 앱 시작 시 1회 실행
# ============================================================

def init_db():
    """
    users / study_logs 테이블이 없으면 생성.
    이미 있으면 아무것도 하지 않음 (IF NOT EXISTS).
    think_ai.py에서 앱 시작 시 호출.
    """
    conn = get_conn()
    cursor = conn.cursor()

    # 사용자 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         SERIAL  PRIMARY KEY,
            email      TEXT    NOT NULL UNIQUE,
            password   TEXT    NOT NULL,
            name       TEXT    NOT NULL,
            gender     TEXT,
            birth      TEXT,
            education  TEXT,
            interests  TEXT,
            created_at TEXT    NOT NULL
        )
    """)

    # 학습 기록 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS study_logs (
            id            SERIAL  PRIMARY KEY,
            email         TEXT    NOT NULL,
            study_date    TEXT    NOT NULL,
            article_title TEXT,
            score         INTEGER,
            created_at    TEXT    NOT NULL
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("✅ DB 초기화 완료 (PostgreSQL)")


# ============================================================
# 회원가입
# ============================================================

def register_user(email, password, name, gender, birth, education, interests):
    """
    새 사용자를 DB에 저장.
    비밀번호는 bcrypt로 해싱해서 저장 (평문 저장 금지).

    Args:
        email:     이메일 (중복 시 에러 반환)
        password:  평문 비밀번호 (해싱 후 저장)
        name:      이름
        gender:    성별
        birth:     생년월일
        education: 최종 학력
        interests: 관심사 리스트 (예: ["경제", "사회"])
    Returns:
        {"success": True}                                      → 가입 성공
        {"success": False, "error": "이미 사용 중인 이메일입니다."} → 중복 이메일
        {"success": False, "error": "..."}                     → 기타 오류
    """
    hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    interests_str = ",".join(interests) if isinstance(interests, list) else interests

    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (email, password, name, gender, birth, education, interests, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (email, hashed_pw, name, gender, birth, education, interests_str,
              datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        cursor.close()
        conn.close()
        return {"success": True}

    except psycopg2.errors.UniqueViolation:
        return {"success": False, "error": "이미 사용 중인 이메일입니다."}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================
# 로그인
# ============================================================

def login_user(email, password):
    """
    이메일과 비밀번호로 사용자 인증.
    bcrypt.checkpw()로 해싱된 비밀번호와 입력값을 비교.

    Args:
        email:    입력한 이메일
        password: 입력한 평문 비밀번호
    Returns:
        {"success": True, "user": { name, email, interests }} → 로그인 성공
        {"success": False, "error": "..."}                    → 실패
    """
    try:
        conn = get_conn()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if not user:
            return {"success": False, "error": "이메일 또는 비밀번호가 올바르지 않습니다."}

        if not bcrypt.checkpw(password.encode("utf-8"), user["password"].encode("utf-8")):
            return {"success": False, "error": "이메일 또는 비밀번호가 올바르지 않습니다."}

        return {
            "success": True,
            "user": {
                "name":      user["name"],
                "email":     user["email"],
                "interests": user["interests"].split(",") if user["interests"] else [],
            }
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================
# 학습 기록 저장
# ============================================================

def save_study_log(email, article_title, score):
    """
    채점 완료 시 학습 기록을 저장.
    think_ai.py의 /score 엔드포인트에서 채점 완료 후 호출됨.
    """
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO study_logs (email, study_date, article_title, score, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            email,
            datetime.now().strftime("%Y-%m-%d"),
            article_title,
            score,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"[학습 기록 저장 실패] {e}")
        return False


# ============================================================
# 학습 날짜 조회 (마이페이지 달력용)
# ============================================================

def get_study_dates(email, year):
    """
    해당 연도에 학습한 날짜 목록을 반환.
    달력에서 색칠할 날짜를 결정하는 데 사용됨.

    Args:
        email: 사용자 이메일
        year:  조회할 연도 (예: 2026)
    Returns:
        ["2026-01-03", "2026-05-15", ...] 형태의 날짜 리스트 (중복 제거, 오름차순)
    """
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT study_date
            FROM study_logs
            WHERE email = %s AND study_date LIKE %s
            ORDER BY study_date
        """, (email, f"{year}-%"))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [row[0] for row in rows]
    except Exception as e:
        print(f"[학습 날짜 조회 실패] {e}")
        return []
