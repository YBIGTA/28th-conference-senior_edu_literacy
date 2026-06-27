// =============================================================
// 역할:
//   1. 화면 전환 (로그인 → 회원가입 → 추천 목록 → 기사 읽기)
//   2. Flask 서버(think_ai.py)에 API 요청 및 결과 화면 출력
//   3. 드래그 단어 툴팁, 챗봇 대화, 요약 채점 기능
//   4. 마이페이지 달력 렌더링 + 단어장 표시
//
// 서버 요청 요약:
//   GET  /recommend?interests=...     추천 기사 5개
//   GET  /article/<type>/<id>         기사 전문
//   GET  /mypage?email=...&year=...   학습 날짜 목록 (달력용)
//   POST /word   { word, context }    단어 뜻 (Groq)
//   POST /score  { news, summary, email, article_title }  요약 채점 (KoBART + Clova HCX)
//   POST /chat   { article, ... }     챗봇 대화 (업스테이지 Solar Pro 2)
//   POST /register { ... }            회원가입
//   POST /login    { email, password } 로그인
// =============================================================


// Flask 서버 주소
// const SERVER_URL = 'http://127.0.0.1:5001';
const SERVER_URL = 'https://edudata-ieum-production.up.railway.app';

// ── 전역 상태 변수 ──────────────────────────────────────────

// 현재 로그인한 사용자 정보
// email: 학습 기록 저장(/score)과 마이페이지 달력(/mypage)에 사용
let currentUser = { name: "사용자", email: "", interests: [] };

// 현재 읽고 있는 기사
// type: "news"(보도자료) 또는 "edunet"(에듀넷)
// id: 서버 캐시/데이터프레임에서의 인덱스 번호
// content: 기사 본문 전문 — /score, /chat, /word 요청 시 서버로 전달
let currentArticle = { type: "", id: null, title: "", content: "" };

// 챗봇 대화 기록
// 시스템 메시지 제외한 user/assistant 기록만 누적
// 서버에 매 요청마다 전체 기록을 보내서 맥락 유지하도록 <-> 새 기사 선택시 초기화
let chatHistory = [];

// 세션 중 드래그해서 찾아본 단어 기록
// 마이페이지 단어장에 표시됨 (새로고침하면 초기화)
// * TODO: DB에 저장해서 영구 보관하도록 확장 가능
const wordHistory = [];

// 요약 채점까지 완료한 기사 목록 (추천 목록에서 색 표시용)
// localStorage에서 불러와서 하루 동안 유지
const completedArticles = new Set(JSON.parse(localStorage.getItem('completedArticles') || '[]'));

// ============================================================
// 화면 전환
// ============================================================
/**
 * pageID에 해당하는 페이지만 보이게 함
 * 뉴스 목록 페이지 이동시 자동으로 추천기사 불러옴
 * 마이페이지 이동시 자동으로 달력·단어장 불러옴
 *
 * @param {string} pageId - 보여줄 페이지의 HTML id 값
 */
function showPage(pageId) {
    // 1. 현재 보이는 페이지 모두 숨기고
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));

    // 2. 목표 페이지만 보이도록
    const target = document.getElementById(pageId);
    if (target) target.classList.add('active');

    // 뉴스 목록 페이지로 이동할 때만 추천 기사 자동 불러옴
    if (pageId === 'news-list-page') loadRecommendations();
    // 마이페이지로 이동할 때 달력·단어장 자동 불러옴
    if (pageId === 'mypage') loadMypage();
}

// ============================================================
// 로그인 / 회원가입 / 로그아웃
// ============================================================

// * TODO: 실제 서비스에서는 서버에 로그인 요청을 보내고 세션/토큰을 관리해야 함. -> 구현 완료
function toggleInterest(el) { el.classList.toggle('selected'); }

async function handleLogin() {
    const email    = document.getElementById('login-id').value.trim();
    const password = document.getElementById('login-pw').value;
    if (!email || !password) { alert("아이디와 비밀번호를 입력해주세요."); return; }

    try {
        const res    = await fetch(`${SERVER_URL}/login`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ email, password }),
        });
        const result = await res.json();

        if (!result.success) {
            alert(result.error);
            return;
        }

        // 서버에서 받은 실제 사용자 정보 저장
        currentUser.name      = result.user.name;
        currentUser.email     = result.user.email;   // 학습 기록 저장·달력 조회에 사용
        currentUser.interests = result.user.interests;
        updateUserUI();
        document.getElementById('main-nav').style.display = 'flex';
        alert(`반갑습니다, ${currentUser.name} 님!`);

        // 로그인 정보 localStorage에 저장
        localStorage.setItem('user', JSON.stringify({
            name: currentUser.name,
            email: currentUser.email,
            interests: currentUser.interests
        }));

        showPage('news-list-page');

    } catch (err) {
        alert("서버 연결에 실패했습니다.");
        console.error(err);
    }
}

