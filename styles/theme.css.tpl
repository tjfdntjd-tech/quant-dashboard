<style>
    /* ── 폰트 임포트 ──────────────────────────────────────────────── *
     * 디스플레이 & 본문: Manrope (모던/미니멀)                         *
     * 데이터: JetBrains Mono (가격/티커/지표 — 자릿수 정렬되는 단말기 느낌) */
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&family=Black+Han+Sans&display=swap');

    :root {
        --font-display: 'Black Han Sans', 'Manrope', 'Apple SD Gothic Neo', 'Malgun Gothic', 'Segoe UI', sans-serif;
        --font-body:    'Manrope', 'Apple SD Gothic Neo', 'Malgun Gothic', system-ui, sans-serif;
        --font-mono:    'JetBrains Mono', 'Consolas', monospace;

        /* ── 섹션별 시그니처 컬러 (순수 색상) ─────────────────────── */
        --c-amber:  #e0943a;
        --c-teal:   #21b39d;
        --c-indigo: #5a5bd6;
        --c-violet: #9c7ff2;
        --c-cyan:   #2ec2e8;
        --c-rose:   #f2617e;
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
        --c-amber-a65:  rgba(224,148,58,0.65);
        --c-amber-a32:  rgba(224,148,58,0.32);
        --c-amber-a12:  rgba(224,148,58,0.12);
        --c-amber-a45:  rgba(224,148,58,0.45);
        --c-amber-a30:  rgba(224,148,58,0.3);
        --c-amber-a18:  rgba(224,148,58,0.18);

        --c-teal-a65:   rgba(33,179,157,0.65);
        --c-teal-a32:   rgba(33,179,157,0.32);
        --c-teal-a12:   rgba(33,179,157,0.12);
        --c-teal-a45:   rgba(33,179,157,0.45);

        --c-indigo-a65: rgba(90,91,214,0.65);
        --c-indigo-a32: rgba(90,91,214,0.32);
        --c-indigo-a12: rgba(90,91,214,0.12);
        --c-indigo-a45: rgba(90,91,214,0.45);
        --c-indigo-a20: rgba(90,91,214,0.2);
        --c-indigo-a15: rgba(90,91,214,0.15);
        --c-indigo-a35: rgba(90,91,214,0.35);

        --c-violet-a65: rgba(156,127,242,0.65);
        --c-violet-a32: rgba(156,127,242,0.32);
        --c-violet-a12: rgba(156,127,242,0.12);
        --c-violet-a45: rgba(156,127,242,0.45);

        --c-cyan-a65:   rgba(46,194,232,0.65);
        --c-cyan-a32:   rgba(46,194,232,0.32);
        --c-cyan-a12:   rgba(46,194,232,0.12);
        --c-cyan-a45:   rgba(46,194,232,0.45);
        --c-cyan-a25:   rgba(46,194,232,0.25);

        --c-rose-a65:   rgba(242,97,126,0.65);
        --c-rose-a32:   rgba(242,97,126,0.32);
        --c-rose-a12:   rgba(242,97,126,0.12);
        --c-rose-a45:   rgba(242,97,126,0.45);
        --c-rose-a16:   rgba(242,97,126,0.16);

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

        /* ── #디자인개선(위젯 스타일 전면 교체): iOS/Apple Watch 잠금화면
           위젯 참고 이미지 톤앤매너 — 벨벳처럼 진한 순검정 카드, 글래스/블러
           없이 완전 불투명, 매우 큰 라운드 코너, 카드 안의 데이터는 채도
           높은 플랫(단색) 네온 블록으로 강조. 아래는 그 시스템의 공통 토큰. */
        --radius-card:   28px;
        --radius-card-sm:20px;
        --radius-pill:   999px;
        --card-solid:    #0c0c0e;
        --card-solid-2:  #131316;
        --card-line:     rgba(255,255,255,0.08);
        --neon-green:  #baff29;
        --neon-green-ink: #12210a;
        --neon-yellow: #eaff3d;
        --neon-yellow-ink: #23230a;
        --neon-red:    #ff2d55;
        --neon-red-ink: #ffffff;
        --neon-cyan:   #35e0ff;
        --neon-cyan-ink: #072226;
        --neon-orange: #ff9a2e;
        --neon-orange-ink: #241300;

        /* ── 카드 전용 고정 텍스트 컬러 (라이트/다크 토글과 무관) ──────
           #버그수정: metric-card/glass-card/news-card/social-card 등은
           --card-solid(#0c0c0e)로 배경이 항상 순검정 고정인데, 기존엔
           그 안의 텍스트(${text_primary} 등)만 라이트 모드 값(짙은 남색)으로
           바뀌어 "어두운 배경 + 어두운 글씨"가 되는 저대비 버그가 있었음.
           → 카드 배경이 절대 안 바뀌므로 카드 안 텍스트도 항상 이 고정
           밝은 색을 쓰도록 분리. (라이트 모드 전용 보정은 LIGHT_MODE_OVERRIDE_CSS
           쪽에서 페이지 배경 위 텍스트에만 계속 적용됨) */
        --card-ink-primary:   #f1f5f9;
        --card-ink-secondary: #e2e8f0;
        --card-ink-label:     #8fc4e8;
        --card-ink-muted:     #8fc4e8;
        --card-ink-dimmed:    #e0b374;
        --card-ink-status:    #cbd5e1;
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
    /* #디자인개선 시그니처 요소: 앱 전체에서 유일하게 쓰이는 브랜드 강조색
       (--c-accent, 코랄)을 헤더 상단 얇은 바로 다시 보여줘 "이 앱의 색"이라는
       인상을 첫 화면에서부터 각인시킴. 나머지 장식은 절제. */
    .app-header {
        position: relative;
        background: var(--card-solid);
        border: none;
        border-radius: var(--radius-card);
        padding: 1.4rem 1.8rem;
        margin-bottom: 1.4rem;
        box-shadow: 0 14px 30px rgba(0,0,0,0.45);
        overflow: hidden;
    }
    .app-header::before {
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 4px;
        background: var(--neon-green);
    }
    .app-header h1 {
        margin: 0 0 0.2rem 0;
        font-size: 1.3rem;
        font-weight: 800;
        color: #ffffff;
        letter-spacing: 0;
    }
    .app-header p {
        margin: 0;
        color: var(--card-ink-muted);
        font-size: 0.72rem;
        font-family: var(--font-mono);
        letter-spacing: 0.3px;
    }

    /* ── 글래스 카드 공통 ──────────────────────────────────────────── */
    /* #디자인개선(리퀴드 글래스): iOS 26 스타일 참고 이미지처럼 카드 상단에
       얇은 하이라이트 실선(빛이 유리 위쪽 모서리에 맺히는 느낌)을 추가하고,
       그림자를 outer(띄움) + inset(안쪽 미세 광택) 레이어로 나눠 단순한
       blur보다 훨씬 입체적인 "볼록한 유리판" 인상을 준다. */
    .glass-card {
        position: relative;
        background: var(--card-solid);
        border: 1px solid var(--card-line);
        border-radius: var(--radius-card);
        padding: 1.15rem 1.25rem;
        margin-bottom: 1rem;
        box-shadow: 0 12px 28px rgba(0,0,0,0.4);
        transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
        overflow: hidden;
    }
    .glass-card:hover {
        border-color: rgba(255,255,255,0.16);
        transform: translateY(-1px);
        box-shadow: 0 16px 34px rgba(0,0,0,0.46);
    }
    .glass-card-title {
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 1.2px;
        text-transform: uppercase;
        color: var(--card-ink-muted);
        margin-bottom: 0.6rem;
    }

    /* ── 메트릭 카드 ──────────────────────────────────────────────── */
    /* #디자인개선: 기존엔 카드마다 좌측 3px 컬러 바 하나로만 구분됐고,
       배경/그림자는 모든 카드가 완전히 동일해 평면적으로 보였음.
       → 카테고리 색을 아주 옅은 배경 그라디언트로도 은은하게 스며들게 하고,
       호버 시 그림자+테두리가 함께 반응하도록 해 입체감과 고급스러움을 더함. */
    .metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-bottom: 1rem; }
    .metric-card {
        position: relative;
        background: var(--card-solid);
        border: 1px solid var(--card-line);
        border-radius: var(--radius-card-sm);
        padding: 1rem 1.1rem;
        box-shadow: 0 8px 20px rgba(0,0,0,0.35);
        transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
        overflow: hidden;
    }
    .metric-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 12px 26px rgba(0,0,0,0.42);
    }
    .metric-card { border-left: 4px solid transparent; }
    .mc-amber  { border-left-color: var(--c-amber)  !important; }
    .mc-violet { border-left-color: var(--c-violet) !important; }
    .mc-rose   { border-left-color: var(--c-rose)   !important; }
    .mc-cyan   { border-left-color: var(--c-cyan)   !important; }
    .mc-indigo { border-left-color: var(--c-indigo) !important; }
    .mc-teal   { border-left-color: var(--c-teal)   !important; }
    .mc-amber:hover  { border-color: var(--c-amber)  !important; }
    .mc-violet:hover { border-color: var(--c-violet) !important; }
    .mc-rose:hover   { border-color: var(--c-rose)   !important; }
    .mc-cyan:hover   { border-color: var(--c-cyan)   !important; }
    .mc-indigo:hover { border-color: var(--c-indigo) !important; }
    .mc-teal:hover   { border-color: var(--c-teal)   !important; }
    .metric-label { font-size: 0.7rem; color: var(--card-ink-label); font-weight: 600; letter-spacing: 0.8px; text-transform: uppercase; margin-bottom: 0.35rem; }
    .metric-value { font-size: 1.6rem; font-weight: 800; color: var(--card-ink-primary); line-height: 1; font-family: var(--font-mono); }
    .metric-delta { font-size: 0.78rem; font-weight: 700; margin-top: 0.3rem; }
    .delta-up   { color: var(--neon-green); }
    .delta-down { color: var(--neon-red); }
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
    /* #디자인개선(컬러 그라디언트 카드): 참고 이미지(운동 앱 알림 카드 —
       원색 그라디언트 배경 + 좌측 라운드 사각 아이콘 배지 + 흰색 굵은 제목
       + 옅은 흰색 부제 + 투명 흰 필 태그) 톤앤매너를 3종 배너에 그대로
       이식. 배경 자체가 항상 채도 높은 색이라 라이트/다크 모드와 무관하게
       흰색 텍스트가 always-on-brand 대비를 보장한다. */
    .alert-banner {
        position: relative;
        background: var(--neon-red);
        border: none;
        border-radius: var(--radius-card);
        padding: 1.05rem 1.25rem;
        margin-bottom: 1rem;
        display: flex;
        align-items: flex-start;
        gap: 0.85rem;
        box-shadow: 0 12px 26px rgba(255,45,85,0.28);
        overflow: hidden;
    }
    .alert-icon {
        width: 40px; height: 40px; border-radius: 14px;
        background: rgba(0,0,0,0.18);
        border: none;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.15rem; line-height: 1;
        flex-shrink: 0;
    }
    .alert-title {
        font-size: 0.95rem; font-weight: 800; letter-spacing: 0;
        text-transform: none; color: #fff !important;
        font-family: var(--font-display);
        margin-bottom: 0.35rem;
    }
    .alert-signals { display: flex; flex-wrap: wrap; gap: 0.4rem; }
    .signal-chip {
        background: rgba(0,0,0,0.22);
        border: none;
        border-radius: var(--radius-pill);
        padding: 0.22rem 0.75rem;
        font-size: 0.75rem;
        font-weight: 800;
        color: #fff !important;
    }
    .china-banner {
        background: var(--neon-orange);
        border: none;
        border-radius: var(--radius-card);
        padding: 0.9rem 1.2rem;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 0.8rem;
        box-shadow: 0 12px 26px rgba(255,154,46,0.25);
    }
    .china-banner-icon {
        width: 38px; height: 38px; border-radius: 12px;
        background: rgba(0,0,0,0.18);
        border: none;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.05rem; line-height: 1;
        flex-shrink: 0;
    }
    .china-banner-text { font-size: 0.87rem; font-weight: 800; color: var(--neon-orange-ink) !important; letter-spacing: 0.1px; font-family: var(--font-display); }
    .china-banner-sub { font-size: 0.73rem; font-weight: 600; color: var(--neon-orange-ink) !important; opacity: 0.8; margin-top: 0.15rem; }
    .split-banner {
        background: var(--neon-green);
        border: none;
        border-radius: var(--radius-card);
        padding: 0.95rem 1.2rem;
        margin-bottom: 0.8rem;
        box-shadow: 0 12px 26px rgba(186,255,41,0.22);
    }
    .split-banner-title { font-size: 0.9rem; font-weight: 800; letter-spacing: 0; color: var(--neon-green-ink) !important; margin-bottom: 0.35rem; font-family: var(--font-display); }
    .split-banner-body  { font-size: 0.8rem; color: var(--neon-green-ink) !important; opacity: 0.85; line-height: 1.55; }
    .split-banner-body strong { color: var(--neon-green-ink) !important; opacity: 1; }
    .split-banner .news-link { color: var(--neon-green-ink) !important; text-decoration: underline; font-weight: 700; }
    .split-banner .news-link:hover { opacity: 0.7; }

    /* ── 섹션 헤더 ─────────────────────────────────────────────────── */
    .section-header {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin: 1.3rem 0 0.7rem 0;
    }
    .section-icon {
        position: relative;
        width: 32px; height: 32px;
        background: rgba(255,255,255,0.08);
        border: none;
        border-radius: 11px;
        display: flex; align-items: center; justify-content: center;
        font-size: 0.9rem;
        flex-shrink: 0;
        overflow: hidden;
    }
    /* 섹션별 시그니처 컬러 — 의미별로 구분 (플랫 단색 배경) */
    .icon-amber  { background: var(--c-amber)  !important; }
    .icon-teal   { background: var(--c-teal)   !important; }
    .icon-indigo { background: var(--c-indigo) !important; }
    .icon-violet { background: var(--c-violet) !important; }
    .icon-cyan   { background: var(--c-cyan)   !important; }
    .icon-rose   { background: var(--c-rose)   !important; }
    /* ── 아이콘 배지 (mono_icon_badge 출력용) — 플랫 단색 원형, 글로시 효과 제거 ── */
    .liquid-icon {
        position: relative;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        overflow: hidden;
        border: none;
        box-shadow: 0 4px 10px rgba(0,0,0,0.3);
    }
    .liquid-icon svg { position: relative; z-index: 1; }
    /* 테두리형(outline) 배지 — 플랫 카드 위에 라인 아이콘 */
    .liquid-icon-outline {
        background: rgba(255,255,255,0.06);
        border: 1.5px solid rgba(255,255,255,0.14);
        box-shadow: none;
    }


    .title-amber  { color: var(--c-amber)  !important; }
    .title-teal   { color: var(--c-teal)   !important; }
    .title-indigo { color: var(--c-indigo) !important; }
    .title-violet { color: var(--c-violet) !important; }
    .title-cyan   { color: var(--c-cyan)   !important; }
    .title-rose   { color: var(--c-rose)   !important; }
    .section-title { font-size: 0.98rem; font-weight: 800; letter-spacing: 0.1px; color: ${text_sec}; }

    /* ── 감성 배지 (플랫 단색 필) ─────────────────────────────────── */
    .sentiment-badge {
        display: inline-flex; align-items: center; gap: 0.3rem;
        padding: 0.18rem 0.6rem;
        border-radius: var(--radius-pill);
        font-size: 0.68rem;
        font-weight: 800;
    }
    .sent-pos { background: var(--neon-green);  color: var(--neon-green-ink);  border: none; }
    .sent-neg { background: var(--neon-red);    color: #fff;                  border: none; }
    .sent-neu { background: var(--neon-yellow); color: var(--neon-yellow-ink); border: none; }
    .impact-badge {
        background: var(--neon-cyan); color: var(--neon-cyan-ink);
        border: none;
        padding: 0.18rem 0.6rem; border-radius: var(--radius-pill);
        font-size: 0.68rem; font-weight: 800;
    }
    .status-row { display: flex; flex-direction: column; gap: 0.55rem; }
    .status-item {
        display: flex;
        align-items: center;
        gap: 0.7rem;
        background: var(--card-solid-2);
        border: 1px solid var(--card-line);
        border-radius: 14px;
        padding: 0.65rem 0.9rem;
    }
    .status-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
    .dot-green  { background: var(--neon-green);  box-shadow: 0 0 6px rgba(186,255,41,0.6); }
    .dot-yellow { background: var(--neon-yellow); box-shadow: 0 0 6px rgba(234,255,61,0.6); }
    .dot-red    { background: var(--neon-red);    box-shadow: 0 0 6px rgba(255,45,85,0.6); }
    .dot-blue   { background: var(--neon-cyan);   box-shadow: 0 0 6px rgba(53,224,255,0.5); }
    .status-text { font-size: 0.82rem; color: var(--card-ink-status); flex: 1; line-height: 1.4; }
    .status-text strong { color: var(--card-ink-primary); }

    /* ── 뉴스 카드 ─────────────────────────────────────────────────── */
    .news-card {
        background: var(--card-solid);
        border: 1px solid var(--card-line);
        border-radius: var(--radius-card-sm);
        padding: 1rem 1.1rem;
        margin-bottom: 0.8rem;
        transition: border-color 0.2s;
    }
    .news-card:hover { border-color: rgba(255,255,255,0.18); }
    .pos-card { border-left: 4px solid var(--neon-green); }
    .neg-card { border-left: 4px solid var(--neon-red);   }
    .neu-card { border-left: 4px solid var(--neon-yellow); }
    .news-meta { font-size: 0.7rem; color: var(--card-ink-muted); margin-bottom: 0.4rem; display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
    .news-title { font-size: 0.9rem; font-weight: 600; color: var(--card-ink-primary); line-height: 1.45; margin-bottom: 0.35rem; }
    .news-orig  { font-size: 0.72rem; color: var(--card-ink-dimmed); margin-bottom: 0.5rem; font-style: italic; }
    .news-link  { font-size: 0.78rem; color: var(--neon-cyan); text-decoration: none; font-weight: 700; }
    .news-link:hover { opacity: 0.75; }

    /* ── 소셜 미디어 카드 ─────────────────────────────────────────── */
    .social-card {
        background: var(--card-solid);
        border: 1px solid var(--card-line);
        border-radius: var(--radius-card-sm);
        padding: 0.95rem 1.1rem;
        margin-bottom: 0.7rem;
        transition: border-color 0.2s;
    }
    .social-card:hover { border-color: rgba(53,224,255,0.4); }
    .social-bull { border-left: 4px solid var(--neon-green); }
    .social-bear { border-left: 4px solid var(--neon-red);   }
    .social-meta {
        display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;
        font-size: 0.7rem; color: var(--card-ink-muted); margin-bottom: 0.4rem;
    }
    .social-body { font-size: 0.88rem; color: var(--card-ink-secondary); line-height: 1.5; margin-bottom: 0.4rem; }
    .social-stats { display: flex; gap: 0.9rem; font-size: 0.72rem; color: var(--card-ink-dimmed); }
    .social-selftext {
        font-size: 0.82rem; color: var(--card-ink-dimmed);
        line-height: 1.55; margin: 0.3rem 0 0.4rem 0;
        border-left: 2px solid ${social_selftext_bdr};
        padding-left: 0.7rem;
    }
    .bull-badge {
        background: var(--neon-green); color: var(--neon-green-ink);
        border: none;
        padding: 0.14rem 0.55rem; border-radius: var(--radius-pill); font-size: 0.68rem; font-weight: 800;
    }
    .bear-badge {
        background: var(--neon-red); color: #fff;
        border: none;
        padding: 0.14rem 0.55rem; border-radius: var(--radius-pill); font-size: 0.68rem; font-weight: 800;
    }
    .platform-badge {
        background: var(--neon-cyan); color: var(--neon-cyan-ink);
        border: none;
        padding: 0.14rem 0.55rem; border-radius: var(--radius-pill); font-size: 0.68rem; font-weight: 800;
    }
    .reddit-badge {
        background: var(--neon-orange); color: var(--neon-orange-ink);
        border: none;
        padding: 0.14rem 0.55rem; border-radius: var(--radius-pill); font-size: 0.68rem; font-weight: 800;
    }
    .sentiment-bar-wrap {
        background: var(--card-solid-2); border-radius: 18px;
        padding: 0.85rem 1rem; margin-bottom: 0.8rem;
        border: 1px solid var(--card-line);
    }
    .sentiment-bar-track {
        background: rgba(255,255,255,0.08); border-radius: var(--radius-pill);
        height: 10px; overflow: hidden; margin: 0.4rem 0;
    }
    .sentiment-bar-fill {
        height: 100%; border-radius: var(--radius-pill);
        background: var(--neon-green);
        transition: width 0.6s ease;
    }

    /* ── 스캔 결과 테이블 ──────────────────────────────────────────── */
    .scan-header {
        background: var(--card-solid);
        border: 1px solid var(--card-line);
        border-left: 4px solid var(--c-amber);
        border-radius: var(--radius-card-sm);
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
        display: flex; align-items: center; justify-content: space-between;
    }
    .scan-title { font-size: 0.95rem; font-weight: 700; color: #e0943a; }

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

    /* ── 버튼 (리퀴드 글래스 필 형태 CTA) ─────────────────────────────── *
     * 참고 이미지의 유리 토글/버튼처럼 상단에 옅은 하이라이트 그라디언트를
     * 겹쳐 "볼록한 알약" 느낌을 내고, 안쪽 위/아래 inset으로 두께감 추가. */
    .stButton button {
        background: var(--neon-green) !important;
        border: none !important;
        border-radius: var(--radius-pill) !important;
        color: var(--neon-green-ink) !important;
        font-weight: 800 !important;
        font-size: 0.88rem !important;
        transition: all 0.2s !important;
        min-height: 2.5rem !important;
        box-shadow: 0 4px 14px rgba(186,255,41,0.25) !important;
    }
    .stButton button:hover {
        filter: brightness(1.08);
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 18px rgba(186,255,41,0.35) !important;
    }

    /* ── 탭 (Blobs 목업 스타일: 필터 칩) ──────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {
        background: var(--card-solid-2) !important;
        border-radius: var(--radius-pill) !important;
        padding: 0.3rem !important;
        gap: 0.3rem !important;
        border: 1px solid var(--card-line) !important;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: var(--radius-pill) !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        color: var(--card-ink-muted) !important;
        padding: 0.55rem 1.1rem !important;
    }
    .stTabs [aria-selected="true"] {
        background: var(--neon-green) !important;
        color: var(--neon-green-ink) !important;
        border: none !important;
        font-weight: 800 !important;
    }

    /* ── 세그먼트 컨트롤 (뉴스/소셜/기술분석 전환 — 항상 연한 분홍, 선택 시 진한 분홍) ── */
    [data-testid="stSegmentedControl"] {
        background: ${tab_bg} !important;
        border-radius: 999px !important;
        padding: 0.3rem !important;
        gap: 0.3rem !important;
        border: 1px solid ${tab_bdr} !important;
    }
    /* 미선택 세그먼트 버튼 (실제 Streamlit DOM: stBaseButton-segmented_control) */
    [data-testid="stSegmentedControl"] [data-testid="stBaseButton-segmented_control"] {
        border-radius: 999px !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        color: var(--c-rose) !important;
        background: var(--c-rose-a16) !important;
        background-color: var(--c-rose-a16) !important;
        border: 1px solid var(--c-rose-a32) !important;
        opacity: 1 !important;
    }
    [data-testid="stSegmentedControl"] [data-testid="stBaseButton-segmented_control"] *,
    [data-testid="stSegmentedControl"] [data-testid="stBaseButton-segmented_control"] p,
    [data-testid="stSegmentedControl"] [data-testid="stBaseButton-segmented_control"] [data-testid="stMarkdownContainer"],
    [data-testid="stSegmentedControl"] [data-testid="stBaseButton-segmented_control"] [data-testid="stMarkdownContainer"] * {
        color: var(--c-rose) !important;
        fill: var(--c-rose) !important;
        opacity: 1 !important;
    }
    [data-testid="stSegmentedControl"] [data-testid="stBaseButton-segmented_control"]:hover {
        background: var(--c-rose-a32) !important;
        background-color: var(--c-rose-a32) !important;
        border: 1px solid var(--c-rose) !important;
    }
    /* 선택된 세그먼트 버튼 (실제 Streamlit DOM: stBaseButton-segmented_controlActive) */
    [data-testid="stSegmentedControl"] [data-testid="stBaseButton-segmented_controlActive"] {
        border-radius: 999px !important;
        font-weight: 700 !important;
        font-size: 0.88rem !important;
        background: var(--c-rose) !important;
        background-color: var(--c-rose) !important;
        color: #fff !important;
        border: 1px solid var(--c-rose) !important;
    }
    [data-testid="stSegmentedControl"] [data-testid="stBaseButton-segmented_controlActive"] *,
    [data-testid="stSegmentedControl"] [data-testid="stBaseButton-segmented_controlActive"] p,
    [data-testid="stSegmentedControl"] [data-testid="stBaseButton-segmented_controlActive"] [data-testid="stMarkdownContainer"],
    [data-testid="stSegmentedControl"] [data-testid="stBaseButton-segmented_controlActive"] [data-testid="stMarkdownContainer"] * {
        color: #fff !important;
        fill: #fff !important;
    }
    /* 구버전 Streamlit 호환용 폴백 선택자 (label/button/aria-checked 기반) */
    [data-testid="stSegmentedControl"] label,
    [data-testid="stSegmentedControl"] button,
    [data-testid="stSegmentedControl"] div[role="radiogroup"] label,
    [data-testid="stSegmentedControl"] div[data-baseweb="button-group"] > * {
        border-radius: 999px !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        color: var(--c-rose) !important;
        background: var(--c-rose-a16) !important;
        background-color: var(--c-rose-a16) !important;
        border: 1px solid var(--c-rose-a32) !important;
        opacity: 1 !important;
    }
    [data-testid="stSegmentedControl"] label *,
    [data-testid="stSegmentedControl"] button *,
    [data-testid="stSegmentedControl"] label p,
    [data-testid="stSegmentedControl"] button p,
    [data-testid="stSegmentedControl"] [data-testid="stMarkdownContainer"],
    [data-testid="stSegmentedControl"] [data-testid="stMarkdownContainer"] * {
        color: var(--c-rose) !important;
        fill: var(--c-rose) !important;
        opacity: 1 !important;
    }
    [data-testid="stSegmentedControl"] [aria-checked="true"],
    [data-testid="stSegmentedControl"] [aria-selected="true"] {
        background: var(--c-rose) !important;
        background-color: var(--c-rose) !important;
        color: #fff !important;
        border: 1px solid var(--c-rose) !important;
        font-weight: 700 !important;
    }
    [data-testid="stSegmentedControl"] [aria-checked="true"] *,
    [data-testid="stSegmentedControl"] [aria-selected="true"] *,
    [data-testid="stSegmentedControl"] [aria-checked="true"] p,
    [data-testid="stSegmentedControl"] [aria-selected="true"] p {
        color: #fff !important;
        fill: #fff !important;
    }

    /* ── 즐겨찾기 리스트: 티커 칩 (은은한 카드, 좌측 정렬) ───────────── */
    [class*="st-key-fav_ticker_"] button {
        background: var(--card-solid-2) !important;
        border: 1px solid var(--card-line) !important;
        color: var(--card-ink-primary) !important;
        font-weight: 700 !important;
        font-size: 0.85rem !important;
        border-radius: 16px !important;
        box-shadow: none !important;
        justify-content: flex-start !important;
        padding-left: 0.9rem !important;
        min-height: 2.3rem !important;
        transition: all 0.15s !important;
    }
    [class*="st-key-fav_ticker_"] button:hover {
        border-color: var(--neon-green) !important;
        color: var(--neon-green) !important;
        background: var(--card-solid-2) !important;
        transform: none !important;
        box-shadow: none !important;
    }

    /* ── 즐겨찾기 액션 아이콘(▲▼✕): 고스트 스타일로 시각적 무게 축소 ── */
    [class*="st-key-fav_action_"] button {
        background: transparent !important;
        border: 1px solid var(--card-line) !important;
        color: var(--card-ink-muted) !important;
        font-weight: 600 !important;
        border-radius: 12px !important;
        min-height: 2.3rem !important;
        box-shadow: none !important;
        padding: 0 !important;
    }
    [class*="st-key-fav_action_"] button:hover:not(:disabled) {
        border-color: var(--neon-green) !important;
        color: var(--neon-green) !important;
        background: var(--card-solid-2) !important;
        transform: none !important;
        box-shadow: none !important;
    }
    [class*="st-key-fav_action_"] button:disabled {
        opacity: 0.3 !important;
    }

    /* ── 폼 제출 버튼 (사이드바 '실시간 정밀 검증 시작' 등, .stButton과 별도 클래스) ── */
    .stFormSubmitButton button,
    [data-testid="stFormSubmitButton"] button {
        background: var(--neon-green) !important;
        border: none !important;
        border-radius: var(--radius-pill) !important;
        color: var(--neon-green-ink) !important;
        font-weight: 800 !important;
        font-size: 0.88rem !important;
        transition: all 0.2s !important;
        min-height: 2.5rem !important;
        box-shadow: 0 4px 14px rgba(186,255,41,0.25) !important;
    }
    .stFormSubmitButton button *,
    [data-testid="stFormSubmitButton"] button * {
        color: var(--neon-green-ink) !important;
    }
    .stFormSubmitButton button:hover,
    [data-testid="stFormSubmitButton"] button:hover {
        filter: brightness(1.08);
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 18px rgba(186,255,41,0.35) !important;
    }

    /* ── 섹터 히트맵 ───────────────────────────────────────────────── */
    .sector-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
        gap: 0.6rem;
        margin-bottom: 1rem;
    }
    .sector-cell {
        border-radius: var(--radius-card-sm);
        padding: 0.85rem 0.9rem;
        text-align: center;
        border: 1px solid rgba(255,255,255,0.08);
        transition: transform 0.15s;
        cursor: default;
    }
    .sector-cell:hover { transform: translateY(-2px); }
    .sector-name { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.6px; text-transform: uppercase; color: ${sector_name_clr}; margin-bottom: 0.3rem; }
    .sector-ticker { font-size: 0.62rem; color: ${sector_ticker_clr}; margin-bottom: 0.4rem; }
    .sector-pct { font-size: 1.25rem; font-weight: 800; line-height: 1; }
    .sector-sub { font-size: 0.68rem; margin-top: 0.25rem; opacity: 1; }
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

        /* #개선 모바일 터치 편의성 — 지표 카드/메트릭 그리드는 2열 고정으로
           촘촘하게(한눈에), 대신 탭 가능한 버튼류는 손가락 오차를 감안해
           키우고 간격을 넓힘. "많이 보여주기"와 "누르기 쉽게"를 요소 종류별로
           다르게 적용 (정보 카드=밀도↑, 조작 버튼=터치영역↑). */
        .metric-grid { grid-template-columns: 1fr 1fr; gap: 0.55rem; }
        .metric-card { padding: 0.7rem 0.8rem !important; }
        .metric-label { font-size: 0.62rem; }
        .metric-value { font-size: 1.15rem; }
        .metric-delta { font-size: 0.68rem; }

        /* 세그먼트 컨트롤(뷰 전환) 탭 영역 확대 — 엄지 터치 기준 최소 44px */
        [data-testid="stSegmentedControl"] [data-testid="stBaseButton-segmented_control"],
        [data-testid="stSegmentedControl"] [data-testid="stBaseButton-segmented_controlActive"],
        [data-testid="stSegmentedControl"] label,
        [data-testid="stSegmentedControl"] button,
        [data-testid="stSegmentedControl"] div[role="radiogroup"] label,
        [data-testid="stSegmentedControl"] div[data-baseweb="button-group"] > * {
            min-height: 2.75rem !important;
            font-size: 0.92rem !important;
            padding: 0.55rem 0.4rem !important;
        }

        /* 사이드바 슬라이더/체크박스 등 조작 요소 터치 영역 확대 */
        [data-testid="stSidebar"] [data-baseweb="slider"] { padding: 0.4rem 0 !important; }
        [data-testid="stCheckbox"] label, [data-testid="stRadio"] label { min-height: 2.4rem; display: flex; align-items: center; }
    }

    /* ── 라이트 모드: 저대비 텍스트 색상 전면 보정 ──────────────────── *
     * (버그 수정: 기존 코드는 이 블록이 바깥 f-string 안에 중첩된      *
     * "일반 문자열"인데도 중괄호를 { } 로 이중 이스케이프해서       *
     * 실제로는 깨진 CSS( { ... } )가 출력되어 라이트 모드 보정이    *
     * 하나도 적용되지 않고 있었음. 홑 중괄호로 수정 + 저대비 색상     *
     * 전반(회색 노트, 파스텔 강조색 등)에 대한 보정을 추가함.         */
    $light_mode_overrides
</style>
