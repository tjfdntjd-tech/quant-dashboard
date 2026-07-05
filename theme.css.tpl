<style>
    /* ── 폰트 임포트 ──────────────────────────────────────────────── *
     * 디스플레이 & 본문: Manrope (모던/미니멀)                         *
     * 데이터: JetBrains Mono (가격/티커/지표 — 자릿수 정렬되는 단말기 느낌) */
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap');

    :root {
        --font-display: 'Manrope', 'Apple SD Gothic Neo', 'Malgun Gothic', 'Segoe UI', sans-serif;
        --font-body:    'Manrope', 'Apple SD Gothic Neo', 'Malgun Gothic', system-ui, sans-serif;
        --font-mono:    'JetBrains Mono', 'Consolas', monospace;

        /* ── 섹션별 시그니처 컬러 (순수 색상) ─────────────────────── */
        --c-amber:  #f5b942;
        --c-teal:   #2dd4bf;
        --c-indigo: #6366f1;
        --c-violet: #a78bfa;
        --c-cyan:   #38bdf8;
        --c-rose:   #fb7185;
        --c-green:  #34d399;
        --c-red:    #f87171;
        --c-blue:   #60a5fa;
        --c-orange: #ff6a00;

        /* ── 통일 액센트 컬러 (Blobs 목업 참고 — 코랄/피치 단일 강조색) ── */
        --c-accent:     #f5a973;
        --c-accent-ink: #2a1a10;   /* 액센트 배경 위 텍스트 (고대비) */
        --c-accent-a15: rgba(245,169,115,0.15);
        --c-accent-a25: rgba(245,169,115,0.25);
        --c-accent-a45: rgba(245,169,115,0.45);
        --c-accent-hov: #f8bd8e;

        /* ── 알파 변형 (border-left, 배경, 아이콘 등) ──────────────── */
        --c-amber-a65:  rgba(245,185,66,0.65);
        --c-amber-a32:  rgba(245,185,66,0.32);
        --c-amber-a12:  rgba(245,185,66,0.12);
        --c-amber-a45:  rgba(245,185,66,0.45);
        --c-amber-a30:  rgba(245,185,66,0.3);
        --c-amber-a18:  rgba(245,185,66,0.18);

        --c-teal-a65:   rgba(45,212,191,0.65);
        --c-teal-a32:   rgba(45,212,191,0.32);
        --c-teal-a12:   rgba(45,212,191,0.12);
        --c-teal-a45:   rgba(45,212,191,0.45);

        --c-indigo-a65: rgba(99,102,241,0.65);
        --c-indigo-a32: rgba(99,102,241,0.32);
        --c-indigo-a12: rgba(99,102,241,0.12);
        --c-indigo-a45: rgba(99,102,241,0.45);
        --c-indigo-a20: rgba(99,102,241,0.2);
        --c-indigo-a15: rgba(99,102,241,0.15);
        --c-indigo-a35: rgba(99,102,241,0.35);

        --c-violet-a65: rgba(167,139,250,0.65);
        --c-violet-a32: rgba(167,139,250,0.32);
        --c-violet-a12: rgba(167,139,250,0.12);
        --c-violet-a45: rgba(167,139,250,0.45);

        --c-cyan-a65:   rgba(56,189,248,0.65);
        --c-cyan-a32:   rgba(56,189,248,0.32);
        --c-cyan-a12:   rgba(56,189,248,0.12);
        --c-cyan-a45:   rgba(56,189,248,0.45);
        --c-cyan-a25:   rgba(56,189,248,0.25);

        --c-rose-a65:   rgba(251,113,133,0.65);
        --c-rose-a32:   rgba(251,113,133,0.32);
        --c-rose-a12:   rgba(251,113,133,0.12);
        --c-rose-a45:   rgba(251,113,133,0.45);
        --c-rose-a16:   rgba(251,113,133,0.16);

        --c-green-a15:  rgba(52,211,153,0.15);
        --c-green-a30:  rgba(52,211,153,0.3);
        --c-green-a06:  rgba(52,211,153,0.06);
        --c-green-a05:  rgba(52,211,153,0.05);

        --c-red-a15:    rgba(248,113,113,0.15);
        --c-red-a30:    rgba(248,113,113,0.3);
        --c-red-a06:    rgba(248,113,113,0.06);
        --c-red-a05:    rgba(248,113,113,0.05);
        --c-red-a18:    rgba(239,68,68,0.18);
        --c-red-a45:    rgba(239,68,68,0.45);
        --c-red-a20:    rgba(239,68,68,0.2);
        --c-red-a35:    rgba(239,68,68,0.35);
        --c-red-a12:    rgba(239,68,68,0.12);

        --c-blue-a15:   rgba(96,165,250,0.15);
        --c-blue-a30:   rgba(96,165,250,0.3);

        --c-orange-a12: rgba(255,106,0,0.12);
        --c-orange-a25: rgba(255,106,0,0.25);

        --c-violet-std: rgba(139,92,246,0.3);   /* 섹션 아이콘 기본 보라 */
        --c-violet-bdr: rgba(139,92,246,0.35);
        --c-violet-bdr2:rgba(139,92,246,0.4);
        --c-violet-bdr3:rgba(139,92,246,0.65);
        --c-violet-a25: rgba(139,92,246,0.25);
        --c-violet-a20: rgba(139,92,246,0.2);

        --c-yellow-a15: rgba(251,191,36,0.15);
        --c-yellow-a30: rgba(251,191,36,0.3);
        --c-yellow-a06: rgba(251,191,36,0.06);
        --c-yellow-a12: rgba(245,158,11,0.12);
    }

    /* ── 전역 배경 & 폰트 ─────────────────────────────────────────── */
    html, body, [data-testid="stAppViewContainer"] {
        background-image: ${mesh_bg_layers}$mesh_bg_comma ${bg_main} !important;
        background-size: ${mesh_bg_size} !important;
        background-attachment: fixed !important;
        animation: ${mesh_bg_anim};
        font-family: var(--font-body);
    }
    ${mesh_keyframes_css}
    ${particle_overlay_css}
    h1, h2, h3, .app-header h1, .section-title, .glass-card-title,
    .scan-title, .alert-title { font-family: var(--font-display); }
    .metric-value, .metric-delta, .sector-pct, .sector-sub, .sector-ticker,
    [data-testid="stDataFrame"] * {
        font-family: var(--font-mono) !important;
        font-variant-numeric: tabular-nums;
    }
    [data-testid="stAppViewContainer"] > .main { background: transparent !important; }
    .block-container { padding: 1.2rem 1.5rem 2rem 1.5rem !important; max-width: 900px; }

    /* ── 사이드바 ──────────────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        background: ${bg_sidebar} !important;
        border-right: 1px solid rgba(139, 92, 246, 0.2);
    }
    [data-testid="stSidebar"] .stTextInput input {
        background: ${sidebar_input_bg} !important;
        border: 1px solid ${sidebar_input_bdr} !important;
        border-radius: 10px !important;
        color: ${sidebar_input_clr} !important;
        font-family: var(--font-mono) !important;
        font-size: 1rem !important;
        letter-spacing: 0.5px !important;
        padding: 0.6rem 0.8rem !important;
    }

    /* ── 헤더 배너 ─────────────────────────────────────────────────── */
    .app-header {
        background: linear-gradient(135deg, rgba(245,185,66,0.18) 0%, rgba(251,113,133,0.16) 45%, rgba(99,102,241,0.2) 100%);
        border: 1px solid rgba(245,185,66,0.3);
        border-radius: 22px;
        padding: 1.4rem 1.8rem;
        margin-bottom: 1.4rem;
        backdrop-filter: blur(12px);
        box-shadow: 0 8px 32px rgba(99,102,241,0.15), inset 0 1px 0 rgba(255,255,255,0.08);
    }
    .app-header h1 {
        margin: 0 0 0.2rem 0;
        font-size: 1.15rem;
        font-weight: 800;
        background: linear-gradient(90deg, #f5b942, #fb7185, #818cf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        letter-spacing: -0.3px;
    }
    .app-header p {
        margin: 0;
        color: ${text_muted};
        font-size: 0.72rem;
    }

    /* ── 글래스 카드 공통 ──────────────────────────────────────────── */
    .glass-card {
        background: ${glass_bg};
        border: 1px solid ${glass_border};
        border-radius: 20px;
        padding: 1.15rem 1.25rem;
        margin-bottom: 1rem;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }
    .glass-card-title {
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 1.2px;
        text-transform: uppercase;
        color: ${text_muted};
        margin-bottom: 0.6rem;
    }

    /* ── 메트릭 카드 ──────────────────────────────────────────────── */
    .metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-bottom: 1rem; }
    .metric-card {
        background: ${metric_bg};
        border: 1px solid ${metric_bdr};
        border-radius: 18px;
        padding: 1rem 1.1rem;
        backdrop-filter: blur(8px);
        box-shadow: 0 2px 12px rgba(0,0,0,0.2);
        transition: transform 0.15s;
    }
    .metric-card:hover { transform: translateY(-2px); }
    .metric-card { border-left: 3px solid transparent; }
    .mc-amber  { border-left-color: var(--c-amber-a65)  !important; }
    .mc-violet { border-left-color: var(--c-violet-a65) !important; }
    .mc-rose   { border-left-color: var(--c-rose-a65)   !important; }
    .mc-cyan   { border-left-color: var(--c-cyan-a65)   !important; }
    .mc-indigo { border-left-color: var(--c-indigo-a65) !important; }
    .mc-teal   { border-left-color: var(--c-teal-a65)   !important; }
    .metric-label { font-size: 0.7rem; color: ${metric_label}; font-weight: 600; letter-spacing: 0.8px; text-transform: uppercase; margin-bottom: 0.35rem; }
    .metric-value { font-size: 1.45rem; font-weight: 800; color: ${text_primary}; line-height: 1; }
    .metric-delta { font-size: 0.78rem; font-weight: 600; margin-top: 0.3rem; }
    .delta-up   { color: #34d399; }
    .delta-down { color: #f87171; }
    .delta-neu  { color: #94a3b8; }

    /* ── 상단 st.metric 스코어보드 글씨 크기 축소 ─────────────────────── */
    [data-testid="stMetric"] { gap: 0.15rem; }
    [data-testid="stMetricLabel"] { font-size: 0.72rem !important; }
    [data-testid="stMetricValue"] { font-size: 1.3rem !important; line-height: 1.15 !important; }
    [data-testid="stMetricDelta"] { font-size: 0.72rem !important; }
    [data-testid="stMetricValue"] > div {
        overflow: visible !important;
        white-space: nowrap !important;
        text-overflow: clip !important;
    }

    /* ── 신호 알림 배너 ────────────────────────────────────────────── */
    .alert-banner {
        background: linear-gradient(135deg, var(--c-red-a18), var(--c-yellow-a12));
        border: 1px solid var(--c-red-a45);
        border-radius: 14px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
        display: flex;
        align-items: flex-start;
        gap: 0.7rem;
        box-shadow: 0 0 20px var(--c-red-a12);
    }
    .alert-icon { font-size: 1.4rem; line-height: 1; }
    .alert-title { font-size: 0.72rem; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; color: #fca5a5; margin-bottom: 0.3rem; }
    .alert-signals { display: flex; flex-wrap: wrap; gap: 0.4rem; }
    .signal-chip {
        background: var(--c-red-a20);
        border: 1px solid var(--c-red-a35);
        border-radius: 20px;
        padding: 0.2rem 0.7rem;
        font-size: 0.75rem;
        font-weight: 600;
        color: #fca5a5;
    }
    .china-banner {
        background: linear-gradient(135deg, rgba(220,38,38,0.28), rgba(220,38,38,0.12));
        border: 1.5px solid rgba(248,113,113,0.75);
        border-radius: 14px;
        padding: 0.85rem 1.2rem;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 0.7rem;
        box-shadow: 0 0 22px rgba(220,38,38,0.25);
    }
    .china-banner-icon { font-size: 1.3rem; line-height: 1; }
    .china-banner-text { font-size: 0.85rem; font-weight: 700; color: #fecaca; letter-spacing: 0.3px; }
    .china-banner-sub { font-size: 0.72rem; font-weight: 500; color: rgba(254,202,202,0.75); margin-top: 0.15rem; }
    .split-banner {
        background: linear-gradient(135deg, rgba(245,158,11,0.22), rgba(245,158,11,0.08));
        border: 1.5px solid rgba(251,191,36,0.6);
        border-radius: 14px;
        padding: 0.85rem 1.2rem;
        margin-bottom: 0.8rem;
    }
    .split-banner-title { font-size: 0.85rem; font-weight: 700; color: #fbbf24; letter-spacing: 0.3px; margin-bottom: 0.3rem; }
    .split-banner-body  { font-size: 0.8rem; color: ${text_status}; line-height: 1.5; }
    .split-banner-body strong { color: ${text_primary}; }

    /* ── 섹션 헤더 ─────────────────────────────────────────────────── */
    .section-header {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin: 1.3rem 0 0.7rem 0;
    }
    .section-icon {
        width: 32px; height: 32px;
        background: linear-gradient(135deg, var(--c-violet-std), var(--c-indigo-a20));
        border: 1px solid var(--c-violet-bdr);
        border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 0.9rem;
        flex-shrink: 0;
    }
    /* 섹션별 시그니처 컬러 — 의미별로 구분 */
    .icon-amber  { background: linear-gradient(135deg, var(--c-amber-a32),  var(--c-amber-a12));  border-color: var(--c-amber-a45)  !important; }
    .icon-teal   { background: linear-gradient(135deg, var(--c-teal-a32),   var(--c-teal-a12));   border-color: var(--c-teal-a45)   !important; }
    .icon-indigo { background: linear-gradient(135deg, var(--c-indigo-a32), var(--c-indigo-a12)); border-color: var(--c-indigo-a45) !important; }
    .icon-violet { background: linear-gradient(135deg, var(--c-violet-a32), var(--c-violet-a12)); border-color: var(--c-violet-a45) !important; }
    .icon-cyan   { background: linear-gradient(135deg, var(--c-cyan-a32),   var(--c-cyan-a12));   border-color: var(--c-cyan-a45)   !important; }
    .icon-rose   { background: linear-gradient(135deg, var(--c-rose-a32),   var(--c-rose-a12));   border-color: var(--c-rose-a45)   !important; }
    .title-amber  { color: var(--c-amber)  !important; }
    .title-teal   { color: var(--c-teal)   !important; }
    .title-indigo { color: var(--c-indigo) !important; }
    .title-violet { color: var(--c-violet) !important; }
    .title-cyan   { color: var(--c-cyan)   !important; }
    .title-rose   { color: var(--c-rose)   !important; }
    .section-title { font-size: 0.9rem; font-weight: 700; color: ${text_sec}; }

    /* ── 감성 배지 ─────────────────────────────────────────────────── */
    .sentiment-badge {
        display: inline-flex; align-items: center; gap: 0.3rem;
        padding: 0.15rem 0.55rem;
        border-radius: 20px;
        font-size: 0.68rem;
        font-weight: 700;
    }
    .sent-pos { background: var(--c-green-a15); color: var(--c-green); border: 1px solid var(--c-green-a30); }
    .sent-neg { background: var(--c-red-a15);   color: var(--c-red);   border: 1px solid var(--c-red-a30);   }
    .sent-neu { background: var(--c-yellow-a15); color: #fbbf24;       border: 1px solid var(--c-yellow-a30); }
    .impact-badge {
        background: var(--c-blue-a15); color: var(--c-blue);
        border: 1px solid var(--c-blue-a30);
        padding: 0.15rem 0.55rem; border-radius: 20px;
        font-size: 0.68rem; font-weight: 700;
    }
    .status-row { display: flex; flex-direction: column; gap: 0.55rem; }
    .status-item {
        display: flex;
        align-items: center;
        gap: 0.7rem;
        background: ${status_bg};
        border: 1px solid ${status_bdr};
        border-radius: 10px;
        padding: 0.65rem 0.9rem;
    }
    .status-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
    .dot-green  { background: #34d399; box-shadow: 0 0 6px rgba(52,211,153,0.6); }
    .dot-yellow { background: #fbbf24; box-shadow: 0 0 6px rgba(251,191,36,0.6); }
    .dot-red    { background: #f87171; box-shadow: 0 0 6px rgba(248,113,113,0.6); }
    .dot-blue   { background: #60a5fa; box-shadow: 0 0 6px rgba(96,165,250,0.5); }
    .status-text { font-size: 0.82rem; color: ${text_status}; flex: 1; line-height: 1.4; }
    .status-text strong { color: ${text_primary}; }

    /* ── 뉴스 카드 ─────────────────────────────────────────────────── */
    .news-card {
        background: ${news_bg};
        border: 1px solid ${news_bdr};
        border-radius: 14px;
        padding: 1rem 1.1rem;
        margin-bottom: 0.8rem;
        backdrop-filter: blur(8px);
        transition: border-color 0.2s;
    }
    .news-card:hover { border-color: var(--c-violet-bdr); }
    .pos-card { border-left: 3px solid var(--c-green);  background: var(--c-green-a06); }
    .neg-card { border-left: 3px solid var(--c-red);    background: var(--c-red-a06);   }
    .neu-card { border-left: 3px solid #fbbf24;         background: var(--c-yellow-a06); }
    .news-meta { font-size: 0.7rem; color: ${text_muted}; margin-bottom: 0.4rem; display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
    .news-title { font-size: 0.9rem; font-weight: 600; color: ${text_primary}; line-height: 1.45; margin-bottom: 0.35rem; }
    .news-orig  { font-size: 0.72rem; color: ${text_dimmed}; margin-bottom: 0.5rem; font-style: italic; }
    .news-link  { font-size: 0.78rem; color: #818cf8; text-decoration: none; font-weight: 500; }
    .news-link:hover { color: #a78bfa; }

    /* ── 소셜 미디어 카드 ─────────────────────────────────────────── */
    .social-card {
        background: ${social_bg};
        border: 1px solid ${social_bdr};
        border-radius: 14px;
        padding: 0.95rem 1.1rem;
        margin-bottom: 0.7rem;
        backdrop-filter: blur(8px);
        transition: border-color 0.2s;
    }
    .social-card:hover { border-color: var(--c-cyan-a45); }
    .social-bull { border-left: 3px solid var(--c-green); background: var(--c-green-a05); }
    .social-bear { border-left: 3px solid var(--c-red);   background: var(--c-red-a05);   }
    .social-meta {
        display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;
        font-size: 0.7rem; color: ${text_muted}; margin-bottom: 0.4rem;
    }
    .social-body { font-size: 0.88rem; color: ${text_sec}; line-height: 1.5; margin-bottom: 0.4rem; }
    .social-stats { display: flex; gap: 0.9rem; font-size: 0.72rem; color: ${text_dimmed}; }
    .social-selftext {
        font-size: 0.82rem; color: ${social_selftext_clr};
        line-height: 1.55; margin: 0.3rem 0 0.4rem 0;
        border-left: 2px solid ${social_selftext_bdr};
        padding-left: 0.7rem;
    }
    .bull-badge {
        background: var(--c-green-a15); color: var(--c-green);
        border: 1px solid var(--c-green-a30);
        padding: 0.12rem 0.5rem; border-radius: 20px; font-size: 0.68rem; font-weight: 700;
    }
    .bear-badge {
        background: var(--c-red-a15); color: var(--c-red);
        border: 1px solid var(--c-red-a30);
        padding: 0.12rem 0.5rem; border-radius: 20px; font-size: 0.68rem; font-weight: 700;
    }
    .platform-badge {
        background: var(--c-cyan-a12); color: var(--c-cyan);
        border: 1px solid var(--c-cyan-a25);
        padding: 0.12rem 0.5rem; border-radius: 20px; font-size: 0.68rem; font-weight: 700;
    }
    .reddit-badge {
        background: var(--c-orange-a12); color: var(--c-orange);
        border: 1px solid var(--c-orange-a25);
        padding: 0.12rem 0.5rem; border-radius: 20px; font-size: 0.68rem; font-weight: 700;
    }
    .sentiment-bar-wrap {
        background: ${sent_wrap_bg}; border-radius: 10px;
        padding: 0.85rem 1rem; margin-bottom: 0.8rem;
        border: 1px solid ${sent_wrap_bdr};
    }
    .sentiment-bar-track {
        background: ${sent_track}; border-radius: 99px;
        height: 8px; overflow: hidden; margin: 0.4rem 0;
    }
    .sentiment-bar-fill {
        height: 100%; border-radius: 99px;
        background: linear-gradient(90deg, #34d399, #fbbf24);
        transition: width 0.6s ease;
    }

    /* ── 스캔 결과 테이블 ──────────────────────────────────────────── */
    .scan-header {
        background: linear-gradient(135deg, rgba(245,185,66,0.2), rgba(251,113,133,0.12));
        border: 1px solid rgba(245,185,66,0.35);
        border-radius: 14px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
        display: flex; align-items: center; justify-content: space-between;
    }
    .scan-title { font-size: 0.95rem; font-weight: 700; color: #f5b942; }

    /* ── 메모 영역 ─────────────────────────────────────────────────── */
    .stTextArea textarea {
        background: ${textarea_bg} !important;
        border: 1px solid rgba(139,92,246,0.3) !important;
        border-radius: 12px !important;
        color: ${text_primary} !important;
        font-size: 0.88rem !important;
        resize: vertical;
    }
    .stTextArea textarea:focus {
        border-color: rgba(139,92,246,0.6) !important;
        box-shadow: 0 0 0 2px rgba(139,92,246,0.15) !important;
    }

    /* ── 버튼 (Blobs 목업 스타일: 단색 필 형태 CTA) ───────────────────── */
    .stButton button {
        background: var(--c-accent) !important;
        border: 1px solid var(--c-accent) !important;
        border-radius: 999px !important;
        color: var(--c-accent-ink) !important;
        font-weight: 700 !important;
        font-size: 0.88rem !important;
        transition: all 0.2s !important;
        min-height: 2.5rem !important;
        box-shadow: 0 2px 10px rgba(245,169,115,0.25) !important;
    }
    .stButton button:hover {
        background: var(--c-accent-hov) !important;
        border-color: var(--c-accent-hov) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 16px rgba(245,169,115,0.4) !important;
    }

    /* ── 탭 (Blobs 목업 스타일: 필터 칩) ──────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {
        background: ${tab_bg} !important;
        border-radius: 999px !important;
        padding: 0.3rem !important;
        gap: 0.3rem !important;
        border: 1px solid ${tab_bdr} !important;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 999px !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        color: ${text_muted} !important;
        padding: 0.55rem 1.1rem !important;
    }
    .stTabs [aria-selected="true"] {
        background: var(--c-accent) !important;
        color: var(--c-accent-ink) !important;
        border: 1px solid var(--c-accent) !important;
        font-weight: 700 !important;
    }

    /* ── 세그먼트 컨트롤 (뉴스/소셜/기술분석 전환 — 탭과 동일한 필터 칩 스타일) ── */
    [data-testid="stSegmentedControl"] {
        background: ${tab_bg} !important;
        border-radius: 999px !important;
        padding: 0.3rem !important;
        gap: 0.3rem !important;
        border: 1px solid ${tab_bdr} !important;
    }
    [data-testid="stSegmentedControl"] label,
    [data-testid="stSegmentedControl"] button,
    [data-testid="stSegmentedControl"] div[role="radiogroup"] label,
    [data-testid="stSegmentedControl"] div[data-baseweb="button-group"] > * {
        border-radius: 999px !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        color: ${text_sec} !important;
        background: transparent !important;
        background-color: transparent !important;
        opacity: 1 !important;
    }
    [data-testid="stSegmentedControl"] label *,
    [data-testid="stSegmentedControl"] button *,
    [data-testid="stSegmentedControl"] label p,
    [data-testid="stSegmentedControl"] button p,
    [data-testid="stSegmentedControl"] [data-testid="stMarkdownContainer"],
    [data-testid="stSegmentedControl"] [data-testid="stMarkdownContainer"] * {
        color: ${text_sec} !important;
        fill: ${text_sec} !important;
        opacity: 1 !important;
    }
    [data-testid="stSegmentedControl"] [aria-checked="true"],
    [data-testid="stSegmentedControl"] [aria-selected="true"] {
        background: var(--c-accent) !important;
        background-color: var(--c-accent) !important;
        color: var(--c-accent-ink) !important;
        border: 1px solid var(--c-accent) !important;
        font-weight: 700 !important;
    }
    [data-testid="stSegmentedControl"] [aria-checked="true"] *,
    [data-testid="stSegmentedControl"] [aria-selected="true"] *,
    [data-testid="stSegmentedControl"] [aria-checked="true"] p,
    [data-testid="stSegmentedControl"] [aria-selected="true"] p {
        color: var(--c-accent-ink) !important;
        fill: var(--c-accent-ink) !important;
    }

    /* ── 즐겨찾기 리스트: 티커 칩 (은은한 카드, 좌측 정렬) ───────────── */
    [class*="st-key-fav_ticker_"] button {
        background: ${glass_bg} !important;
        border: 1px solid ${glass_border} !important;
        color: ${text_primary} !important;
        font-weight: 700 !important;
        font-size: 0.85rem !important;
        border-radius: 10px !important;
        box-shadow: none !important;
        justify-content: flex-start !important;
        padding-left: 0.9rem !important;
        min-height: 2.3rem !important;
        transition: all 0.15s !important;
    }
    [class*="st-key-fav_ticker_"] button:hover {
        border-color: var(--c-accent) !important;
        color: var(--c-accent) !important;
        background: ${glass_bg} !important;
        transform: none !important;
        box-shadow: none !important;
    }

    /* ── 즐겨찾기 액션 아이콘(▲▼✕): 고스트 스타일로 시각적 무게 축소 ── */
    [class*="st-key-fav_action_"] button {
        background: transparent !important;
        border: 1px solid ${glass_border} !important;
        color: ${text_muted} !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
        min-height: 2.3rem !important;
        box-shadow: none !important;
        padding: 0 !important;
    }
    [class*="st-key-fav_action_"] button:hover:not(:disabled) {
        border-color: var(--c-accent) !important;
        color: var(--c-accent) !important;
        background: ${glass_bg} !important;
        transform: none !important;
        box-shadow: none !important;
    }
    [class*="st-key-fav_action_"] button:disabled {
        opacity: 0.3 !important;
    }

    /* ── 폼 제출 버튼 (사이드바 '실시간 정밀 검증 시작' 등, .stButton과 별도 클래스) ── */
    .stFormSubmitButton button,
    [data-testid="stFormSubmitButton"] button {
        background: var(--c-accent) !important;
        border: 1px solid var(--c-accent) !important;
        border-radius: 999px !important;
        color: var(--c-accent-ink) !important;
        font-weight: 700 !important;
        font-size: 0.88rem !important;
        transition: all 0.2s !important;
        min-height: 2.5rem !important;
        box-shadow: 0 2px 10px rgba(245,169,115,0.25) !important;
    }
    .stFormSubmitButton button *,
    [data-testid="stFormSubmitButton"] button * {
        color: var(--c-accent-ink) !important;
    }
    .stFormSubmitButton button:hover,
    [data-testid="stFormSubmitButton"] button:hover {
        background: var(--c-accent-hov) !important;
        border-color: var(--c-accent-hov) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 16px rgba(245,169,115,0.4) !important;
    }

    /* ── 섹터 히트맵 ───────────────────────────────────────────────── */
    .sector-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
        gap: 0.6rem;
        margin-bottom: 1rem;
    }
    .sector-cell {
        border-radius: 12px;
        padding: 0.85rem 0.9rem;
        text-align: center;
        backdrop-filter: blur(8px);
        border: 1px solid rgba(255,255,255,0.1);
        transition: transform 0.15s;
        cursor: default;
    }
    .sector-cell:hover { transform: translateY(-2px); }
    .sector-name { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.6px; text-transform: uppercase; color: ${sector_name_clr}; margin-bottom: 0.3rem; }
    .sector-ticker { font-size: 0.62rem; color: ${sector_ticker_clr}; margin-bottom: 0.4rem; }
    .sector-pct { font-size: 1.25rem; font-weight: 800; line-height: 1; }
    .sector-sub { font-size: 0.68rem; margin-top: 0.25rem; opacity: 0.7; }
    .sector-legend { display: flex; gap: 1.2rem; align-items: center; flex-wrap: wrap; margin-bottom: 0.9rem; }
    .legend-item { display: flex; align-items: center; gap: 0.35rem; font-size: 0.72rem; color: ${text_muted}; }
    .legend-dot { width: 10px; height: 10px; border-radius: 3px; }

    /* ── 구분선 ────────────────────────────────────────────────────── */
    hr { border-color: ${hr_color} !important; margin: 1rem 0 !important; }

    /* ── 모바일 ────────────────────────────────────────────────────── */
    @media (max-width: 640px) {
        .block-container { padding: 0.8rem 0.9rem 2rem !important; }
        .app-header { padding: 1rem 1.1rem; border-radius: 14px; }
        .app-header h1 { font-size: 1rem; }
        .app-header p { font-size: 0.68rem; }
        .metric-value { font-size: 1.25rem; }
        [data-testid="stMetricValue"] { font-size: 1.05rem !important; }
        [data-testid="stMetricLabel"] { font-size: 0.65rem !important; }
        [data-testid="stMetricDelta"] { font-size: 0.65rem !important; }
        .stButton button { min-height: 2.8rem !important; font-size: 0.95rem !important; }
    }

    /* ── 라이트 모드: 저대비 텍스트 색상 전면 보정 ──────────────────── *
     * (버그 수정: 기존 코드는 이 블록이 바깥 f-string 안에 중첩된      *
     * "일반 문자열"인데도 중괄호를 { } 로 이중 이스케이프해서       *
     * 실제로는 깨진 CSS( { ... } )가 출력되어 라이트 모드 보정이    *
     * 하나도 적용되지 않고 있었음. 홑 중괄호로 수정 + 저대비 색상     *
     * 전반(회색 노트, 파스텔 강조색 등)에 대한 보정을 추가함.         */
    $light_mode_overrides
</style>