function selectGender(gender) {
    // 숨겨진 input에 값 저장
    document.getElementById('reg-gender').value = gender;
    // 선택된 버튼 스타일 변경
    document.getElementById('gender-male').classList.remove('gender-selected');
    document.getElementById('gender-female').classList.remove('gender-selected');
    if (gender === '남성') {
        document.getElementById('gender-male').classList.add('gender-selected');
    } else {
        document.getElementById('gender-female').classList.add('gender-selected');
    }
}

// * TODO: 실제 서비스에서는 서버에 사용자 정보를 저장해야 함. -> 이것도 구현 완료
async function handleRegister() {
    const email     = document.getElementById('reg-email').value.trim();
    const password  = document.getElementById('reg-pw').value;
    const name      = document.getElementById('reg-name').value.trim();
    const gender    = document.getElementById('reg-gender').value;
    const birth     = document.getElementById('reg-birth').value;
    const chips     = document.querySelectorAll('.interest-chip.selected');
    const interests = Array.from(chips).map(c => c.getAttribute('data-value'));

    if (!email || !password) { alert("이메일과 비밀번호를 입력해주세요."); return; }
    if (!name.trim() || !gender || !birth) {
        alert("모든 정보를 입력해주세요."); return;
    }
    if (interests.length === 0) {
        alert("관심사를 1개 이상 선택해주세요."); return;
    }

    try {
        const res    = await fetch(`${SERVER_URL}/register`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ email, password, name, gender, birth, interests }),
        });
        const result = await res.json();

        if (!result.success) { alert(result.error); return; }

        // 가입 성공 → 자동 로그인 처리
        currentUser.name      = name;
        currentUser.email     = email;
        currentUser.interests = interests;
        updateUserUI();
        document.getElementById('main-nav').style.display = 'flex';
        alert(`가입 완료! ${name} 님, 맞춤 뉴스를 확인해보세요.`);

                // 회원가입 후 자동 로그인 정보 저장
        localStorage.setItem('user', JSON.stringify({
            name: currentUser.name,
            email: currentUser.email,
            interests: currentUser.interests
        }));

        showPage('news-list-page');

    } catch (err) {
        alert("서버 연결에 실패했습니다.");
        console.error(err);
    }
}

function handleLogout() {
    document.getElementById('main-nav').style.display = 'none';
    document.getElementById('login-id').value = "";
    document.getElementById('login-pw').value = "";

    // 로그아웃 시 localStorage 삭제
    localStorage.removeItem('user');

    showPage('start-page');
    alert("로그아웃 되었습니다.");
}

function updateUserUI() {
    // 화면에 표시되는 사용자 이름 갱신
    document.getElementById('user-welcome-name').innerText = currentUser.name;
    // 모든 요소 한 번에 업데이트
    document.querySelectorAll('.user-profile-name').forEach(el => el.innerText = currentUser.name);
}

// ============================================================
// 추천 뉴스 목록 (GET /recommend)
// ============================================================

/**
 * 서버에 interest 보내 추천 기사 받아와서 화면에 띄우기
 * showPage() 호출시 자동 실행
 */
async function loadRecommendations() {
    const listContainer = document.getElementById('recommended-news-list');
    listContainer.innerHTML = "<li style='padding:20px;color:#666;'>추천 기사를 불러오는 중입니다...</li>";

    // 관심사 없으면 기본값으로 사용
    // * TODO: 로그인으로 진입했을 때는 저장된 관심사 불러와서 적용하도록 수정 필요
    const interests = currentUser.interests.length > 0
        ? currentUser.interests.join(',')
        : '사회,경제';  // 관심사 미설정 시 기본값

    try {
        // 한글 관심사 URL 형식으로 인코딩
        const res  = await fetch(`${SERVER_URL}/recommend?interests=${encodeURIComponent(interests)}`);
        const data = await res.json();

        if (data.error) { listContainer.innerHTML = `<li>${data.error}</li>`; return; }

        // 추천 기사 5개 렌더링
        listContainer.innerHTML = "";
        data.recommendations.forEach(item => {
            // 에듀넷 <-> 기사 구분
            const badge = item.type === 'edunet' ? '에듀넷' : '보도자료';
            // 요약 채점까지 완료한 기사면 초록색으로 표시
            const isCompleted = completedArticles.has(`${item.type}_${item.id}`);
            const li = document.createElement('li');
            li.className = 'news-item';
            if (isCompleted) li.style.borderLeftColor = '#40c057'; // 완료: 초록색

            // 클릭시 전문 호출
            li.onclick   = () => selectArticle(item.type, item.id, item.title);
            li.innerHTML = `
                <h3>${item.title} ${isCompleted ? '✅' : ''}</h3>
                <p>${item.source}</p>
            `;
            listContainer.appendChild(li);
        });
    } catch (err) {
        listContainer.innerHTML = "<li>서버 연결에 실패했습니다. (5001번 서버 확인)</li>";
        console.error(err);
    }
}

// ============================================================
// 기사 선택 → 전문 불러오기 (GET /article/<type>/<id>)
// ============================================================
/**
 * 추천 목록에서 기사를 클릭했을 때 호출됨.
 * 서버에서 기사 전문을 받아와 화면에 표시하고,
 * 채점·챗봇 상태를 초기화함.
 *
 * @param {string} type  - "news" 또는 "edunet"
 * @param {number} id    - 서버 캐시/데이터프레임 인덱스
 * @param {string} title - 기사 제목 (로딩 중 임시 표시용)
 */
async function selectArticle(type, id, title) {
    // 기사 페이지 이동 후 로딩 상태 표시 (UX 개선)
    document.getElementById('current-article-title').innerText = "불러오는 중...";
    document.getElementById('news-content').innerText = "";
    showPage('article-page');

    try {
        const res     = await fetch(`${SERVER_URL}/article/${type}/${id}`);
        const article = await res.json();

        if (article.error) { document.getElementById('news-content').innerText = article.error; return; }

        // 전역 상태에 저장 → 이후 /score, /chat, /word 요청 시 재사용
        currentArticle = { type, id, title: article.title, content: article.content, summary: article.summary || "" };

        // 기사 제목·본문을 화면에 출력
        document.getElementById('current-article-title').innerText = article.title;
        document.getElementById('news-content').innerText          = article.content;

        // 채점·챗봇 초기화
        document.getElementById('user-summary').value         = "";
        document.getElementById('score-result').style.display = 'none';
        document.getElementById('chat-section').style.display = 'none'; // 대화창 숨김 (채점 후 표시)
        document.getElementById('bottom-nav').style.display   = 'none'; // 하단 버튼 숨김 (채점 후 표시)
        document.getElementById('chat-box').innerHTML         = "";
        chatHistory = []; // 이전 대화 기록 초기화

    } catch (err) {
        document.getElementById('news-content').innerText = "기사를 불러오는 데 실패했습니다.";
        console.error(err);
    }
}

// ============================================================
// 초기 질문 생성 (POST /chat, is_first=true)
// ============================================================
/**
 * 채점 완료 후 대화창이 열릴 때 AI가 비판적 질문 3개를 자동 생성.
 * submitSummary() 내부에서 호출됨.
 *
 * @param {string} articleContent - 기사 본문 전문
 */
async function generateInitialQuestions(articleContent) {
    const chatBox = document.getElementById('chat-box');

    // 로딩 메세지 표시
    const loadingDiv = document.createElement('div');
    loadingDiv.className  = 'chat-message ai';
    loadingDiv.innerText  = "비판적 질문을 준비하고 있습니다...";
    chatBox.appendChild(loadingDiv);

    try {
        const res  = await fetch(`${SERVER_URL}/chat`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ article: articleContent, messages: [], is_first: true }),
        });
        const data = await res.json();

        // 로딩 메시지를 실제 질문 내용으로 교체
        loadingDiv.innerText = data.answer || "질문을 생성하지 못했습니다.";

        // 생성된 질문을 AI 메시지로 대화 기록에 추가
        // → 이후 대화에서 AI가 "내가 어떤 질문을 했는지" 기억할 수 있음
        chatHistory.push({ role: "assistant", content: data.answer });
    } catch (err) {
        loadingDiv.innerText = "질문 생성에 실패했습니다.";
        console.error(err);
    }
    chatBox.scrollTop = chatBox.scrollHeight;
}

// ============================================================
// 챗봇 대화 (POST /chat, is_first=false)
// ============================================================

/**
 * 사용자가 채팅창에 메시지를 입력하고 보내기를 눌렀을 때 호출됨.
 * chatHistory 전체를 서버로 보내서 AI가 이전 대화 맥락을 유지하게 함.
 * 엔터키(onkeypress)로도 전송 가능 (index.html의 chat-input에 설정됨).
 */
async function sendChatMessage() {
    const chatInput = document.getElementById('chat-input');
    const chatBox   = document.getElementById('chat-box');
    const question  = chatInput.value.trim();
    if (!question) return; // 빈 입력 무시

    // 사용자 메시지 화면 출력
    const userDiv = document.createElement('div');
    userDiv.className = 'chat-message user';
    userDiv.innerText = question;
    chatBox.appendChild(userDiv);
    chatInput.value = "";
    chatBox.scrollTop = chatBox.scrollHeight;

    // AI 대기 메시지
    const aiDiv = document.createElement('div');
    aiDiv.className = 'chat-message ai';
    aiDiv.innerText = "생각하고 있습니다...";
    chatBox.appendChild(aiDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    // 대화 기록에 사용자 메시지 추가
    chatHistory.push({ role: "user", content: question });

    try {
        // is_first: false → 서버가 대화 이어가기 모드로 처리
        // chatHistory: 지금까지의 전체 대화 기록 (AI가 맥락 파악에 사용)
        // article: 현재 기사 본문 (서버에서 시스템 메시지에 포함시킴)
        const res  = await fetch(`${SERVER_URL}/chat`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
                article:  currentArticle.content,
                messages: chatHistory,
                is_first: false,
            }),
        });
        const data = await res.json();

        if (data.error) {
            aiDiv.innerText = "오류: " + data.error;
        } else {
            aiDiv.innerText = data.answer;
            chatHistory.push({ role: "assistant", content: data.answer });
        }
    } catch (err) {
        aiDiv.innerText = "서버 연결에 실패했습니다.";
        console.error(err);
    }
    chatBox.scrollTop = chatBox.scrollHeight;
}

// ============================================================
// 요약 채점 (POST /score)
// ============================================================

/**
 * 사용자가 요약을 작성하고 "채점 받기" 버튼을 눌렀을 때 호출됨.
 * 서버에서 KoBART로 정답 요약을 생성하고 Clova HCX로 채점한 결과를 표시.
 * 채점 완료 후 학습 기록이 DB에 저장되고, 대화창이 열림.
 *
 * 채점 결과 구조 (서버에서 반환):
 * {
 *   score: 75,                    // 총점 0~100
 *   score_breakdown: {            // 항목별 점수
 *     core_facts: 30,             // 핵심 사실 (40점 만점)
 *     causation: 25,              // 인과관계 (30점 만점)
 *     completeness: 15,           // 완전성 (20점 만점)
 *     expression: 5               // 표현 (10점 만점)
 *   },
 *   display: {                    // 화면 표시용 시니어 친화 메시지
 *     stars: 4,
 *     headline: "정말 잘 읽으셨어요!",
 *     good_points: ["핵심 내용을 잘 파악하셨어요", ...],
 *     next_step: "관련 기사를 더 읽어보세요",
 *     encouragement: "앞으로도 화이팅이세요!"
 *   }
 * }
 */
async function submitSummary() {
    const userSummary   = document.getElementById('user-summary').value.trim();
    const scoreResultDiv = document.getElementById('score-result');

    if (!userSummary) { alert("요약 내용을 입력해주세요."); return; }
    if (!currentArticle.content) { alert("기사를 먼저 선택해주세요."); return; }

    // 채점 중 로딩 상태 표시
    scoreResultDiv.style.display = 'block';
    scoreResultDiv.innerText     = "요약 내용을 확인하고 있습니다...";

    try {
        const res = await fetch(`${SERVER_URL}/score`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
                news:          currentArticle.content,
                user_summary:  userSummary,
                email:         currentUser.email,        // 학습 기록 저장용
                article_title: currentArticle.title,     // 학습 기록 저장용
                pre_summary:   currentArticle.summary,   // 미리 생성된 요약
            }),
        });
        const result = await res.json();

        if (result.error) {
            scoreResultDiv.innerText = "채점 오류: " + result.error;
        } else {
            const d = result.display;
            // 채점 완료한 기사 기록
            completedArticles.add(`${currentArticle.type}_${currentArticle.id}`);
            // localStorage에도 저장
            localStorage.setItem('completedArticles', JSON.stringify([...completedArticles]));

            // 잘한 점: 있으면 표시, 없으면 생략
            const goodPart = Array.isArray(d.good_points) && d.good_points.length > 0
                ? `✅ 잘하신 점:\n${d.good_points.map(p => `- ${p}`).join('\n')}\n\n`
                : '';

            // 아쉬운 점: 놓친 내용(missing) 먼저, 없으면 서술 아쉬움(next_step)
            const missingPart = result.missing && result.missing.length > 0
                ? `⚠️ 아쉬운 점:\n${result.missing.map(m => `- ${m}`).join('\n')}`
                : `⚠️ 아쉬운 점:\n- ${d.next_step}`;

            scoreResultDiv.innerText = `
${goodPart}${missingPart}

🌟 ${d.encouragement}`.trim();

            // 채점 완료 후 대화창 표시 + 초기 질문 생성 (2번 제출 눌러도 1개의 질문만 뜨도록)
            const chatSection = document.getElementById('chat-section');
            chatSection.style.display = 'block';
            document.getElementById('bottom-nav').style.display = 'block';
            document.getElementById('chat-box').innerHTML = ""; // 이전 질문 초기화
            chatHistory = []; // 대화 기록도 초기화
            chatSection.scrollIntoView({ behavior: 'smooth' }); // 대화창으로 스크롤
            await generateInitialQuestions(currentArticle.content);
        }
    } catch (err) {
        scoreResultDiv.innerText = "서버 연결에 실패했습니다.";
        console.error(err);
    }
}

// ============================================================
// 단어 뜻 드래그 툴팁 (POST /word)
// ============================================================

/**
 * 기사 본문에서 드래그한 단어의 뜻을 Groq에 요청해서 툴팁에 표시.
 * 아래 mouseup 이벤트 리스너에서 자동으로 호출됨.
 * 찾아본 단어는 wordHistory에 저장 → 마이페이지 단어장에 표시됨.
 *
 * @param {string} word - 드래그로 선택된 단어 (1~14자)
 */
async function fetchDefinition(word) {
    const wordDesc = document.getElementById('word-desc');
    if (wordDesc) wordDesc.innerText = "의미를 분석 중입니다...";

    try {
        const res  = await fetch(`${SERVER_URL}/word`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
                word,
                // 기사 앞부분 300자를 문맥으로 전달 for 맥락적 의미 파악
                context: currentArticle.content.slice(0, 300),
            }),
        });
        const data = await res.json();
        const definition = data.definition || "설명을 불러올 수 없습니다.";
        if (wordDesc) wordDesc.innerText = definition;

        // 세션 단어장에 추가 (중복 제거)
        if (data.definition && !wordHistory.find(w => w.word === word)) {
            wordHistory.push({ word, definition });
        }
    } catch (err) {
        if (wordDesc) wordDesc.innerText = "서버 연결에 실패했습니다.";
        console.error(err);
    }
}

// 드래그 감지
document.addEventListener('mouseup', function(e) {
    const newsContent = document.getElementById('news-content');

    // 기사 본문 밖에서 드래한 경우 무시
    if (!newsContent || !newsContent.contains(e.target)) return;

    const selected = window.getSelection().toString().trim();

    // 1~14자 사이의 선택만 툴팁 처리
    // - 1자 미만: 드래그 실패로 간주
    // - 15자 이상: 단어가 아닌 문장이므로 제외
    if (selected.length > 0 && selected.length < 15) {
        const tooltip = document.getElementById('tooltip');
        document.getElementById('word-title').innerText = selected;

        tooltip.style.left    = e.pageX + 'px';
        tooltip.style.top     = (e.pageY + 10) + 'px';
        tooltip.style.display = 'block';
        fetchDefinition(selected); // 서버에 단어 뜻 요청
    }
});

// 툴팁 닫기
document.addEventListener('mousedown', function(e) {
    const tooltip = document.getElementById('tooltip');
    if (tooltip && !tooltip.contains(e.target)) tooltip.style.display = 'none';
});

// ============================================================
// 마이페이지 — 달력 + 단어장 로드
// ============================================================

/**
 * 마이페이지 이동 시 자동 호출.
 * 서버에서 학습 날짜 목록을 받아 달력을 렌더링하고,
 * 세션 중 찾아본 단어장을 표시함.
 */
async function loadMypage() {
    const year = new Date().getFullYear();

    // 빈 달력 먼저 렌더링 (로딩 중 표시)
    renderCalendar([]);

    if (!currentUser.email) return;

    try {
        const res  = await fetch(`${SERVER_URL}/mypage?email=${encodeURIComponent(currentUser.email)}&year=${year}`);
        const data = await res.json();
        // 학습한 날짜를 받아 달력 업데이트
        renderCalendar(data.study_dates || []);
    } catch (err) {
        console.error("마이페이지 로드 실패:", err);
    }

    // 단어장 렌더링
    renderWordList();
}

/**
 * 학습 달력 렌더링
 * 1월~12월을 행으로, 1~31일을 열로 구성 (GitHub 잔디 스타일)
 * 학습한 날짜는 초록색, 오늘은 파란 테두리로 표시
 *
 * @param {string[]} studiedDates - ["2026-01-03", "2026-03-15", ...] 형태
 */
function renderCalendar(studiedDates) {
    const container = document.getElementById('study-calendar');
    if (!container) return;

    const year    = new Date().getFullYear();
    const today   = new Date().toISOString().slice(0, 10); // "2026-05-29"
    const studied = new Set(studiedDates);
    const months  = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

    // 총 학습일 수 표시
    const totalDays = studied.size;
    let html = `<p style="color:#666; font-size:15px; margin-bottom:12px;">
        총 <strong style="color:#40c057;">${totalDays}일</strong> 학습하셨어요!
    </p>`;
    html += '<div class="calendar-grid">';

    months.forEach((month, mIdx) => {
        // 해당 월의 마지막 날 (예: 2월 = 28 또는 29)
        const daysInMonth = new Date(year, mIdx + 1, 0).getDate();

        // 월 이름 레이블
        html += `<div class="cal-month-label">${month}</div>`;

        // 1~31일 칸 생성
        for (let d = 1; d <= 31; d++) {
            if (d > daysInMonth) {
                // 해당 월에 없는 날짜는 빈 칸으로 처리
                html += `<div></div>`;
            } else {
                const dateStr  = `${year}-${String(mIdx+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
                const isStudied = studied.has(dateStr);
                const isToday   = dateStr === today;
                // studied: 초록색, today: 파란 테두리
                html += `<div class="cal-day${isStudied ? ' studied' : ''}${isToday ? ' today' : ''}" title="${dateStr}"></div>`;
            }
        }
    });

    html += '</div>';
    container.innerHTML = html;
}

/**
 * 단어장 렌더링
 * 이번 세션에서 드래그해서 찾아본 단어 목록을 표시.
 * wordHistory 배열에서 읽어옴.
 */
function renderWordList() {
    const container = document.getElementById('word-list');
    if (!container) return;

    if (wordHistory.length === 0) {
        container.innerHTML = '<p style="color:#aaa; font-size:16px;">아직 찾아본 단어가 없어요.</p>';
        return;
    }

    const items = wordHistory.map(w =>
        `<div style="padding:12px 16px; background:#f8f9fa; border-radius:10px; margin-bottom:10px; font-size:17px;">
            <strong style="color:#007bff;">${w.word}</strong>: ${w.definition}
        </div>`
    ).join('');
    container.innerHTML = items;
}

// 초기 페이지
// HTML이 완전히 로드된 후 localStorage에 저장된 로그인 정보 확인
// 저장된 정보가 있으면 자동 로그인, 없으면 로그인 화면 표시
window.addEventListener('DOMContentLoaded', () => {
    const saved = localStorage.getItem('user');
    if (saved) {
        const user = JSON.parse(saved);
        currentUser.name      = user.name;
        currentUser.email     = user.email;
        currentUser.interests = user.interests;
        updateUserUI();
        document.getElementById('main-nav').style.display = 'flex';
        showPage('news-list-page');
    } else {
        showPage('start-page');
    }
});