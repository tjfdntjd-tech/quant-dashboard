import json
import os
import random
import re
import streamlit as st
import yfinance as yf
from yfinance import EquityQuery
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from deep_translator import GoogleTranslator
from concurrent.futures import ThreadPoolExecutor, as_completed
from string import Template

# ════════════════════════════════════════════════════════════════
# 상수
# ════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════
# 환율 — exchangerate-api.com 무료 API (캐시 TTL 1시간)
# ════════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_usd_to_krw() -> float:
    """
    Open Exchange Rates의 무료 엔드포인트로 USD→KRW 실시간 환율을 조회합니다.
    API 키 불필요, 호출 제한 없음.
    실패 시 1,400원 폴백.
    """
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        rate = data["rates"]["KRW"]
        return float(rate)
    except Exception:
        return 1400.0  # 폴백: 조회 실패 시 고정값 사용

TRADING_THRESHOLD = 500           # 거래대금 기준 (억 원)
MEMO_FILE         = "memos.json"  # #9 메모 영구 저장 파일

# ════════════════════════════════════════════════════════════════
# #개선 번역 캐시 영구 저장 파일 (TTL 만료로 인한 재번역 방지)
# ════════════════════════════════════════════════════════════════
TRANSLATE_CACHE_FILE = "translate_cache.json"

# ════════════════════════════════════════════════════════════════
# #개선 CSS 템플릿 파일 경로 — inject_css()의 거대한 인라인 문자열을
# styles/theme.css.tpl 로 분리해 스타일 수정 시 파이썬 코드를
# 건드리지 않아도 되도록 함. 스크립트 파일 기준 상대경로로 찾으므로
# 실행 위치(cwd)와 무관하게 항상 올바른 경로를 찾는다.
# ════════════════════════════════════════════════════════════════
APP_DIR       = os.path.dirname(os.path.abspath(__file__))
CSS_TPL_PATH  = os.path.join(APP_DIR, "styles", "theme.css.tpl")

# ════════════════════════════════════════════════════════════════
# #개선 라이트 모드 전용 색상 보정 CSS
# theme.css.tpl 안의 다크/라이트 공통 구조와 달리, 라이트 모드에서만
# 추가로 덮어써야 하는 저대비 텍스트 보정 규칙들이라 별도 상수로 분리.
# (inject_css()가 dark=False일 때만 $light_mode_overrides 자리에 채워 넣음)
# ════════════════════════════════════════════════════════════════
LIGHT_MODE_OVERRIDE_CSS = """
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stMarkdown,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] div {
        color: #1e1b4b !important;
    }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: #0f0d2a !important;
    }
    .stMarkdown p, .stMarkdown span,
    [data-testid="stAppViewContainer"] label,
    [data-testid="stAppViewContainer"] .stSelectbox label,
    [data-testid="stAppViewContainer"] .stCheckbox label,
    [data-testid="stAppViewContainer"] .stRadio label,
    [data-testid="stAppViewContainer"] .stTextInput label,
    [data-testid="stAppViewContainer"] p {
        color: #1e1b4b !important;
    }

    /* 시그니처 컬러 변수 재정의 — var(--c-*)를 쓰는 모든 요소
       (title-*, sent-pos/neg, impact-badge, bull/bear-badge,
       pos-card/neg-card, news-card:hover 등)에 자동 적용됨 */
    :root {
        --c-amber:  #92600a !important;
        --c-teal:   #0f766e !important;
        --c-indigo: #4338ca !important;
        --c-violet: #6d28d9 !important;
        --c-cyan:   #0369a1 !important;
        --c-rose:   #be123c !important;
        --c-green:  #047857 !important;
        --c-red:    #dc2626 !important;
        --c-blue:   #1d4ed8 !important;
        --c-orange: #c2410c !important;
    }

    /* 하드코딩된 클래스 색상 보정 */
    .delta-up   { color: #047857 !important; }
    .delta-down { color: #dc2626 !important; }
    .delta-neu  { color: #475569 !important; }
    /* #디자인개선(컬러 그라디언트 카드): alert-banner/china-banner/split-banner는
       이제 채도 높은 그라디언트 배경 + 흰색 텍스트로 자체 완결되는 카드라
       라이트/다크 모드 보정이 불필요 (과거엔 어두운 배경 기준 저대비 파스텔
       텍스트라 라이트 모드에서 진한 색으로 덮어써야 했음) */
    .sent-neu   { color: #92600a !important; }
    .news-link  { color: #4338ca !important; }
    .news-link:hover { color: #6d28d9 !important; }
    .scan-title { color: #92600a !important; }
    .status-text { color: #334155 !important; }

    /* 인라인 style="color:..." 로 하드코딩된 파스텔 색상 보정
       (dark 테마 배경 기준으로 만들어진 값이라 밝은 배경에서 저대비)
       #개선: rgba(148,163,184/255,255,255)류는 이제 다크/라이트 공통으로
       inject_css() 안의 통합 대비 보정(unified_contrast_css)에서 처리하므로
       여기서는 중복 제거. */
    /* #버그수정: 아래 4개 색상(#34d399/#fbbf24/#e0943a/#9c7ff2)은 실제로는
       metric-card/glass-card/scan-header/news-card처럼 배경이 --card-solid로
       항상 순검정 고정인 곳에서만 인라인으로 쓰이고 있어, 라이트 모드라고
       어둡게 덮어쓰면 "어두운 배경 위 어두운 글씨"가 되어 오히려 안 보이게
       됨. 카드 배경이 안 바뀌므로 원래의 밝은 색 그대로 두는 것이 맞음.
       (st.dataframe 하이라이트에 쓰이는 #34d399만 예외적으로 흰 배경 위에
       놓일 수 있으나, 해당 케이스는 소수라 카드 쪽 저대비를 막는 쪽을 우선함) */
    [style*="color:#6ee7b7"],  [style*="color: #6ee7b7"]  { color: #059669 !important; }
    [style*="color:#a7f3d0"],  [style*="color: #a7f3d0"]  { color: #0d9488 !important; }
    [style*="color:#f87171"],  [style*="color: #f87171"]  { color: #dc2626 !important; }
    [style*="color:#ef4444"],  [style*="color: #ef4444"]  { color: #b91c1c !important; }
    [style*="color:#fca5a5"],  [style*="color: #fca5a5"]  { color: #b91c1c !important; }
    [style*="color:#fecaca"],  [style*="color: #fecaca"]  { color: #991b1b !important; }
    [style*="color:#7b7de3"],  [style*="color: #7b7de3"]  { color: #4338ca !important; }
    [style*="color:#60a5fa"],  [style*="color: #60a5fa"]  { color: #1d4ed8 !important; }
    [style*="color:#94a3b8"],  [style*="color: #94a3b8"]  { color: #475569 !important; }
    [style*="color:#ff6a00"],  [style*="color: #ff6a00"]  { color: #c2410c !important; }
"""

# ════════════════════════════════════════════════════════════════
# 아이콘 — 단색 원형 배지 스타일 (요청 이미지 참고: 실선 벡터 아이콘)
# 특정 브랜드 로고(페이스북/X/틱톡 등)는 상표이므로 재현하지 않고,
# 동일한 "단색 원형 + 라인 아이콘" 톤앤매너만 차용한 범용 아이콘 세트.
# ════════════════════════════════════════════════════════════════
_ICON_SVG = {
    # 말풍선 — 소셜 미디어 섹션
    "chat": '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>',
    # 신문 — 뉴스 / Yahoo Finance
    "news": '<rect x="3" y="4" width="18" height="16" rx="2"/><line x1="7" y1="8.5" x2="17" y2="8.5"/><line x1="7" y1="12" x2="17" y2="12"/><line x1="7" y1="15.5" x2="13" y2="15.5"/>',
    # 말풍선 + 시세선 — StockTwits
    "quote": '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/><path d="M8 11.5l2.2 2.2L16 8.2" stroke-width="1.6"/>',
    # 벽돌담 — 악성매물대(저항선)
    "wall": '<rect x="3" y="4" width="18" height="16" rx="1.5"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="3" y1="16" x2="21" y2="16"/><line x1="9" y1="4" x2="9" y2="10"/><line x1="15" y1="10" x2="15" y2="16"/><line x1="6" y1="16" x2="6" y2="20"/><line x1="18" y1="16" x2="18" y2="20"/>',
    # 로켓 — 급등 이력 / 급등주 검색기
    "rocket": '<path d="M4.5 16.5c-1.5 1.5-2 5-2 5s3.5-.5 5-2c.8-.8 1-2.2.5-3-.5-.6-2.2-.5-3.5.5z"/><path d="M12 15l-3-3c1.5-4 4-8 7.5-9.5C19.5 1 22 3 21.5 6c-1.5 3.5-5.5 6-9.5 9z"/><path d="M9 12c-1.5 0-3 1-3.5 2.5"/><circle cx="15" cy="9" r="1.5"/>',
    # 문서/공시 — 오퍼링 공시 이력
    "doc": '<path d="M6 2.5h8l4 4V21a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1z"/><path d="M14 2.5V7h4"/><line x1="8" y1="12" x2="16" y2="12"/><line x1="8" y1="16" x2="16" y2="16"/>',
    # 전구 — 실시간 자금 유입 체크
    "bulb": '<path d="M9 18h6"/><path d="M10 21h4"/><path d="M12 3a6 6 0 0 0-3.5 10.9c.5.4.8 1 .8 1.6H14.7c0-.6.3-1.2.8-1.6A6 6 0 0 0 12 3z"/>',
    # 상승 추세선 — 이동평균선 배열
    "trend": '<polyline points="3,17 9,10 13,13 21,4"/><polyline points="15,4 21,4 21,10"/>',
    # 메모/연필 — 분석 메모
    "note": '<path d="M4 20l1-4L16.5 4.5a1.5 1.5 0 0 1 2.1 0l0.9.9a1.5 1.5 0 0 1 0 2.1L8 19l-4 1z"/><line x1="14" y1="7" x2="17" y2="10"/>',
    # 그리드 — 섹터 히트맵
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    # 불꽃 — 실시간 호재
    "fire": '<path d="M12 2s-1 3-1 5c0 1 .5 1.8 1 2.5.7-1 1-2 1-3 2 1.5 4 4 4 7.5A5 5 0 0 1 12 19a5 5 0 0 1-5-5c0-3 2-4.5 3-6.5.3 1 1 1.8 1 3 .5-.7 1-2 1-3.5A7 7 0 0 0 12 2z"/>',
    # 막대 차트 — 기술 분석
    "chart": '<line x1="4" y1="20" x2="20" y2="20"/><rect x="6" y="12" width="3" height="8"/><rect x="11" y="7" width="3" height="13"/><rect x="16" y="15" width="3" height="5"/>',
    # 카메라 — AI 차트 해석(이미지 업로드)
    "camera": '<path d="M4 8h3l1.5-2h7L17 8h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13.5" r="3.5"/>',
    # 과녁 — 악성매물대 돌파 가능성 점검(게이지)
    "target": '<circle cx="12" cy="12" r="8.2"/><circle cx="12" cy="12" r="4.6"/><circle cx="12" cy="12" r="1"/>',
}

def mono_icon_badge(icon_key: str, color: str = "#111827", size: int = 32,
                     glyph_size: int = 16, outline: bool = False) -> str:
    """리퀴드 글래스 스타일 원형 배지 아이콘 HTML(SVG)을 반환.

    #디자인개선(리퀴드 글래스): 참고로 받은 iOS 홈 화면 위젯 / 유리 토글
    버튼 세트(둥근 원 위쪽에 흰 하이라이트가 맺히고, 테두리는 얇은 반투명
    링, 바깥은 살짝 뜬 그림자로 볼록해 보이는 스타일)를 원형 배지에 반영.
    실제 광택·그림자 레이어는 theme.css.tpl 의 .liquid-icon(::after)에서
    처리하고, 여기서는 배경에 방향성 있는 radial-gradient 하이라이트를
    원색 위에 얹어 CSS 레이어와 합쳐졌을 때 유리알처럼 보이게 한다.

    outline=False → 컬러 유리 구슬 + 흰색 아이콘 (참고 이미지 위쪽 톤)
    outline=True  → 반투명 유리판 + 테두리색 라인 아이콘 (참고 이미지 아래쪽 톤)
    """
    path = _ICON_SVG.get(icon_key, "")
    if outline:
        return (
            f'<div class="liquid-icon liquid-icon-outline" '
            f'style="width:{size}px;height:{size}px;border-color:{color};">'
            f'<svg width="{glyph_size}" height="{glyph_size}" viewBox="0 0 24 24" '
            f'fill="none" stroke="{color}" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round">{path}</svg></div>'
        )
    return (
        f'<div class="liquid-icon" style="width:{size}px;height:{size}px;'
        f'background:{color};">'
        f'<svg width="{glyph_size}" height="{glyph_size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="#ffffff" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round">{path}</svg></div>'
    )

# ════════════════════════════════════════════════════════════════
# 공통 UI 헬퍼 — 반복되는 섹션 헤더 HTML 렌더링을 함수로 분리
# ════════════════════════════════════════════════════════════════
def ui_section_header(icon: str, title: str, icon_class: str = "icon-cyan", title_class: str = "title-cyan"):
    """반복되는 section-header HTML 구조를 공통 함수로 제거.

    icon_class / title_class를 모두 인자로 받아, 색상 테마가 다른
    섹션(rose/amber/teal/violet 등)에도 그대로 재사용 가능하도록 함.

    icon 이 mono_icon_badge()로 만든 완성된 원형 배지(HTML div)인 경우
    ('<div' 로 시작) 이중 원 래핑을 피하기 위해 section-icon 클래스 없이
    그대로 삽입한다.
    """
    icon_html = icon if icon.strip().startswith("<div") else f'<div class="section-icon {icon_class}">{icon}</div>'
    st.markdown(
        f"""<div class="section-header">
            {icon_html}
            <div class="section-title {title_class}">{title}</div>
        </div>""",
        unsafe_allow_html=True,
    )

# ════════════════════════════════════════════════════════════════
# 오퍼링(유상증자) 관련 SEC 공시 서식
# ════════════════════════════════════════════════════════════════
OFFERING_FORM_TYPES = {
    "S-1", "S-1/A", "S-3", "S-3/A", "S-11", "S-11/A",
    "F-1", "F-1/A", "F-3", "F-3/A",
    "424B1", "424B2", "424B3", "424B4", "424B5", "424B7", "424B8",
}

# ════════════════════════════════════════════════════════════════
# 나스닥 최소 호가($1) 규정 준수 파라미터
# (Nasdaq Listing Rule 5550(a)(2) — 참고용 추정치 계산에 사용)
# ════════════════════════════════════════════════════════════════
NASDAQ_MIN_BID          = 1.00
NASDAQ_DEFICIENCY_DAYS  = 30    # 연속 영업일 미만 시 결핍통지(Deficiency Notice) 발송 기준
NASDAQ_CURE_PERIOD_DAYS = 180   # 통지 후 유예기간 (캘린더 일)

# ════════════════════════════════════════════════════════════════
# 섹터 ETF 정의 (S&P 500 11개 섹터)
# ════════════════════════════════════════════════════════════════
SECTOR_ETFS = [
    ("XLK",  "기술"),
    ("XLF",  "금융"),
    ("XLV",  "헬스케어"),
    ("XLY",  "임의소비재"),
    ("XLP",  "필수소비재"),
    ("XLE",  "에너지"),
    ("XLI",  "산업재"),
    ("XLB",  "소재"),
    ("XLRE", "부동산"),
    ("XLU",  "유틸리티"),
    ("XLC",  "커뮤니케이션"),
]

# ════════════════════════════════════════════════════════════════
# #9 메모 영구 저장 헬퍼
# ════════════════════════════════════════════════════════════════
def load_memos() -> dict:
    """앱 재시작 후에도 메모를 복원합니다."""
    try:
        if os.path.exists(MEMO_FILE):
            with open(MEMO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_memos(memos: dict) -> None:
    """메모를 JSON 파일로 저장합니다."""
    try:
        with open(MEMO_FILE, "w", encoding="utf-8") as f:
            json.dump(memos, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ════════════════════════════════════════════════════════════════
# 즐겨찾기 영구 저장 헬퍼 (메모와 동일한 방식)
# ════════════════════════════════════════════════════════════════
FAVORITES_FILE = "favorites.json"

def load_favorites() -> list:
    """앱 재시작 후에도 즐겨찾기를 복원합니다."""
    try:
        if os.path.exists(FAVORITES_FILE):
            with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
    except Exception:
        pass
    return []

def save_favorites(favorites: list) -> None:
    """즐겨찾기를 JSON 파일로 저장합니다."""
    try:
        with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(favorites, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ════════════════════════════════════════════════════════════════
# 1. 페이지 설정 — set_page_config는 반드시 가장 먼저
# ════════════════════════════════════════════════════════════════
st.set_page_config(page_title="급등주 실시간 검증기 V3", layout="wide", initial_sidebar_state="auto")

# ════════════════════════════════════════════════════════════════
# #1 session_state 초기화 — 단일 위치, 중복 제거
# ════════════════════════════════════════════════════════════════
_defaults = {
    "favorites":        load_favorites(),   # 파일에서 복원
    "selected_ticker":  "",
    "memos":            load_memos(),   # #9 파일에서 복원
    "scan_results":     [],
    "show_heatmap":     False,          # 섹터 히트맵 토글 (사이드바 버튼보다 먼저 초기화)
    "show_screener":    False,          # 급등주 검색기 토글
    "screener_results": [],
    "has_searched":     False,          # #15 검색 실행 여부 — 기간 변경 등 리렌더링 후에도 결과 유지
    "active_ticker":    "",             # #15 마지막으로 검색을 실행한 티커
    "dark_mode":        True,           # 다크/라이트 모드 토글 (기본값: 다크 모드)
}
for _k, _v in _defaults.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ════════════════════════════════════════════════════════════════
# 캐시 래퍼 함수
# ════════════════════════════════════════════════════════════════
@st.cache_data(ttl=300, show_spinner=False)
def fetch_history(ticker: str) -> pd.DataFrame:
    """yfinance 1년치 OHLCV — 동일 티커 재검색 시 재다운로드 없이 즉시 반환"""
    return yf.Ticker(ticker).history(period="1y")

@st.cache_data(ttl=120, show_spinner=False)
def fetch_top_gainers(min_pct: float, min_price: float, max_price: float,
                       min_volume: int, limit: int = 40) -> list:
    """
    Yahoo Finance 공식 스크리너(yf.screen)로 조건에 맞는 급등주를 조회합니다.
    실시간(지연 가능) 시세 기준 상승률/거래량/주가 조건으로 필터링.
    이후 enrich_screener_results()에서 RSI·거래대금 등 상세 지표를 추가로 병합하므로,
    후속 필터링(중국계 제외/동전주 제외 등)에서 걸러질 종목을 감안해 넉넉하게 조회합니다.
    """
    try:
        query = EquityQuery('and', [
            EquityQuery('gt',  ['percentchange',   min_pct]),
            EquityQuery('gte', ['intradayprice',   min_price]),
            EquityQuery('lte', ['intradayprice',   max_price]),
            EquityQuery('gt',  ['dayvolume',       min_volume]),
            EquityQuery('eq',  ['region',          'us']),
        ])
        result = yf.screen(query, sortField='percentchange', sortAsc=False, size=limit)
        quotes = (result or {}).get('quotes', [])
        out = []
        for q in quotes:
            out.append({
                "ticker":     q.get("symbol", ""),
                "name":       q.get("shortName") or q.get("longName") or "",
                "price":      q.get("regularMarketPrice", 0) or 0,
                "pct_change": q.get("regularMarketChangePercent", 0) or 0,
                "volume":     q.get("regularMarketVolume", 0) or 0,
                "market_cap": q.get("marketCap", 0) or 0,
                "exchange":   q.get("fullExchangeName", ""),
            })
        return out
    except Exception:
        return []

@st.cache_data(ttl=120, show_spinner=False)
def enrich_screener_results(tickers: tuple) -> dict:
    """
    검색기 1차 결과(tickers)를 받아 종목별 상세 지표를 ThreadPoolExecutor로 병렬 수집합니다.
    - RSI(14), 전일 대비 거래량 비율(%), 20일 거래량 MA 대비 비율(%)
    - 당일 거래대금(억원 환산, 실시간 환율 적용)
    - 국가(중국/홍콩 여부) — 리스크 스크리닝용
    - 나스닥 최소호가($1) 컴플라이언스 추정 (calc_nasdaq_compliance 재사용)
    fetch_history / fetch_ticker_info는 이미 개별적으로 st.cache_data 캐싱되어 있으므로
    여기서는 병렬 호출만 담당하고 이중 캐싱하지 않습니다.
    """
    usd_krw = fetch_usd_to_krw()

    def _enrich_one(ticker: str) -> dict:
        try:
            hist = fetch_history(ticker)
            if hist.empty or len(hist) < 2:
                return {"ticker": ticker, "error": True}
            hist = calc_indicators(hist.dropna())
            today     = hist.iloc[-1]
            yesterday = hist.iloc[-2]

            rsi_val = today['RSI']
            rsi     = round(float(rsi_val), 1) if pd.notna(rsi_val) else None

            vol_ratio = (today['Volume'] / yesterday['Volume'] * 100) if yesterday['Volume'] else 0
            # #버그수정: VOL_MA20이 20일 미만 데이터로 NaN이 될 수 있음(calc_indicators 참고).
            # 예전처럼 1주로 나누면 수백만% 같은 말도 안 되는 값이 나와 "거래량 급증"이
            # 오탐지됨 → 데이터 부족 시 현재 거래량 자체를 기준으로 삼아 중립(100%)로 처리.
            vol_ma20  = today['VOL_MA20'] if pd.notna(today['VOL_MA20']) and today['VOL_MA20'] > 0 else today['Volume']
            vol_ma20_ratio = (today['Volume'] / vol_ma20) * 100 if vol_ma20 else 0

            trading_value_usd     = today['Close'] * today['Volume']
            trading_value_krw_eok = (trading_value_usd * usd_krw) / 100_000_000

            info      = fetch_ticker_info(ticker)
            country   = str(info.get("country") or "").strip()
            is_china  = country in {"China", "Hong Kong"}

            nasdaq_risk = calc_nasdaq_compliance(hist, today['Close'])

            return {
                "ticker":            ticker,
                "rsi":               rsi,
                "vol_ratio":         round(vol_ratio, 0),
                "vol_ma20_ratio":    round(vol_ma20_ratio, 0),
                "trading_value_eok": round(trading_value_krw_eok, 1),
                "is_china":          is_china,
                "country":           country,
                "nasdaq_risk":       nasdaq_risk,
                "error":             False,
            }
        except Exception:
            return {"ticker": ticker, "error": True}

    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(_enrich_one, tickers))

    return {r["ticker"]: r for r in results}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_sector_data() -> list:
    """11개 섹터 ETF의 당일/1주/1개월 수익률을 병렬로 수집"""
    def _fetch_one(etf_tuple):
        ticker_sym, sector_name = etf_tuple
        try:
            hist = yf.Ticker(ticker_sym).history(period="3mo")
            if hist.empty or len(hist) < 2:
                return None
            hist = hist.dropna()
            close = hist['Close']
            d1_pct  = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100
            w1_pct  = (close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100  if len(close) >= 6  else 0
            m1_pct  = (close.iloc[-1] - close.iloc[-22]) / close.iloc[-22] * 100 if len(close) >= 22 else 0
            return {
                "ticker":  ticker_sym,
                "sector":  sector_name,
                "d1":      round(d1_pct, 2),
                "w1":      round(w1_pct, 2),
                "m1":      round(m1_pct, 2),
                "price":   round(close.iloc[-1], 2),
            }
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=11) as ex:
        results = list(ex.map(_fetch_one, SECTOR_ETFS))
    return [r for r in results if r is not None]

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yahoo_news(ticker: str) -> list:
    """yfinance 뉴스 목록 캐싱 — #14 try/except 추가"""
    try:
        return yf.Ticker(ticker).news or []
    except Exception:
        return []

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ticker_info(ticker: str) -> dict:
    """
    yfinance .info 딕셔너리를 TTL 1시간으로 캐싱합니다.
    매 리렌더링마다 네트워크 요청이 발생하던 성능 저하를 방지합니다.
    실패 시 빈 딕셔너리를 반환하여 호출부에서 .get() 사용이 안전합니다.
    """
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_spike_history(ticker: str) -> pd.DataFrame:
    """
    상장 이후 전체 기간(period='max')을 조회해 하루 등락률이 +100% 이상이었던
    날짜들을 찾습니다. 급등주는 종종 상장 초기~단기간에 여러 번의 100%+ 급등을
    겪으므로, 차트용 1년치 데이터(fetch_history)와는 별도로 전체 기간을 조회합니다.
    """
    try:
        df = yf.Ticker(ticker).history(period="max")
        if df.empty or len(df) < 2:
            return pd.DataFrame()
        df = df.dropna(subset=["Close"])
        df["PctChange"] = df["Close"].pct_change() * 100
        spikes = df[df["PctChange"] >= 100].copy()
        spikes = spikes[["Close", "PctChange", "Volume"]].sort_index(ascending=False)
        return spikes
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_offering_history(ticker: str) -> list:
    """
    야후 파이낸스가 제공하는 SEC 공시 목록(Ticker.sec_filings)에서
    유상증자/오퍼링과 직접 관련된 서식(S-1, S-3, 424B 시리즈 등)만 필터링합니다.
    실제 공모 여부·금액까지는 알 수 없으므로 '오퍼링 가능성이 있는 공시' 목록입니다.
    """
    try:
        filings = yf.Ticker(ticker).sec_filings
        if not filings:
            return []
        results = []
        for f in filings:
            ftype = (f.get("type") or "").upper().strip()
            if ftype in OFFERING_FORM_TYPES:
                exhibits = f.get("exhibits") or []
                url = f.get("edgarUrl") or (exhibits[0].get("url") if exhibits else "") or ""
                results.append({
                    "date":  f.get("date", "") or "",
                    "type":  f.get("type", "") or ftype,
                    "title": f.get("title", "") or f.get("type", ""),
                    "url":   url,
                })
        results.sort(key=lambda x: x["date"], reverse=True)
        return results
    except Exception:
        return []

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_short_interest(ticker: str) -> dict:
    """
    yfinance .info에서 공매도 관련 지표(공매도 수량, 전월 대비 변동,
    Days-to-Cover, 유통주식 대비 공매도 비율)를 추출합니다.
    Yahoo Finance의 공매도 데이터는 FINRA 집계 기준 통상 격주(2주) 간격으로만
    갱신되므로 실시간 수치가 아니라 '가장 최근 발표된 결산일 기준' 값입니다.
    """
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        return {}

    shares_short = info.get("sharesShort")
    if not shares_short:
        return {}

    prior_month     = info.get("sharesShortPriorMonth")
    short_ratio     = info.get("shortRatio")               # Days-to-Cover
    short_pct_float = info.get("shortPercentOfFloat")       # 유통주식 대비 비율 (0~1)
    date_raw        = info.get("dateShortInterest")

    pct_change_mom = None
    if prior_month:
        try:
            pct_change_mom = (shares_short - prior_month) / prior_month * 100
        except Exception:
            pct_change_mom = None

    date_str = ""
    if date_raw:
        try:
            if isinstance(date_raw, (int, float)):
                date_str = datetime.fromtimestamp(date_raw).strftime("%Y-%m-%d")
            else:
                date_str = pd.Timestamp(date_raw).strftime("%Y-%m-%d")
        except Exception:
            date_str = ""

    return {
        "shares_short":    shares_short,
        "prior_month":     prior_month,
        "pct_change_mom":  pct_change_mom,
        "short_ratio":     short_ratio,
        "short_pct_float": short_pct_float,
        "date":            date_str,
    }


def calc_execution_strength(candles: pd.DataFrame) -> dict:
    """
    당일 3분봉(캔들)의 양봉/음봉 거래량 비율로 '체결강도'를 근사 추정합니다.
    한국 HTS의 체결강도(매수체결량/매도체결량*100)는 틱 단위 호가 체결 데이터가
    있어야 정확히 계산되지만, 미국 주식은 그런 실시간 체결 데이터를 공개 API로
    구할 수 없습니다. 대안으로 각 3분봉의 방향(양봉=매수 우위, 음봉=매도 우위)에
    거래량을 배분해 근사치를 산출합니다 — 참고용 프록시 지표입니다.
    """
    if candles is None or candles.empty or len(candles) < 2:
        return {}
    df = candles.copy()
    up_vol   = float(df.loc[df["Close"] > df["Open"], "Volume"].sum())
    down_vol = float(df.loc[df["Close"] < df["Open"], "Volume"].sum())
    flat_vol = float(df.loc[df["Close"] == df["Open"], "Volume"].sum())

    if up_vol <= 0 and down_vol <= 0:
        return {}

    if down_vol <= 0:
        strength = 300.0  # 매도 체결이 거의 없어 상한 표시용 값
        capped = True
    else:
        strength = (up_vol / down_vol) * 100
        capped = strength > 300.0
        strength = min(strength, 300.0)

    return {
        "strength":    strength,
        "capped":      capped,
        "up_volume":   up_vol,
        "down_volume": down_vol,
        "flat_volume": flat_vol,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def calc_dilution_since_offering(ticker: str, offering_date: str) -> dict:
    """
    가장 최근 오퍼링(유상증자) 관련 공시일 이후, 실제 유통주식수가 얼마나
    늘었는지를 yfinance의 과거 발행주식수 시계열(get_shares_full)로 추정합니다.

    주의: ATM(시장가발행) 프로그램의 '승인 한도'나 '잔여 한도(달러 기준)'는
    공시 원문(424B5 등)에서만 확인 가능하며 시세 데이터만으로는 알 수 없습니다.
    본 함수는 그 대신 '공시일 이후 실제로 증가한 주식수(=이미 발행되어 시장에
    풀린 것으로 추정되는 희석 물량)'를 근사 계산한 것입니다.
    """
    if not offering_date:
        return {}
    try:
        offer_dt = pd.to_datetime(offering_date)
    except Exception:
        return {}
    try:
        shares_series = yf.Ticker(ticker).get_shares_full(
            start=(offer_dt - timedelta(days=7)).strftime("%Y-%m-%d"),
            end=datetime.now().strftime("%Y-%m-%d"),
        )
    except Exception:
        return {}
    if shares_series is None or shares_series.empty:
        return {}

    try:
        shares_series = shares_series.sort_index()
        before = shares_series[shares_series.index <= offer_dt]
        base_shares   = float(before.iloc[-1]) if not before.empty else float(shares_series.iloc[0])
        latest_shares = float(shares_series.iloc[-1])
        diluted_shares = latest_shares - base_shares
        diluted_pct = (diluted_shares / base_shares * 100) if base_shares else None
        return {
            "base_shares":    base_shares,
            "latest_shares":  latest_shares,
            "diluted_shares": diluted_shares,
            "diluted_pct":    diluted_pct,
        }
    except Exception:
        return {}


def calc_nasdaq_compliance(hist: pd.DataFrame, today_close: float) -> dict:
    """
    나스닥 최소 호가 요건(Listing Rule 5550(a)(2)) 관련 잔여 유예기간을 추정합니다.
    - 종가가 30 연속 영업일 동안 $1 미만이면 결핍통지(Deficiency Notice) 대상이 되고,
      통지일로부터 180일(캘린더 기준)의 유예기간이 주어지는 것이 일반적인 규정입니다.
    - 실제 통지 발송 여부·정확한 날짜는 공개 시세 데이터만으로는 알 수 없으므로,
      본 계산은 가격 데이터 기반의 '추정치'이며 공식 컴플라이언스 확인을 대체하지 않습니다.
    """
    if today_close is None or today_close >= NASDAQ_MIN_BID:
        return {"applicable": False}

    closes = hist["Close"].dropna()
    if closes.empty:
        return {"applicable": False}

    # 최근 종가부터 역순으로 연속 $1 미만 영업일 수 계산
    streak = 0
    streak_start_idx = None
    for i in range(len(closes) - 1, -1, -1):
        if closes.iloc[i] < NASDAQ_MIN_BID:
            streak += 1
            streak_start_idx = i
        else:
            break

    if streak_start_idx is None:
        return {"applicable": False}

    if streak >= NASDAQ_DEFICIENCY_DAYS:
        # 연속 30영업일째 되는 날 결핍통지가 발송되었다고 가정
        notice_idx      = streak_start_idx + NASDAQ_DEFICIENCY_DAYS - 1
        notice_date_est = closes.index[notice_idx].date()
        deadline_est     = notice_date_est + timedelta(days=NASDAQ_CURE_PERIOD_DAYS)
        days_left        = (deadline_est - datetime.now().date()).days
        return {
            "applicable":      True,
            "phase":           "notice_issued_est",
            "streak_days":     streak,
            "notice_date_est": notice_date_est,
            "deadline_est":    deadline_est,
            "days_left":       days_left,
        }
    else:
        return {
            "applicable":     True,
            "phase":          "counting",
            "streak_days":    streak,
            "days_to_notice": NASDAQ_DEFICIENCY_DAYS - streak,
        }

# ════════════════════════════════════════════════════════════════
# 주식병합(리버스 스플릿) 예정 뉴스 감지
# ════════════════════════════════════════════════════════════════
_REVERSE_SPLIT_PATTERNS = [
    re.compile(r"reverse\s+stock\s+split", re.I),
    re.compile(r"reverse\s+split", re.I),
    re.compile(r"주식\s*병합"),
    re.compile(r"역병합"),
    re.compile(r"리버스\s*스플릿"),
]

_RATIO_PATTERN = re.compile(r"(\d+)\s*[-: ]?\s*(?:for|대)\s*[-: ]?\s*(\d+)", re.I)

_EFFECTIVE_DATE_PATTERNS = [
    re.compile(r"effective\s+(?:as\s+of\s+|on\s+)?([A-Za-z]+\s+\d{1,2},?\s+\d{4})", re.I),
    re.compile(r"effective\s+(?:as\s+of\s+|on\s+)?(\d{1,2}/\d{1,2}/\d{2,4})", re.I),
    re.compile(r"(?:effective|시행일?|적용일?)\s*[:\-]?\s*(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})"),
]

def detect_reverse_split_news(news_items: list) -> list:
    """
    뉴스 제목(한글 번역본 + 영문 원문)에서 리버스 스플릿(주식병합) 관련
    키워드를 감지하고, 가능한 경우 정규식으로 병합 비율과 시행(effective)일을
    함께 추출합니다. 원문에 명시적인 날짜가 없으면 시행일은 None으로 남기고
    뉴스 게재일(date)만 표시합니다 — 실제 시행일은 원문 확인이 필요합니다.
    """
    results = []
    for n in news_items:
        text = " ".join(filter(None, [n.get("title", ""), n.get("title_en", "")]))
        if not text or not any(p.search(text) for p in _REVERSE_SPLIT_PATTERNS):
            continue

        ratio_match = _RATIO_PATTERN.search(text)
        ratio = f"{ratio_match.group(1)}-for-{ratio_match.group(2)}" if ratio_match else None

        eff_date = None
        for p in _EFFECTIVE_DATE_PATTERNS:
            m = p.search(text)
            if m:
                eff_date = m.group(1)
                break

        results.append({
            "date":           n.get("date", ""),
            "title":          n.get("title", "") or n.get("title_en", ""),
            "title_en":       n.get("title_en", ""),
            "link":           n.get("link", ""),
            "ratio":          ratio,
            "effective_date": eff_date,
        })
    return results

# ════════════════════════════════════════════════════════════════
# #개선 번역 결과 영구 캐시
# 기존엔 st.cache_data(ttl=3600)라서 1시간마다 캐시가 사라져
# 같은 뉴스 제목도 계속 재번역 요청을 보냈음 (구글 번역 비공식 API라
# 요청이 잦아질수록 차단/실패 위험이 커짐). 영어 뉴스 제목은 번역
# 결과가 바뀔 일이 없으므로, 파일(translate_cache.json)에 영구
# 저장해 앱을 재시작해도 동일 문장은 다시 번역하지 않도록 한다.
# ════════════════════════════════════════════════════════════════
def _load_translate_cache() -> dict:
    try:
        if os.path.exists(TRANSLATE_CACHE_FILE):
            with open(TRANSLATE_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save_translate_cache(cache: dict) -> None:
    try:
        with open(TRANSLATE_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass

def translate_texts_batch(texts: list) -> dict:
    """
    여러 문장을 한 번에 병렬로 번역하고, 캐시 파일에는 배치당 단 1회만 저장합니다.

    #성능개선: 기존 translate_text()는 문장 하나마다 번역 API를 호출하고 그때마다
    캐시 파일 전체를 디스크에 다시 썼습니다. 뉴스/소셜 섹션에서 이 함수를 최대
    8회까지 "순차" 호출했기 때문에 (번역 왕복 + 디스크 I/O) × 문장 수 만큼
    지연이 직렬로 누적되어 체감 로딩 속도가 느린 주된 원인이었습니다.
    → 신규 번역이 필요한 문장만 골라 스레드풀로 동시에 번역 요청을 보내고,
      캐시 저장은 배치 전체가 끝난 뒤 딱 한 번만 수행합니다.
    반환값: {원문: 번역문} 매핑 딕셔너리.
    """
    if "_translate_cache" not in st.session_state:
        st.session_state["_translate_cache"] = _load_translate_cache()
    cache = st.session_state["_translate_cache"]

    unique_texts = list(dict.fromkeys(t for t in texts if t))
    to_translate = [t for t in unique_texts if t not in cache]

    if to_translate:
        def _do(t: str):
            try:
                return t, GoogleTranslator(source='en', target='ko').translate(t)
            except Exception:
                return t, t

        with ThreadPoolExecutor(max_workers=min(8, len(to_translate))) as ex:
            for original, translated in ex.map(_do, to_translate):
                cache[original] = translated
        _save_translate_cache(cache)   # 배치 전체 완료 후 단 1회만 디스크에 저장

    return {t: cache.get(t, t) for t in unique_texts}

def translate_text(text: str) -> str:
    """단일 문장 번역 — 내부적으로 translate_texts_batch()를 재사용합니다."""
    if not text:
        return text
    return translate_texts_batch([text]).get(text, text)

def parse_yahoo_news_item(raw_item: dict) -> dict:
    """
    yfinance .news 응답 구조를 안전하게 파싱합니다.
    최신 yfinance는 title/publisher/link가 최상위가 아니라
    'content' 키 안에 한 번 더 감싸진 구조로 옵니다.
    """
    content   = raw_item.get("content", raw_item)
    title     = content.get("title", "제목 없음")
    publisher = (
        content.get("publisher")
        or (content.get("provider") or {}).get("displayName")
        or "출처 미확인"
    )
    link = (
        content.get("link")
        or (content.get("canonicalUrl") or {}).get("url")
        or ""
    )
    return {"title": title, "publisher": publisher, "link": link}

# ════════════════════════════════════════════════════════════════
# 기술적 지표 계산
# ════════════════════════════════════════════════════════════════
def calc_indicators(df: pd.DataFrame) -> pd.DataFrame:
    c = df['Close']

    # 이동평균선
    # #버그수정: min_periods=1이면 상장 초기(데이터 20~120일 미만) 종목에서
    # 실제 창 크기보다 훨씬 적은 데이터로 평균을 내버려 "MA120 돌파" 같은
    # 신호가 사실상 최근 종가와 거의 같은 값을 기준으로 왜곡되어 발생했음.
    # → 각 지표는 자신의 룩백 기간만큼 데이터가 쌓이기 전까지 NaN으로 두고,
    # 신호 판정부에서 NaN을 "데이터 부족"으로 명시적으로 처리한다.
    df['MA5']   = c.rolling(5,   min_periods=5).mean()
    df['MA20']  = c.rolling(20,  min_periods=20).mean()
    df['MA120'] = c.rolling(120, min_periods=120).mean()

    # #8 거래량 20일 이동평균
    df['VOL_MA20'] = df['Volume'].rolling(20, min_periods=20).mean()

    # RSI (14일)
    delta = c.diff()
    gain  = delta.clip(lower=0).rolling(14, min_periods=14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14, min_periods=14).mean()
    rs    = gain / loss.replace(0, float('nan'))
    df['RSI'] = 100 - (100 / (1 + rs))

    # 볼린저밴드 (20일, ±2σ)
    mid            = c.rolling(20, min_periods=20).mean()
    std            = c.rolling(20, min_periods=20).std()
    df['BB_MID']   = mid
    df['BB_UPPER'] = mid + 2 * std
    df['BB_LOWER'] = mid - 2 * std
    df['BB_WIDTH'] = (df['BB_UPPER'] - df['BB_LOWER']) / mid * 100

    # MACD (12/26 EMA, Signal 9)
    ema12           = c.ewm(span=12, adjust=False).mean()
    ema26           = c.ewm(span=26, adjust=False).mean()
    df['MACD']      = ema12 - ema26
    df['MACD_SIG']  = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_HIST'] = df['MACD'] - df['MACD_SIG']

    # 전고점(누적 최고가) 대비 낙폭 — 항상 0 이하 값 (%)
    running_peak  = c.cummax()
    df['Drawdown'] = (c - running_peak) / running_peak * 100

    return df

# ════════════════════════════════════════════════════════════════
# 🧱 악성매물대(거래량 프로파일 기반 저항 구간) 분석
# ════════════════════════════════════════════════════════════════
@st.cache_data(ttl=300, show_spinner=False)
def calc_supply_zones(hist: pd.DataFrame, current_price: float,
                       n_bins: int = 40, lookback_days: int = 252,
                       heavy_mult: float = 1.3, max_zones: int = 4,
                       max_zone_width_pct: float = 3.0) -> dict:
    """
    최근 lookback_days(기본 1년) 동안의 일별 High~Low 구간에 그날의 거래량을
    균등 분산시켜 '거래량 프로파일(Volume Profile)'을 만든 뒤, 현재가보다 위쪽에서
    평균 대비 거래량이 몰려있는 가격대(=매물대, 이전 매수자들의 평단가 밀집구간)를
    현재가에 가까운 순으로 추출한다.

    #개선 render_technical_analysis()와 render_chart_interpretation()이
    동일한 (hist, current_price, 파라미터) 조합으로 매번 이 함수를 중복 호출하고
    있었음 → st.cache_data로 캐싱해 같은 화면 렌더링 내 중복 계산을 제거.

    #개선 인접한 '매물대 판정' 구간(bin)을 조건 없이 통째로 하나의 매물대로
    합치다 보니, 거래량이 넓은 가격대에 걸쳐 몰린 종목은 매물대 폭이 지나치게
    넓게(예: 현재가 대비 10%+) 잡혀 실전에서 저항선으로 쓰기 어려웠음.
    → max_zone_width_pct(현재가 대비 최대 폭 %)를 넘는 병합 구간은 거래량
    가중치를 유지한 채 여러 개의 좁은 매물대로 재분할한다.
    """
    df = hist.tail(lookback_days).dropna(subset=["High", "Low", "Volume"])
    if df.empty or len(df) < 10 or current_price <= 0:
        return {"zones": [], "total_volume": 0.0, "has_data": False}

    price_min = float(df["Low"].min())
    price_max = float(df["High"].max())
    if price_max <= price_min:
        return {"zones": [], "total_volume": 0.0, "has_data": False}

    bin_edges = np.linspace(price_min, price_max, n_bins + 1)
    bin_vols  = np.zeros(n_bins)

    lows  = df["Low"].to_numpy()
    highs = df["High"].to_numpy()
    vols  = df["Volume"].to_numpy()

    for lo, hi, vol in zip(lows, highs, vols):
        if vol <= 0:
            continue
        if hi <= lo:
            idx = min(int((lo - price_min) / (price_max - price_min) * n_bins), n_bins - 1)
            bin_vols[idx] += vol
            continue
        overlap_lo = np.maximum(bin_edges[:-1], lo)
        overlap_hi = np.minimum(bin_edges[1:], hi)
        overlap    = np.clip(overlap_hi - overlap_lo, 0, None)
        total_overlap = overlap.sum()
        if total_overlap > 0:
            bin_vols += vol * (overlap / total_overlap)

    total_volume = float(bin_vols.sum())
    if total_volume <= 0:
        return {"zones": [], "total_volume": 0.0, "has_data": False}

    bin_mids = (bin_edges[:-1] + bin_edges[1:]) / 2
    avg_vol  = bin_vols.mean()

    above_mask = bin_mids > current_price
    heavy_mask = above_mask & (bin_vols >= avg_vol * heavy_mult)

    if not heavy_mask.any() and above_mask.any():
        above_idx = np.where(above_mask)[0]
        top_n = min(max_zones, len(above_idx))
        top_idx = above_idx[np.argsort(bin_vols[above_idx])[::-1][:top_n]]
        heavy_mask = np.zeros_like(heavy_mask)
        heavy_mask[top_idx] = True

    zones = []
    idx_list = np.where(heavy_mask)[0]
    if len(idx_list) > 0:
        group = [idx_list[0]]
        for i in idx_list[1:]:
            if i == group[-1] + 1:
                group.append(i)
            else:
                zones.append(group)
                group = [i]
        zones.append(group)

    zone_infos = []
    max_allowed_width = (current_price * (max_zone_width_pct / 100.0)) if max_zone_width_pct and max_zone_width_pct > 0 else None

    for group in zones:
        group = list(group)
        g_low_full  = bin_edges[group[0]]
        g_high_full = bin_edges[group[-1] + 1]
        width_full  = g_high_full - g_low_full

        # 병합된 구간이 허용 폭보다 넓으면 거래량 가중치를 유지한 채
        # 여러 개의 좁은 하위 매물대로 재분할한다.
        if max_allowed_width and width_full > max_allowed_width and len(group) > 1:
            n_splits = min(len(group), int(np.ceil(width_full / max_allowed_width)))
            sub_groups = [list(a) for a in np.array_split(np.array(group), n_splits)]
        else:
            sub_groups = [group]

        for sub in sub_groups:
            if not sub:
                continue
            g_low  = bin_edges[sub[0]]
            g_high = bin_edges[sub[-1] + 1]
            g_vol  = bin_vols[sub].sum()
            if g_vol <= 0:
                continue
            g_mid  = float((bin_mids[sub] * bin_vols[sub]).sum() / g_vol)
            pct_of_total = g_vol / total_volume * 100
            gap_pct = (g_mid - current_price) / current_price * 100
            avg_bin_in_zone = avg_vol * len(sub)
            ratio = g_vol / avg_bin_in_zone if avg_bin_in_zone > 0 else 1
            if ratio >= 2.0:
                strength = "매우 강함"
            elif ratio >= 1.5:
                strength = "강함"
            else:
                strength = "보통"
            zone_infos.append({
                "low": float(g_low), "high": float(g_high), "mid": g_mid,
                "volume": float(g_vol), "pct_of_total": pct_of_total,
                "gap_pct": gap_pct, "strength": strength, "ratio": ratio,
            })

    zone_infos.sort(key=lambda z: z["mid"])
    zone_infos = zone_infos[:max_zones]

    return {"zones": zone_infos, "total_volume": total_volume, "has_data": True}


def render_supply_zones(current_price: float, supply_data: dict):
    """현재가 위쪽 악성매물대(저항 구간) — 카드 그리드로 표시 (최대 4개)"""
    ui_section_header(mono_icon_badge("wall", color="var(--c-rose)"), "악성매물대 분석 (돌파 저항선)", "icon-rose", "title-rose")

    zones = supply_data.get("zones", [])
    if not supply_data.get("has_data") or not zones:
        st.markdown("""
        <div class="glass-card">
            <div class="status-row">
                <div class="status-item"><div class="status-dot dot-blue"></div>
                <div class="status-text">데이터가 부족하여 매물대를 산출할 수 없습니다</div></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    # 강도별 카드 색상/딜타 색상 매핑 — 강할수록 경고성이 짙은 톤(rose)을 사용
    strength_style = {
        "매우 강함": ("mc-rose",  "delta-down"),
        "강함":     ("mc-amber", "delta-neu"),
        "보통":     ("mc-cyan",  "delta-up"),
    }

    # #버그수정 여러 줄(들여쓰기 포함) f-string으로 카드를 만들면 metric-grid에
    # 끼워 넣을 때 빈 줄이 생겨 마크다운이 HTML 블록을 코드블록으로 오인식하는
    # 문제가 있었음(종합점수 카드에서 동일 이슈 발견/수정). 한 줄짜리 HTML로
    # 만들어 그 여지를 원천적으로 없앰.
    cards_html = ""
    for i, z in enumerate(zones, start=1):
        mc_cls, delta_cls = strength_style.get(z["strength"], ("mc-cyan", "delta-neu"))
        cards_html += (
            f'<div class="metric-card {mc_cls}">'
            f'<div class="metric-label">저항 구간 {i} &nbsp;·&nbsp; 현재가 대비 +{z["gap_pct"]:.1f}%</div>'
            f'<div class="metric-value" style="font-size:1.05rem;">${z["low"]:.2f} ~ ${z["high"]:.2f}</div>'
            f'<div class="metric-delta {delta_cls}">{z["strength"]} &nbsp;|&nbsp; 거래량 {z["volume"]:,.0f}주</div>'
            f'</div>'
        )

    st.markdown(f'<div class="metric-grid">{cards_html}</div>', unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# 🎯 실시간 악성매물대 돌파 가능성 점검
# ════════════════════════════════════════════════════════════════
def calc_breakout_probability(current_price: float, supply_data: dict,
                               rsi_val: float, vol_ma20_ratio: float,
                               macd_val: float, macd_sig_val: float,
                               macd_cross: bool) -> dict:
    """가장 가까운 악성매물대(저항 구간)를 현재 수급/모멘텀 지표로 얼마나
    돌파할 가능성이 있는지 0~100점 게이지로 환산한다.

    절대적인 매매 신호가 아니라 "저항까지 얼마나 가깝고, 그 저항이 얼마나
    두꺼우며, 지금 그걸 밀어붙일 힘(거래량·모멘텀)이 있는가"를 종합한
    참고용 점수이며, 4개 구성요소로 나눠 근거를 함께 보여준다.
      · 근접도(0~30) : 저항 하단까지 남은 거리가 가까울수록 高
      · 매물벽 두께(0~25, 역가중) : 매물대가 평균 대비 얼마나 두꺼운지 — 두꺼울수록 低
      · 수급 압력(0~30) : 거래량 MA20 대비 비율 + RSI 모멘텀 구간
      · MACD 흐름(0~15) : 골든크로스=만점, 상승 배열=절반, 그 외=0
    """
    zones = supply_data.get("zones", []) if supply_data else []
    if not zones or current_price <= 0:
        return {"has_zone": False}

    zone = zones[0]  # mid 기준 오름차순 정렬이므로 첫 번째가 현재가와 가장 가까운 저항
    gap_low_pct = (zone["low"] - current_price) / current_price * 100
    gap_low_pct = max(gap_low_pct, 0.0)  # 이미 저항 구간 내부/돌파 중이면 근접도 만점 처리

    # 1) 근접도 — 0%면 만점, 15% 이상 벌어지면 0점
    proximity_score = max(0.0, 30.0 * (1 - gap_low_pct / 15.0))

    # 2) 매물벽 두께 — ratio(평균 거래량 대비 배수) 1.0=만점, 3.0 이상=0점
    ratio = zone.get("ratio", 1.3)
    strength_score = max(0.0, 25.0 * (1 - (ratio - 1.0) / 2.0))

    # 3) 수급 압력 — 거래량(15점) + RSI 모멘텀(15점)
    vol_score = min(max((vol_ma20_ratio - 80.0) / 220.0, 0.0), 1.0) * 15.0
    # #버그수정: 상장 14거래일 미만 종목은 RSI가 NaN → 예전엔 이 값이 그대로
    # 산식에 들어가 total 점수 전체가 NaN("nan점")으로 새는 문제가 있었음.
    if pd.isna(rsi_val):
        rsi_score = 7.5   # 데이터 부족 시 중립(만점의 절반)으로 처리
    elif 50 <= rsi_val <= 75:
        rsi_score = 15.0
    elif rsi_val < 50:
        rsi_score = 15.0 * max(0.0, rsi_val / 50.0)
    else:
        rsi_score = 15.0 * max(0.0, 1 - (rsi_val - 75.0) / 25.0)
    pressure_score = vol_score + rsi_score

    # 4) MACD 흐름
    if macd_cross:
        macd_score = 15.0
    elif macd_val > macd_sig_val:
        macd_score = 8.0
    else:
        macd_score = 0.0

    total = round(min(100.0, proximity_score + strength_score + pressure_score + macd_score))

    if total >= 70:
        label, tier = "돌파 가능성 높음", "high"
    elif total >= 45:
        label, tier = "돌파 가능성 보통 — 관망", "mid"
    else:
        label, tier = "매물대 저항 우세 — 돌파 어려움", "low"

    return {
        "has_zone": True,
        "score": total,
        "label": label,
        "tier": tier,
        "gap_low_pct": gap_low_pct,
        "zone_low": zone["low"],
        "zone_high": zone["high"],
        "zone_strength": zone["strength"],
        "factors": [
            ("저항까지 거리", proximity_score, 30.0, f"매물대 하단까지 +{gap_low_pct:.1f}%"),
            ("매물벽 두께",   strength_score, 25.0, f"강도: {zone['strength']} (평균 대비 {ratio:.1f}배)"),
            ("수급 압력",     pressure_score, 30.0, f"거래량 MA20 대비 {vol_ma20_ratio:.0f}% · RSI {'데이터 부족' if pd.isna(rsi_val) else f'{rsi_val:.0f}'}"),
            ("MACD 흐름",     macd_score,     15.0, "골든크로스" if macd_cross else ("상승 배열" if macd_val > macd_sig_val else "약세 배열")),
        ],
    }


def render_breakout_probability(calc: dict):
    """돌파 가능성 게이지 카드 — 점수 막대 + 4개 구성요소 근거를 함께 표시."""
    ui_section_header(mono_icon_badge("target", color="var(--c-amber)"), "실시간 악성매물대 돌파 가능성 점검", "icon-amber", "title-amber")

    if not calc.get("has_zone"):
        st.markdown("""
        <div class="glass-card">
            <div class="status-row">
                <div class="status-item"><div class="status-dot dot-green"></div>
                <div class="status-text">현재가 위쪽에 감지된 악성매물대가 없습니다 — 저항 없이 신고가 경신 가능 구간입니다</div></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    tier_style = {
        "high": ("#34d399", "dot-green"),
        "mid":  ("#fbbf24", "dot-yellow"),
        "low":  ("#f2617e", "dot-red"),
    }
    fill_color, dot_cls = tier_style.get(calc["tier"], ("#fbbf24", "dot-yellow"))
    score = calc["score"]

    factors_html = ""
    for name, val, max_val, note in calc["factors"]:
        pct = round(val / max_val * 100) if max_val else 0
        factors_html += (
            f'<div style="margin-bottom:0.55rem;">'
            f'<div style="display:flex;justify-content:space-between;font-size:0.72rem;margin-bottom:0.2rem;">'
            f'<span style="color:rgba(148,163,184,0.75);font-weight:600;">{name}</span>'
            f'<span style="color:rgba(148,163,184,0.6);">{val:.0f} / {max_val:.0f}</span></div>'
            f'<div class="sentiment-bar-track" style="height:6px;">'
            f'<div class="sentiment-bar-fill" style="width:{pct}%;background:{fill_color};"></div></div>'
            f'<div style="font-size:0.68rem;color:rgba(148,163,184,0.55);margin-top:0.2rem;">{note}</div>'
            f'</div>'
        )

    st.markdown(f"""
    <div class="glass-card">
        <div class="status-row" style="margin-bottom:0.6rem;">
            <div class="status-item"><div class="status-dot {dot_cls}"></div>
            <div class="status-text"><strong>{calc['label']}</strong> &nbsp;·&nbsp; 가장 가까운 저항 ${calc['zone_low']:.2f} ~ ${calc['zone_high']:.2f} ({calc['zone_strength']})</div></div>
        </div>
        <div class="sentiment-bar-wrap" style="padding:0.7rem 0.9rem;margin-bottom:0.7rem;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.35rem;">
                <span style="font-size:0.72rem;font-weight:700;color:rgba(148,163,184,0.7);letter-spacing:0.8px;text-transform:uppercase;">돌파 가능성 종합 점수</span>
                <span style="font-size:1.1rem;font-weight:800;color:{fill_color};">{score:.0f}점</span>
            </div>
            <div class="sentiment-bar-track" style="height:10px;">
                <div class="sentiment-bar-fill" style="width:{score}%;background:{fill_color};"></div>
            </div>
        </div>
        {factors_html}
        <div style="font-size:0.68rem;color:rgba(148,163,184,0.5);margin-top:0.3rem;">
            ⚠️ 절대적 매수·매도 신호가 아닌 참고 지표이며, 매물대·거래량·RSI·MACD를 단순 가중 합산한 값입니다.
        </div>
    </div>
    """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# 급등주 검색기 / 즐겨찾기 스캔 공용 — 종합 점수(스코어 랭킹) 계산
# ════════════════════════════════════════════════════════════════
def calc_screener_score(r: dict) -> float:
    """
    검색 결과 여러 지표를 가중 합산해 0~100점 종합 점수를 산출합니다.
    급등주 검색기와 즐겨찾기 일괄 스캔 양쪽에서 동일한 기준으로 사용합니다.
    - 등락률           30% (50% 상승 시 만점)
    - 거래량 20일MA비율 25% (300% 도달 시 만점)
    - 거래대금(억원)    20% (1,000억 도달 시 만점)
    - 거래량 전일비     15% (300% 도달 시 만점)
    - RSI 모멘텀        10% (50~75 구간이 이상적 강세 구간, 과매수/과매도 시 감점)
    단순 산식이며 절대적 매수·매도 신호가 아닌 상대 비교용 참고 지표입니다.
    """
    pct        = r.get("pct_change") or 0
    vol_ma20_r = r.get("vol_ma20_ratio") or 0
    trading_v  = r.get("trading_value_eok") or 0
    vol_r      = r.get("vol_ratio") or 0
    rsi        = r.get("rsi")

    pct_score       = min(max(pct, 0) / 50, 1) * 30
    vol_ma20_score  = min(max(vol_ma20_r, 0) / 300, 1) * 25
    trading_score   = min(max(trading_v, 0) / 1000, 1) * 20
    vol_ratio_score = min(max(vol_r, 0) / 300, 1) * 15

    if rsi is None:
        rsi_score = 5.0
    elif 50 <= rsi <= 75:
        rsi_score = 10.0
    elif rsi > 75:
        rsi_score = max(0.0, 10.0 - (rsi - 75) * 0.6)      # 과매수 근접·초과 시 감점
    else:
        rsi_score = max(0.0, rsi / 50 * 5.0)                # 50 미만이면 모멘텀 약함으로 감점

    total = pct_score + vol_ma20_score + trading_score + vol_ratio_score + rsi_score
    return round(min(total, 100.0), 1)

# ════════════════════════════════════════════════════════════════
# #3 스톡타이탄 크롤링 함수 — render_news_section 위로 이동
# #13 User-Agent 랜덤 순환 추가
# ════════════════════════════════════════════════════════════════
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

def _random_headers() -> dict:
    """#13 매 요청마다 무작위 User-Agent 사용"""
    return {"User-Agent": random.choice(_USER_AGENTS)}

@st.cache_resource
def get_http_session() -> requests.Session:
    """전역에서 재사용할 HTTP 세션 생성 (Keep-Alive 유지로 성능 향상).

    매 요청마다 새 TCP/TLS 연결을 맺는 대신 커넥션 풀을 재사용해
    스톡타이탄 크롤링의 반복 호출 성능을 개선한다.
    """
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def _extract_titan_date(link_tag) -> str:
    """#4 날짜 파싱 로직을 별도 함수로 캡슐화.

    링크 태그의 부모 요소를 최대 4단계까지 탐색하며 datetime 속성이나
    날짜 관련 class를 가진 요소를 찾아 'MMM DD, YYYY' 형식으로 반환한다.
    찾지 못하면 '날짜 미확인'을 반환한다.
    """
    parent = link_tag.parent
    for _ in range(4):                     # 최대 4단계 상위 탐색
        if parent is None:
            break
        date_el = parent.find(attrs={"datetime": True})
        if not date_el:
            date_el = parent.find(class_=lambda x: x and any(
                kw in x.lower() for kw in ("date", "time", "published", "when")
            ))
        if date_el:
            raw_date = date_el.get("datetime") or date_el.text.strip()
            try:
                # 1차: ISO 형식 파싱 시도 (2024-05-01T12:34:56...)
                dt = datetime.fromisoformat(raw_date[:19])
                return dt.strftime("%b %d, %Y")
            except Exception:
                # 2차 폴백: 정규식으로 YYYY-MM-DD 또는 유사 패턴 추출
                _m = re.search(
                    r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})'   # YYYY-MM-DD 계열
                    r'|(\w{3,9})\s+(\d{1,2}),?\s+(\d{4})',       # "May 1, 2024" 계열
                    raw_date or ""
                )
                if _m:
                    try:
                        if _m.group(1):   # YYYY-MM-DD 계열 매칭
                            dt2 = datetime(int(_m.group(1)), int(_m.group(2)), int(_m.group(3)))
                            return dt2.strftime("%b %d, %Y")
                        else:             # "May 1, 2024" 계열 매칭
                            raw_eng = f"{_m.group(4)} {_m.group(5)} {_m.group(6)}"
                            dt2 = datetime.strptime(raw_eng, "%B %d %Y") if len(_m.group(4)) > 3 \
                                  else datetime.strptime(raw_eng, "%b %d %Y")
                            return dt2.strftime("%b %d, %Y")
                    except Exception:
                        return raw_date[:20] if raw_date else "날짜 미확인"
                else:
                    # 3차 최후 폴백: 원문 앞부분을 그대로 사용
                    return raw_date[:20].strip() if raw_date else "날짜 미확인"
        parent = parent.parent
    return "날짜 미확인"

def _fetch_detail(link: str, headers: dict):
    """상세 페이지에서 감성·임팩트를 병렬로 가져오는 내부 함수"""
    sentiment, impact = "Unknown", "Normal"
    try:
        detail_resp = get_http_session().get(link, headers=headers, timeout=5)
        if detail_resp.status_code == 200:
            detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
            sentiment_box = detail_soup.find(class_=lambda x: x and 'sentiment' in x.lower())
            if sentiment_box:
                text = sentiment_box.text.lower()
                if 'positive' in text:   sentiment = "Positive"
                elif 'negative' in text: sentiment = "Negative"
                elif 'neutral' in text:  sentiment = "Neutral"
            if 'high impact' in detail_soup.text.lower():
                impact = "High Impact"
    except Exception:
        pass
    return sentiment, impact

@st.cache_data(ttl=300, show_spinner=False)
def get_stock_titan_data(ticker: str) -> list:
    url     = f"https://www.stocktitan.net/overview/{ticker}/"
    session = get_http_session()  # 커넥션 풀 재사용
    headers = _random_headers()   # #13

    try:
        response = session.get(url, headers=headers, timeout=8)
        if response.status_code != 200:
            return []

        soup    = BeautifulSoup(response.text, 'html.parser')
        pattern = re.compile(
            rf"/news/{re.escape(ticker)}/(?!page-)[^/]+\.html$", re.IGNORECASE
        )
        link_tags = soup.find_all('a', href=pattern)

        # 1단계: 기사 목록 파싱 (번역은 여기서 하지 않음 — 2단계와 동시 실행)
        raw_list   = []
        seen_links = set()
        for link_tag in link_tags:
            title = link_tag.text.strip()
            href  = link_tag['href']
            if not title or not href:
                continue
            link = href if href.startswith('http') else "https://www.stocktitan.net" + href
            if link in seen_links:
                continue
            seen_links.add(link)

            # #4 날짜 파싱 — 부모 태그에서 날짜 요소 탐색 (별도 함수로 캡슐화)
            date_str = _extract_titan_date(link_tag)

            raw_list.append({"date": date_str, "title_en": title, "link": link})
            if len(raw_list) >= 3:
                break

        # 2단계: 상세 페이지 병렬 요청 + 제목 번역을 "동시에" 실행
        # #성능개선: 기존엔 제목 3개를 순차 번역(+매번 디스크 캐시 저장)한 뒤에야
        # 상세 페이지 병렬 요청을 시작해 완전 직렬 대기였음. 서로 의존관계가 없으므로
        # 같은 스레드풀에 번역 작업도 함께 제출해 병렬로 겹쳐 실행되게 한다.
        detail_results = {}
        with ThreadPoolExecutor(max_workers=6) as executor:
            future_to_link = {
                executor.submit(_fetch_detail, item["link"], _random_headers()): item["link"]
                for item in raw_list
            }
            translate_future = executor.submit(
                translate_texts_batch, [item["title_en"] for item in raw_list]
            )
            for future in as_completed(future_to_link):
                link = future_to_link[future]
                detail_results[link] = future.result()
            translations = translate_future.result()

        # 3단계: 결합
        news_list = []
        for item in raw_list:
            sentiment, impact = detail_results.get(item["link"], ("Unknown", "Normal"))
            title_ko = translations.get(item["title_en"], item["title_en"])
            news_list.append({**item, "title": title_ko, "sentiment": sentiment, "impact": impact})

        return news_list
    except Exception:
        return []

# ════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════
# 소셜 미디어 — StockTwits & Reddit
# ════════════════════════════════════════════════════════════════
# 간단 키워드 기반 감성 분류 — StockTwits(야후 대체 경로)·레딧에서 공통 사용
SENTIMENT_POS_KW = {"beat", "bullish", "surge", "soar", "rally", "up", "gain", "buy",
                     "upgrade", "strong", "growth", "profit", "record", "positive",
                     "moon", "squeeze", "calls", "long", "breakout", "rocket"}
SENTIMENT_NEG_KW = {"miss", "bearish", "drop", "fall", "decline", "cut", "downgrade",
                     "loss", "weak", "lawsuit", "fraud", "sell", "negative", "concern",
                     "puts", "dump", "scam", "short", "crash", "bagholders"}

# 모멘텀/소형주 관련 논의가 활발한 서브레딧 위주로 선정
REDDIT_SUBREDDITS = ["wallstreetbets", "stocks", "pennystocks", "Shortsqueeze", "smallstreetbets"]

def _ticker_actually_mentioned(text: str, ticker: str) -> bool:
    """
    레딧 검색 API가 느슨하게 매칭한 결과(제목/본문 어디에도 티커가 없는 글)를
    걸러내기 위한 필터. '$TSLA', 'TSLA', 'tsla'는 인정하고, 'TSLAX'처럼 티커가
    더 긴 단어의 일부로 등장하는 경우(오탐)는 제외한다.
    """
    if not text or not ticker:
        return False
    pattern = r'(?<![A-Za-z0-9])\$?' + re.escape(ticker) + r'(?![A-Za-z0-9])'
    return re.search(pattern, text, re.IGNORECASE) is not None


# 레딧 API 규정상 요구되는 형식: "platform:app ID:version (by /u/username)"
# ⚠️ 반드시 아래 "quant_dashboard_user"를 본인의 실제 레딧 계정명으로 바꾸세요.
# Reddit Responsible Builder Policy(App Transparency 조항)는 API 접근 주체를
# 실제와 다르게 표시하는 것을 금지합니다 — placeholder를 그대로 배포하면 안 됩니다.
REDDIT_USER_AGENT = "web:quant-dashboard-app:v1.1 (by /u/quant_dashboard_user)"


@st.cache_data(ttl=3300, show_spinner=False)  # 토큰 실제 만료(1시간)보다 살짝 짧게 캐시
def fetch_reddit_oauth_token(client_id: str, client_secret: str) -> str:
    """
    레딧 공식 OAuth2 API(application-only, client_credentials 방식)로 액세스
    토큰을 발급받습니다. 비인증 공개 JSON 엔드포인트(www.reddit.com/.../search.json)는
    데이터센터 IP를 봇으로 간주해 403/429로 차단하는 경우가 흔한 반면, 등록된 앱
    자격증명으로 인증하는 이 방식은 신원이 확인되므로 클라우드 호스팅 환경에서도
    정상적으로 동작합니다. reddit.com/prefs/apps 에서 'script' 타입 앱을 만들면
    무료로 client_id/secret을 발급받을 수 있습니다.
    """
    if not client_id or not client_secret:
        return ""
    try:
        resp = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": REDDIT_USER_AGENT},
            timeout=8,
        )
        if resp.status_code != 200:
            return ""
        return resp.json().get("access_token", "") or ""
    except Exception:
        return ""


def _reddit_children_oauth(sub: str, ticker: str, token: str) -> tuple[list, str]:
    """공식 OAuth API(oauth.reddit.com)로 서브레딧 내 검색 — IP 차단 없이 동작."""
    url = f"https://oauth.reddit.com/r/{sub}/search"
    headers = {"Authorization": f"Bearer {token}", "User-Agent": REDDIT_USER_AGENT}
    params = {"q": ticker, "restrict_sr": "1", "sort": "new", "t": "month", "limit": 8}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=8)
    except Exception as e:
        return [], f"r/{sub}(공식 API): 연결 실패 ({e})"
    if resp.status_code != 200:
        return [], f"r/{sub}(공식 API): HTTP {resp.status_code}"
    try:
        data = resp.json()
    except Exception:
        return [], f"r/{sub}(공식 API): 응답 파싱 실패"
    return ((data.get("data") or {}).get("children")) or [], ""


def _reddit_children_public(sub: str, ticker: str, session: requests.Session) -> tuple[list, str]:
    """
    비인증 공개 JSON 엔드포인트 — OAuth 자격증명이 없을 때의 fallback.
    데이터센터 IP(클라우드 호스팅)에서는 403/429로 차단되기 쉽다.
    """
    domains = ["https://www.reddit.com", "https://old.reddit.com"]
    last_error = ""
    for domain in domains:
        url = f"{domain}/r/{sub}/search.json"
        params = {"q": ticker, "restrict_sr": "1", "sort": "new", "t": "month", "limit": 8}
        try:
            resp = session.get(url, headers=_random_headers(), params=params, timeout=6)
        except Exception as e:
            last_error = f"r/{sub}: 연결 실패 ({e})"
            continue
        if resp.status_code != 200:
            last_error = f"r/{sub}: HTTP {resp.status_code}"
            continue
        try:
            data = resp.json()
        except Exception:
            last_error = f"r/{sub}: 응답 파싱 실패"
            continue
        return ((data.get("data") or {}).get("children")) or [], ""
    return [], last_error


@st.cache_data(ttl=300, show_spinner=False)
def fetch_reddit_posts(ticker: str, client_id: str = "", client_secret: str = "") -> dict:
    """
    관련 서브레딧에서 티커 언급 게시글을 수집합니다. StockTwits 외 추가 투자자
    여론 소스로, 밈주식/급등주 논의가 활발한 서브레딧(wallstreetbets, pennystocks
    등) 위주로 검색합니다.

    client_id/client_secret이 주어지면 레딧 공식 OAuth API(oauth.reddit.com)를
    우선 사용합니다 — 클라우드 호스팅(데이터센터 IP)에서도 차단되지 않는 정식
    경로입니다. 자격증명이 없거나 실패하면 비인증 공개 JSON 엔드포인트로
    자동 폴백합니다 (이 경로는 403/429로 막힐 수 있음).

    반환: {"posts": list[dict], "source": "reddit"|"", "bull": int, "bear": int,
           "error": str, "used_oauth": bool}
    """
    token = fetch_reddit_oauth_token(client_id, client_secret) if (client_id and client_secret) else ""
    used_oauth = bool(token)
    session = get_http_session()

    all_posts  = []
    seen_ids   = set()
    last_error = ""

    for sub in REDDIT_SUBREDDITS:
        children: list = []
        if token:
            children, err = _reddit_children_oauth(sub, ticker, token)
            if err:
                last_error = err
                # 토큰이 만료/무효화됐을 가능성 등 — 공개 엔드포인트로 한 번 더 시도
                children, err2 = _reddit_children_public(sub, ticker, session)
                if err2 and not children:
                    last_error = err2
        else:
            children, err = _reddit_children_public(sub, ticker, session)
            if err:
                last_error = err

        for child in children:
            d = child.get("data") or {}
            post_id = d.get("id")
            if not post_id or post_id in seen_ids:
                continue
            title    = (d.get("title") or "").strip()
            selftext = (d.get("selftext") or "")
            if not title:
                continue
            # #신규 레딧 검색이 반환하는 느슨한(유사어 포함) 매칭 결과 중
            # 실제로 제목/본문에 티커가 등장하지 않는 노이즈를 제거
            if not _ticker_actually_mentioned(f"{title} {selftext}", ticker):
                continue
            seen_ids.add(post_id)
            all_posts.append({
                "id":           post_id,
                "subreddit":    d.get("subreddit", sub),
                "title_en":     title,
                "body_en":      selftext[:400].strip(),
                "score":        d.get("score", 0) or 0,
                "num_comments": d.get("num_comments", 0) or 0,
                "created_utc":  d.get("created_utc", 0) or 0,
                "permalink":    f"https://www.reddit.com{d.get('permalink', '')}" if d.get("permalink") else "",
                "author":       d.get("author", "익명") or "익명",
            })

    if not all_posts:
        return {"posts": [], "source": "", "bull": 0, "bear": 0,
                "error": last_error or "알 수 없는 오류", "used_oauth": used_oauth}

    all_posts.sort(key=lambda p: p["created_utc"], reverse=True)
    all_posts = all_posts[:15]

    for p in all_posts:
        words   = set(p["title_en"].lower().split())
        is_bull = bool(words & SENTIMENT_POS_KW)
        is_bear = bool(words & SENTIMENT_NEG_KW)
        if is_bull and not is_bear:
            p["sentiment"] = "Bullish"
        elif is_bear and not is_bull:
            p["sentiment"] = "Bearish"
        else:
            p["sentiment"] = ""
        try:
            p["date"] = datetime.fromtimestamp(p["created_utc"]).strftime("%Y-%m-%d") if p["created_utc"] else ""
        except Exception:
            p["date"] = ""

    translations = translate_texts_batch([p["title_en"] for p in all_posts])
    for p in all_posts:
        p["title"] = translations.get(p["title_en"], p["title_en"])

    bull = sum(1 for p in all_posts if p["sentiment"] == "Bullish")
    bear = sum(1 for p in all_posts if p["sentiment"] == "Bearish")

    return {"posts": all_posts, "source": "reddit", "bull": bull, "bear": bear,
            "error": "", "used_oauth": used_oauth}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_stocktwits(ticker: str) -> dict:
    """
    StockTwits 공개 API → 실패 시 yfinance 뉴스 감성 분석으로 자동 대체.
    반환: { "bull": int, "bear": int, "messages": list[dict], "source": str }
    """
    # ── 1차: StockTwits API ─────────────────────────────────────
    url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
            "Accept": "application/json",
            "Referer": "https://stocktwits.com/",
        }
        resp = requests.get(url, headers=headers, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            messages_raw = data.get("messages", [])
            bull = sum(1 for m in messages_raw
                       if (m.get("entities", {}).get("sentiment") or {}).get("basic") == "Bullish")
            bear = sum(1 for m in messages_raw
                       if (m.get("entities", {}).get("sentiment") or {}).get("basic") == "Bearish")
            messages = []
            for m in messages_raw[:8]:
                raw_body = (m.get("body") or "").strip()
                if not raw_body:
                    continue
                body = BeautifulSoup(raw_body, "html.parser").get_text(separator=" ").strip()
                # body에 여전히 HTML 태그가 남아 있으면 건너뜀
                if not body or "<" in body:
                    continue
                sentiment = (m.get("entities", {}).get("sentiment") or {}).get("basic", "")
                likes_obj = m.get("likes", {})
                likes     = likes_obj.get("total", 0) if isinstance(likes_obj, dict) else 0
                username  = (m.get("user") or {}).get("username", "익명")
                created   = (m.get("created_at") or "")[:10]
                msg_id    = m.get("id", "")
                link = (f"https://stocktwits.com/{username}/message/{msg_id}"
                        if msg_id else f"https://stocktwits.com/{username}")
                messages.append({
                    "user": username, "body_en": body, "sentiment": sentiment,
                    "likes": likes, "date": created, "link": link,
                })
            if messages:
                # #개선 원문 보기 클릭 없이 바로 한글로 보이도록 StockTwits 본문도
                # 일괄(batch) 번역 — Yahoo fallback과 동일한 캐시/번역 로직 재사용.
                _translations = translate_texts_batch([m["body_en"] for m in messages])
                for m in messages:
                    m["body"] = _translations.get(m["body_en"], m["body_en"])
                return {"bull": bull, "bear": bear, "messages": messages, "source": "stocktwits"}
    except Exception:
        pass

    # ── 2차 fallback: yfinance 뉴스 + 키워드 감성 분류 ──────────
    POS_KW = SENTIMENT_POS_KW
    NEG_KW = SENTIMENT_NEG_KW

    try:
        raw_news = yf.Ticker(ticker).news or []
    except Exception:
        raw_news = []

    # #성능개선: 제목별로 순차 번역(+매번 디스크 저장)하던 것을 먼저 후보를 모두
    # 추린 뒤 한 번에 병렬 번역하도록 변경 (translate_texts_batch가 캐시 저장도
    # 배치당 1회로 처리).
    entries    = []
    bull, bear = 0, 0
    for item in raw_news[:10]:
        parsed  = parse_yahoo_news_item(item)
        title   = parsed["title"]
        if not title or title == "제목 없음":
            continue
        words   = set(title.lower().split())
        is_bull = bool(words & POS_KW)
        is_bear = bool(words & NEG_KW)
        if is_bull and not is_bear:
            sentiment = "Bullish"; bull += 1
        elif is_bear and not is_bull:
            sentiment = "Bearish"; bear += 1
        else:
            sentiment = ""
        entries.append({
            "user": parsed["publisher"], "title_en": title,
            "sentiment": sentiment, "likes": 0,
            "date": "", "link": parsed["link"],
        })
        if len(entries) >= 8:
            break

    translations = translate_texts_batch([e["title_en"] for e in entries])
    messages = [
        {
            "user": e["user"], "body": translations.get(e["title_en"], e["title_en"]),
            "body_en": e["title_en"], "sentiment": e["sentiment"], "likes": e["likes"],
            "date": e["date"], "link": e["link"],
        }
        for e in entries
    ]

    return {"bull": bull, "bear": bear, "messages": messages, "source": "yahoo"}


def render_social_section(ticker_input: str):
    """소셜 미디어 의견 탭 — StockTwits"""
    ui_section_header(mono_icon_badge("chat", color="var(--c-cyan)"), "소셜 미디어 투자자 의견")

    with st.spinner("StockTwits 실시간 데이터 수집 중..."):
        st_data = fetch_stocktwits(ticker_input)

    # ── StockTwits / Yahoo Finance fallback ─────────────────────
    src = st_data.get("source", "") if st_data else ""
    if src == "stocktwits":
        src_icon_key = "quote"
        src_label = "StockTwits"
        src_color = "#2ec2e8"
        src_badge_cls = "platform-badge"
    else:
        src_icon_key = "news"
        src_label = "Yahoo Finance 뉴스 감성 분석"
        src_color = "#9c7ff2"
        src_badge_cls = "platform-badge"

    st.markdown(
        f'''<div class="section-header" style="margin-top:0.3rem;">
            {mono_icon_badge(src_icon_key, color=src_color, size=26, glyph_size=13)}
            <div class="section-title" style="color:{src_color};font-size:0.88rem;">{src_label}</div>
        </div>''',
        unsafe_allow_html=True,
    )

    if src == "yahoo" and st_data and st_data.get("messages"):
        st.markdown(
            '''<div class="glass-card"><div class="status-row"><div class="status-item">
                <div class="status-dot dot-yellow"></div>
                <div class="status-text">StockTwits API 연결 불가 — Yahoo Finance 최신 뉴스 헤드라인으로 감성을 분석합니다.</div>
            </div></div></div>''',
            unsafe_allow_html=True,
        )

    if not st_data or not st_data.get("messages"):
        st.markdown(
            '''<div class="glass-card"><div class="status-row"><div class="status-item">
                <div class="status-dot dot-yellow"></div>
                <div class="status-text">소셜 데이터를 불러올 수 없습니다.</div>
            </div></div></div>''',
            unsafe_allow_html=True,
        )
    else:
        bull  = st_data.get("bull", 0)
        bear  = st_data.get("bear", 0)
        total = bull + bear
        bull_pct = round(bull / total * 100) if total else 50

        bar_label = "투자 심리 게이지" if src == "stocktwits" else "뉴스 감성 분포"
        st.markdown(f"""
        <div class="sentiment-bar-wrap">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem;">
                <span style="font-size:0.72rem;font-weight:700;color:rgba(148,163,184,0.7);letter-spacing:0.8px;text-transform:uppercase;">{bar_label}</span>
                <span style="font-size:0.72rem;color:rgba(148,163,184,0.6);">총 {total}건 &nbsp;·&nbsp; 🟢 {bull} &nbsp;🔴 {bear}</span>
            </div>
            <div class="sentiment-bar-track">
                <div class="sentiment-bar-fill" style="width:{bull_pct}%;"></div>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:rgba(148,163,184,0.5);margin-top:0.25rem;">
                <span>🟢 Bullish {bull_pct}%</span>
                <span>🔴 Bearish {100 - bull_pct}%</span>
            </div>
        </div>""", unsafe_allow_html=True)

        for msg in st_data["messages"]:
            sent = msg["sentiment"]
            if sent == "Bullish":
                card_cls = "social-card social-bull"
                badge    = '<span class="bull-badge">🟢 Bullish</span>'
            elif sent == "Bearish":
                card_cls = "social-card social-bear"
                badge    = '<span class="bear-badge">🔴 Bearish</span>'
            else:
                card_cls = "social-card"
                badge    = ""

            likes_val  = msg.get("likes", 0)
            likes_html = f'<span>❤️ {likes_val}</span>' if likes_val else ""
            user_name  = msg["user"]
            msg_date   = msg.get("date", "")
            msg_body   = msg["body"]
            msg_body_en = msg.get("body_en", "")
            msg_link   = msg["link"]

            # 날짜 표시 (yahoo fallback은 date 없음)
            date_html = f'<span>·</span><span>{msg_date}</span>' if msg_date else ""
            # yahoo fallback은 영문 원제목도 표시
            body_en_html = (f'<div style="font-size:0.75rem;color:rgba(148,163,184,0.45);margin-top:0.25rem;font-style:italic;">{msg_body_en}</div>'
                            if msg_body_en else "")
            # 출처 표시: stocktwits면 @username, yahoo면 뉴스사명
            if src == "stocktwits":
                source_html = f'<span class="platform-badge">StockTwits</span>{badge}<span>@{user_name}</span>{date_html}'
            else:
                source_html = f'<span class="{src_badge_cls}" style="background:rgba(156,127,242,0.12);color:#9c7ff2;border-color:rgba(156,127,242,0.25);">Yahoo Finance</span>{badge}<span>📰 {user_name}</span>'

            card_html = (
                f'<div class="{card_cls}">' +
                f'<div class="social-meta">{source_html}</div>' +
                f'<div class="social-body">{msg_body}</div>' +
                body_en_html +
                f'<div class="social-stats">' +
                likes_html +
                (f'<a href="{msg_link}" target="_blank" style="color:rgba(148,163,184,0.4);text-decoration:none;font-size:0.72rem;">원문 보기 →</a>' if msg_link else "") +
                f'</div></div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════
    # 레딧 — StockTwits 외 추가 투자자 여론 소스
    # ════════════════════════════════════════════════════════════
    st.markdown("<div style='margin-top:1.2rem;'></div>", unsafe_allow_html=True)
    st.markdown(
        f'''<div class="section-header" style="margin-top:0.3rem;">
            {mono_icon_badge("chat", color="#ff5700", size=26, glyph_size=13)}
            <div class="section-title" style="color:#ff5700;font-size:0.88rem;">Reddit</div>
        </div>''',
        unsafe_allow_html=True,
    )

    with st.spinner("Reddit 관련 서브레딧에서 언급 게시글 수집 중..."):
        _reddit_cid = st.session_state.get("reddit_client_id", "")
        _reddit_csec = st.session_state.get("reddit_client_secret", "")
        reddit_data = fetch_reddit_posts(ticker_input, _reddit_cid, _reddit_csec)

    if reddit_data and reddit_data.get("used_oauth"):
        st.markdown(
            '''<div style="font-size:0.7rem;color:rgba(52,211,153,0.8);margin:-0.1rem 0 0.5rem 0;">
            ✅ Reddit 공식 API(OAuth)로 조회 — 접속 차단 없이 안정적으로 동작합니다.</div>''',
            unsafe_allow_html=True,
        )

    if not reddit_data or not reddit_data.get("posts"):
        err = (reddit_data or {}).get("error", "")
        err_html = (f"<div style='font-size:0.7rem;color:rgba(148,163,184,0.5);margin-top:0.35rem;'>사유: {err}</div>"
                    if err else "")
        oauth_hint = "" if (reddit_data or {}).get("used_oauth") else (
            "<div style='font-size:0.7rem;color:rgba(148,163,184,0.5);margin-top:0.35rem;'>"
            "💡 사이드바 'Reddit API 설정'에 무료 자격증명을 등록하면 접속 차단 없이 안정적으로 조회할 수 있습니다.</div>"
        )
        st.markdown(f'''
        <div class="glass-card"><div class="status-row"><div class="status-item">
            <div class="status-dot dot-yellow"></div>
            <div class="status-text">최근 관련 게시글을 찾지 못했습니다 (검색 대상: {", ".join("r/"+s for s in REDDIT_SUBREDDITS)}). 클라우드 호스팅 환경에서는 Reddit이 접속을 차단하는 경우가 있습니다.</div>
        </div></div>{err_html}{oauth_hint}</div>
        ''', unsafe_allow_html=True)
    else:
        r_bull, r_bear = reddit_data.get("bull", 0), reddit_data.get("bear", 0)
        r_total = r_bull + r_bear
        r_bull_pct = round(r_bull / r_total * 100) if r_total else 50

        st.markdown(f"""
        <div class="sentiment-bar-wrap">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem;">
                <span style="font-size:0.72rem;font-weight:700;color:rgba(148,163,184,0.7);letter-spacing:0.8px;text-transform:uppercase;">레딧 여론 게이지</span>
                <span style="font-size:0.72rem;color:rgba(148,163,184,0.6);">총 {len(reddit_data["posts"])}건 &nbsp;·&nbsp; 🟢 {r_bull} &nbsp;🔴 {r_bear}</span>
            </div>
            <div class="sentiment-bar-track">
                <div class="sentiment-bar-fill" style="width:{r_bull_pct}%;"></div>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:rgba(148,163,184,0.5);margin-top:0.25rem;">
                <span>🟢 Bullish {r_bull_pct}%</span>
                <span>🔴 Bearish {100 - r_bull_pct}%</span>
            </div>
        </div>""", unsafe_allow_html=True)

        for p in reddit_data["posts"]:
            sent = p["sentiment"]
            if sent == "Bullish":
                card_cls = "social-card social-bull"
                badge    = '<span class="bull-badge">🟢 Bullish</span>'
            elif sent == "Bearish":
                card_cls = "social-card social-bear"
                badge    = '<span class="bear-badge">🔴 Bearish</span>'
            else:
                card_cls = "social-card"
                badge    = ""

            sub_badge  = f'<span class="platform-badge" style="background:rgba(255,87,0,0.12);color:#ff5700;border-color:rgba(255,87,0,0.28);">r/{p["subreddit"]}</span>'
            stats_html = f'<span>⬆️ {p["score"]:,}</span><span>💬 {p["num_comments"]:,}</span>'
            date_html  = f'<span>·</span><span>{p["date"]}</span>' if p.get("date") else ""
            body_en_html = (f'<div style="font-size:0.75rem;color:rgba(148,163,184,0.45);margin-top:0.25rem;font-style:italic;">{p["title_en"]}</div>')

            card_html = (
                f'<div class="{card_cls}">' +
                f'<div class="social-meta">{sub_badge}{badge}<span>u/{p["author"]}</span>{date_html}</div>' +
                f'<div class="social-body">{p["title"]}</div>' +
                body_en_html +
                f'<div class="social-stats">' +
                stats_html +
                (f'<a href="{p["permalink"]}" target="_blank" style="color:rgba(148,163,184,0.4);text-decoration:none;font-size:0.72rem;">원문 보기 →</a>' if p.get("permalink") else "") +
                f'</div></div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# #신규 AI 차트 해석 — 당일 3분봉 자동 분석 (진입 여부 / 저항선 돌파 가능성)
# ════════════════════════════════════════════════════════════════
CHART_ANALYSIS_MODEL = "gemini-2.5-flash"

CHART_ANALYSIS_SYSTEM_PROMPT = """당신은 단타/스윙 트레이더를 돕는 숙련된 기술적 분석가입니다.
사용자가 제공하는 '당일 3분봉 데이터'와 '악성매물대(저항 구간) 분석 결과'를 근거로
한국어로 짧고 명료하게 답변하세요.

#개선 기존 5개 항목(흐름 요약/모멘텀/진입 판단/저항 돌파 가능성/리스크)을
읽는 데 오래 걸린다는 피드백을 반영해 3개 소제목으로 통합하고,
항목별 분량 상한(글머리 기호 1~2줄)을 명시함.

아래 3개 소제목만 이모지와 함께 사용하고, 각 항목은 글머리 기호 1~2줄로 핵심만 쓰세요.
전체 답변은 200자를 넘기지 마세요.

1. 📊 현재 상황 — 시가 대비 등락률, 추세 방향, 저항 구간 돌파 가능성을 한 줄로
2. 🎯 진입 판단 — 매수 / 관망 중 하나를 고르고 핵심 근거 1가지만
3. ⚠️ 리스크 — 가장 중요한 리스크 요인 1가지만

숫자는 주어진 데이터 범위 안에서만 근거로 사용하고, 데이터에 없는 값은 추측하지 마세요.
마지막 줄에 반드시 "이 분석은 참고용이며 투자 조언이 아닙니다."
라는 문구만 짧게 포함하세요."""


@st.cache_data(ttl=60, show_spinner=False)
def fetch_intraday_3min(ticker: str) -> pd.DataFrame:
    """당일 1분봉을 받아 3분봉으로 리샘플링합니다. (장중에만 데이터가 채워짐)"""
    try:
        raw = yf.Ticker(ticker).history(period="1d", interval="1m")
    except Exception:
        return pd.DataFrame()
    if raw is None or raw.empty:
        return pd.DataFrame()

    # #버그수정 거래가 뜸한 종목은 period="1d" 요청에도 며칠치 데이터가 섞여
    # 반환되는 경우가 있어(휴장 중 조회 등) 3분봉이 하루가 아니라 여러 날짜에
    # 걸쳐 듬성듬성 찍히면서 차트 x축이 비정상적으로 늘어지는 문제가 있었음.
    # → 가장 최근 거래일 데이터만 남기고 나머지는 버린다.
    raw.index = pd.to_datetime(raw.index)
    latest_date = raw.index.date.max()
    raw = raw[raw.index.date == latest_date]
    if raw.empty:
        return pd.DataFrame()

    ohlc = raw.resample("3min").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    }).dropna(subset=["Open"])
    return ohlc


def build_chart_analysis_prompt(ticker: str, candles: pd.DataFrame, supply_data: dict,
                                 extra_question: str = "") -> str:
    """3분봉 요약 통계 + 최근 캔들 목록 + 저항 구간 정보를 텍스트 프롬프트로 조립."""
    c = candles.copy()
    c = calc_indicators(c)  # RSI/MA 등 재사용 (3분봉 기준으로 계산됨)

    day_open   = float(c["Open"].iloc[0])
    day_high   = float(c["High"].max())
    day_low    = float(c["Low"].min())
    last_close = float(c["Close"].iloc[-1])
    total_vol  = float(c["Volume"].sum())
    typical    = (c["High"] + c["Low"] + c["Close"]) / 3
    vwap       = float((typical * c["Volume"]).sum() / total_vol) if total_vol > 0 else last_close
    pct_open   = (last_close - day_open) / day_open * 100 if day_open else 0.0
    last_rsi   = c["RSI"].iloc[-1]
    last_rsi_s = f"{last_rsi:.1f}" if pd.notna(last_rsi) else "N/A"

    recent = c.tail(5)
    up_count = int((recent["Close"] > recent["Open"]).sum())

    lines = [f"[{ts.strftime('%H:%M')}] O:{row.Open:.2f} H:{row.High:.2f} L:{row.Low:.2f} C:{row.Close:.2f} V:{int(row.Volume):,}"
              for ts, row in c.tail(20).iterrows()]
    candle_block = "\n".join(lines)

    zones = supply_data.get("zones", []) if supply_data else []
    if zones:
        nearest = zones[0]
        resistance_block = (
            f"가장 가까운 저항 구간: ${nearest['low']:.2f} ~ ${nearest['high']:.2f} "
            f"(현재가 대비 +{nearest['gap_pct']:.1f}%, 강도: {nearest['strength']})\n"
            f"전체 저항 구간 수: {len(zones)}개"
        )
    else:
        resistance_block = "감지된 저항 구간 없음 (또는 데이터 부족)"

    prompt = f"""티커: {ticker}
당일 시가: ${day_open:.2f} / 당일 고가: ${day_high:.2f} / 당일 저가: ${day_low:.2f}
현재가(최근 3분봉 종가): ${last_close:.2f} (시가 대비 {pct_open:+.2f}%)
VWAP(거래량가중평균가): ${vwap:.2f}
누적 거래량: {int(total_vol):,}주
3분봉 RSI(14): {last_rsi_s}
최근 5개 3분봉 중 양봉 개수: {up_count}/5

[악성매물대(저항 구간) 분석 결과]
{resistance_block}

[최근 3분봉 목록 (오래된 순)]
{candle_block}
"""
    if extra_question and extra_question.strip():
        prompt += f"\n[추가 질문]\n{extra_question.strip()}\n"
    return prompt


def analyze_price_action(prompt_text: str, api_key: str) -> str:
    """조립된 텍스트 프롬프트를 Google Gemini API에 전달해 해석 텍스트를 받아온다."""
    payload = {
        "system_instruction": {"parts": [{"text": CHART_ANALYSIS_SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt_text}]}],
        "generationConfig": {
            # #버그수정 gemini-2.5-flash는 답변 생성 전 내부 "thinking" 토큰을
            # maxOutputTokens 예산에서 함께 소모함. 예산이 작으면 thinking에
            # 다 쓰고 실제 답변 텍스트는 인사말만 남긴 채 잘려버리는 문제가
            # 있었음 → thinkingBudget=0으로 비활성화하고 예산도 넉넉히 늘림.
            "maxOutputTokens": 3000,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{CHART_ANALYSIS_MODEL}:generateContent?key={api_key}"
    )
    resp = requests.post(url, json=payload, timeout=60)
    if resp.status_code != 200:
        try:
            err_msg = resp.json().get("error", {}).get("message", resp.text)
        except Exception:
            err_msg = resp.text
        raise RuntimeError(f"API 오류 ({resp.status_code}): {err_msg}")

    data = resp.json()
    candidates = data.get("candidates", [])
    if not candidates:
        block_reason = data.get("promptFeedback", {}).get("blockReason", "")
        if block_reason:
            raise RuntimeError(f"모델이 응답을 거부했습니다 (사유: {block_reason})")
        raise RuntimeError("모델로부터 응답을 받지 못했습니다.")

    cand = candidates[0]
    parts = cand.get("content", {}).get("parts", [])
    texts = [p.get("text", "") for p in parts if "text" in p]
    result = "\n".join(texts).strip()

    finish_reason = cand.get("finishReason", "")
    if finish_reason == "MAX_TOKENS" and len(result) < 100:
        raise RuntimeError(
            "응답이 토큰 한도 내에서 완성되지 못했습니다. 다시 시도해보시거나, "
            "그래도 반복되면 maxOutputTokens 값을 더 늘려주세요."
        )
    return result


def render_chart_interpretation(ticker: str, hist_daily: pd.DataFrame, current_price: float):
    """AI 차트 해석 탭 — 당일 3분봉을 자동으로 받아 진입 여부·저항선 돌파 가능성을 분석."""
    ui_section_header(mono_icon_badge("camera", color="var(--c-cyan)"), "AI 차트 해석 (당일 3분봉 기준)")

    api_key = st.session_state.get("gemini_api_key", "")
    if not api_key:
        st.markdown(
            '''<div class="glass-card"><div class="status-row"><div class="status-item">
                <div class="status-dot dot-yellow"></div>
                <div class="status-text">AI 차트 해석을 사용하려면 사이드바 하단 "🤖 AI 차트 해석 설정"에서
                Google AI(Gemini) API 키를 먼저 입력해주세요. (aistudio.google.com/apikey 에서 무료 발급)</div>
            </div></div></div>''',
            unsafe_allow_html=True,
        )
        return

    with st.spinner("당일 3분봉 데이터를 불러오는 중..."):
        candles = fetch_intraday_3min(ticker)

    if candles.empty or len(candles) < 3:
        st.markdown(
            '''<div class="glass-card"><div class="status-row"><div class="status-item">
                <div class="status-dot dot-blue"></div>
                <div class="status-text">당일 장중(3분봉) 데이터를 가져올 수 없습니다.
                장 마감/휴장 중이거나 데이터 제공이 제한된 종목일 수 있습니다.</div>
            </div></div></div>''',
            unsafe_allow_html=True,
        )
        return

    # #개선 요청: 차트 해석 탭에서는 그래프를 표시하지 않음 (텍스트 분석만 제공)
    # 좌측 컬럼에서 이미 계산된 악성매물대와 동일 기준·파라미터로 저항 구간을 다시 산출
    supply_data = calc_supply_zones(
        hist_daily, current_price,
        n_bins=supply_n_bins, lookback_days=supply_lookback_days,
        heavy_mult=supply_heavy_mult, max_zones=supply_max_zones,
        max_zone_width_pct=supply_max_width_pct,
    )

    extra_question = st.text_input(
        "추가로 궁금한 점이 있다면 적어주세요 (선택)",
        key="chart_ai_question",
        placeholder="예: 손절선은 어디로 잡는 게 좋을까?",
    )

    last_ts = candles.index[-1]
    cache_key = (ticker, str(last_ts), extra_question)

    run_clicked = st.button("🔍 지금 진입 여부 분석하기", use_container_width=True, key="chart_analysis_run_btn")

    if run_clicked or st.session_state.get("chart_analysis_cache_key") != cache_key:
        if run_clicked:
            with st.spinner("Gemini가 당일 흐름과 저항 구간을 분석하는 중..."):
                try:
                    prompt_text = build_chart_analysis_prompt(ticker, candles, supply_data, extra_question)
                    result_text = analyze_price_action(prompt_text, api_key)
                    st.session_state["chart_analysis_result"] = result_text
                    st.session_state["chart_analysis_error"] = None
                    st.session_state["chart_analysis_cache_key"] = cache_key
                except Exception as e:
                    st.session_state["chart_analysis_result"] = None
                    st.session_state["chart_analysis_error"] = str(e)
                    st.session_state["chart_analysis_cache_key"] = cache_key

    error_msg = st.session_state.get("chart_analysis_error")
    if error_msg and st.session_state.get("chart_analysis_cache_key") == cache_key:
        st.markdown(
            f'''<div class="glass-card"><div class="status-row"><div class="status-item">
                <div class="status-dot dot-red"></div>
                <div class="status-text">분석 중 오류가 발생했습니다: {error_msg}</div>
            </div></div></div>''',
            unsafe_allow_html=True,
        )
    elif st.session_state.get("chart_analysis_result") and st.session_state.get("chart_analysis_cache_key") == cache_key:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown(st.session_state["chart_analysis_result"])
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.caption("버튼을 누르면 최신 3분봉 데이터를 기준으로 분석합니다.")


# ════════════════════════════════════════════════════════════════
# CSS — 다크/라이트 모드 동적 주입
# ════════════════════════════════════════════════════════════════
def inject_css(dark: bool = True):
    if dark:
        bg_main      = "linear-gradient(180deg, #232326, #232326)"
        bg_sidebar   = "linear-gradient(180deg, #0c0c0e 0%, #131315 100%)"
        glass_bg     = "rgba(255,255,255,0.04)"
        glass_border = "rgba(255,255,255,0.09)"
        metric_bg    = "rgba(255,255,255,0.045)"
        metric_bdr   = "rgba(255,255,255,0.1)"
        tab_bg       = "rgba(255,255,255,0.06)"
        tab_bdr      = "rgba(255,255,255,0.08)"
        status_bg    = "rgba(255,255,255,0.035)"
        status_bdr   = "rgba(255,255,255,0.08)"
        news_bg      = "rgba(255,255,255,0.04)"
        news_bdr     = "rgba(255,255,255,0.09)"
        social_bg    = "rgba(255,255,255,0.04)"
        social_bdr   = "rgba(255,255,255,0.09)"
        sent_wrap_bg = "rgba(255,255,255,0.06)"
        sent_wrap_bdr= "rgba(255,255,255,0.08)"
        sent_track   = "rgba(255,255,255,0.08)"
        hr_color     = "rgba(255,255,255,0.07)"
        text_primary = "#f1f5f9"
        text_sec     = "#e2e8f0"
        # #개선 요청: 배경색과 비슷하거나 투명도(알파)만으로 흐릿하게 표현하던
        # 보조 텍스트를 전부 불투명(alpha=1) + 뚜렷이 구분되는 색상으로 교체.
        # - text_muted:  스틸 블루 계열(솔리드) — 메타 정보/라벨
        # - text_dimmed: 웜 골드 계열(솔리드) — 원문/부가 설명 (muted와 아예 다른 색상군)
        text_muted   = "#8fc4e8"
        text_dimmed  = "#e0b374"
        text_status  = "#cbd5e1"
        metric_label = "#8fc4e8"
        sidebar_input_bg  = "rgba(255,255,255,0.92)"
        sidebar_input_bdr = "rgba(139,92,246,0.4)"
        sidebar_input_clr = "#000000"
        textarea_bg  = "rgba(255,255,255,0.04)"
        plotly_tmpl  = "plotly_dark"
        sector_name_clr  = "#f8fafc"
        sector_ticker_clr= "#8fc4e8"
        social_selftext_bdr = "rgba(255,255,255,0.1)"
        social_selftext_clr = "#e0b374"

        # ── #디자인개선(위젯 스타일 전면 교체): iOS 잠금화면 위젯 참고
        # 이미지처럼 배경은 무광 플랫 그레이 한 장으로 통일하고, 카드
        # 자체(순검정 + 네온 컬러 블록)가 시각적 주인공이 되도록 한다.
        # 기존의 애니메이션 메시 그라디언트 + 반짝이는 파티클 오버레이는
        # 이 스타일과 상충되므로(글로시 → 플랫) 다크 모드에서도 비활성화.
        mesh_bg_layers = ""
        mesh_bg_size  = "100% 100%"
        mesh_bg_anim  = "none"
        mesh_keyframes_css = ""
        particle_overlay_css = ""
    else:
        bg_main      = "linear-gradient(135deg, #f0f4ff 0%, #e8eeff 40%, #f0f7ff 100%)"
        bg_sidebar   = "linear-gradient(180deg, #eef2ff 0%, #e8f0fe 100%)"
        glass_bg     = "rgba(255,255,255,0.72)"
        glass_border = "rgba(90,91,214,0.15)"
        metric_bg    = "rgba(255,255,255,0.8)"
        metric_bdr   = "rgba(90,91,214,0.15)"
        tab_bg       = "rgba(255,255,255,0.7)"
        tab_bdr      = "rgba(90,91,214,0.15)"
        status_bg    = "rgba(255,255,255,0.7)"
        status_bdr   = "rgba(90,91,214,0.12)"
        news_bg      = "rgba(255,255,255,0.72)"
        news_bdr     = "rgba(90,91,214,0.15)"
        social_bg    = "rgba(255,255,255,0.72)"
        social_bdr   = "rgba(90,91,214,0.15)"
        sent_wrap_bg = "rgba(255,255,255,0.8)"
        sent_wrap_bdr= "rgba(90,91,214,0.12)"
        sent_track   = "rgba(90,91,214,0.1)"
        hr_color     = "rgba(90,91,214,0.12)"
        text_primary = "#1e1b4b"
        text_sec     = "#312e81"
        # #개선 요청: 명암(밝기)만 다른 회색 대신, 다크모드와 짝을 이루는
        # 뚜렷이 구분되는 색상군(짙은 스틸 블루 / 짙은 웜 브라운)의 솔리드 컬러로 교체.
        text_muted   = "#1d5c85"
        text_dimmed  = "#8a5a1e"
        text_status  = "#374151"
        metric_label = "#1d5c85"
        sidebar_input_bg  = "rgba(255,255,255,0.9)"
        sidebar_input_bdr = "rgba(90,91,214,0.4)"
        sidebar_input_clr = "#000000"
        textarea_bg  = "rgba(255,255,255,0.9)"
        plotly_tmpl  = "plotly_white"
        sector_name_clr  = "#1e1b4b"
        sector_ticker_clr= "#1d5c85"
        social_selftext_bdr = "rgba(90,91,214,0.2)"
        social_selftext_clr = "#8a5a1e"

        # 라이트 모드는 정적 배경 유지 (다이나믹 메시/파티클은 다크모드 전용)
        mesh_bg_layers      = ""
        mesh_bg_size        = "100% 100%"
        mesh_bg_anim        = "none"
        mesh_keyframes_css  = ""
        particle_overlay_css = ""

    st.session_state["_plotly_template"] = plotly_tmpl

    mesh_bg_comma = "," if mesh_bg_layers else ""
    light_mode_overrides = "" if dark else LIGHT_MODE_OVERRIDE_CSS

    # #개선 거대 인라인 CSS f-string(옛 720여 줄)을 styles/theme.css.tpl로 분리.
    # 색상/애니메이션 값만 파이썬에서 계산해 Template로 치환하고,
    # 실제 CSS 구조/레이아웃 규칙은 별도 파일에서 관리한다.
    with open(CSS_TPL_PATH, "r", encoding="utf-8") as _f:
        _css_template = _f.read()

    css = Template(_css_template).substitute(
        bg_main=bg_main, bg_sidebar=bg_sidebar, glass_bg=glass_bg, glass_border=glass_border,
        metric_bg=metric_bg, metric_bdr=metric_bdr, tab_bg=tab_bg, tab_bdr=tab_bdr,
        status_bg=status_bg, status_bdr=status_bdr, news_bg=news_bg, news_bdr=news_bdr,
        social_bg=social_bg, social_bdr=social_bdr, sent_wrap_bg=sent_wrap_bg, sent_wrap_bdr=sent_wrap_bdr,
        sent_track=sent_track, hr_color=hr_color, text_primary=text_primary, text_sec=text_sec,
        text_muted=text_muted, text_dimmed=text_dimmed, text_status=text_status, metric_label=metric_label,
        sidebar_input_bg=sidebar_input_bg, sidebar_input_bdr=sidebar_input_bdr, sidebar_input_clr=sidebar_input_clr,
        textarea_bg=textarea_bg, sector_name_clr=sector_name_clr, sector_ticker_clr=sector_ticker_clr,
        social_selftext_bdr=social_selftext_bdr, social_selftext_clr=social_selftext_clr,
        mesh_bg_layers=mesh_bg_layers, mesh_bg_comma=mesh_bg_comma, mesh_bg_size=mesh_bg_size,
        mesh_bg_anim=mesh_bg_anim, mesh_keyframes_css=mesh_keyframes_css, particle_overlay_css=particle_overlay_css,
        light_mode_overrides=light_mode_overrides,
    )
    # #개선 세로가 좁은 직사각형 카드 + 10개 카드를 한 섹션처럼 보이게 함.
    # metric-grid / metric-card의 기본 레이아웃은 styles/theme.css.tpl에 정의돼
    # 있어 여기서 직접 수정할 수 없으므로, 로드된 CSS 뒤에 더 높은 우선순위의
    # 오버라이드를 추가하는 방식으로 처리함(!important).
    # - 정사각형(aspect-ratio:1/1) 대신 세로가 짧은 2열 직사각형 카드로 복귀.
    # - 카드 내부는 기존처럼 좌측 정렬(라벨/값/델타 세로 배치).
    # - 상단 요약 5장 + 기술분석 5장이 이제 render_technical_analysis()에서
    #   하나의 metric-grid로 합쳐져 렌더링되므로, 별도 그리드 간 여백(margin-top:
    #   -0.25rem 등)에 의존하지 않고 gap만으로 균일한 간격을 유지한다.
    narrow_metric_cards_css = """
    .metric-grid {
        grid-template-columns: repeat(2, 1fr) !important;
        gap: 0.5rem !important;
    }
    /* 상단 요약+기술분석 카드 전용 12열 그리드 — 카드마다 grid-column: span N을
       지정해 3개/2개/4개씩 원하는 개수로 한 줄에 배치할 수 있도록 함.
       (다른 섹션의 .metric-grid, 예: 악성매물대 카드는 기존 2열 그대로 유지) */
    .metric-grid.metric-grid-12 {
        grid-template-columns: repeat(12, 1fr) !important;
    }
    .metric-card {
        aspect-ratio: auto !important;
        min-height: 0 !important;
        padding: 0.55rem 0.75rem !important;
        display: flex !important;
        flex-direction: column !important;
        justify-content: center !important;
        text-align: left !important;
    }
    .metric-card .metric-label {
        font-size: 0.68rem !important;
        margin-bottom: 0.15rem !important;
    }
    .metric-card .metric-value {
        font-size: 1.05rem !important;
        line-height: 1.15 !important;
    }
    .metric-card .metric-delta {
        font-size: 0.65rem !important;
        margin-top: 0.15rem !important;
    }
    """

    # #개선 요청: "글씨색이 배경색과 비슷하거나 명암(투명도) 조절로만 구분되지
    # 않도록, 항상 뚜렷이 다른 불투명한 색을 쓸 것" — 코드 곳곳에 인라인
    # style="color:rgba(148,163,184, 0.4~0.75)" 식으로 하드코딩된 반투명 회색
    # 텍스트(뉴스/소셜/매물대/스코어 카드 등)가 남아있어, 기존엔 라이트 모드에서만
    # 속성 선택자로 보정하고 다크 모드는 그대로 방치돼 있었음.
    # → 다크/라이트 모드 모두에 대해 위 패턴들을 전부 "완전 불투명 + 뚜렷이
    #   구분되는 색"으로 강제 치환한다 (이 <style> 블록은 테마 CSS보다 뒤에
    #   렌더링되므로 !important 없이도 우선 적용되지만, 안전하게 !important 유지).
    unified_contrast_css = f"""
    [style*="color:rgba(148,163,184"], [style*="color: rgba(148,163,184"] {{
        color: var(--card-ink-muted) !important;
    }}
    [style*="color:rgba(255,255,255"], [style*="color: rgba(255,255,255"] {{
        color: {"#ffffff" if dark else "#1e1b4b"} !important;
    }}
    [style*="color:rgba(254,202,202"], [style*="color: rgba(254,202,202"] {{
        color: {"#fecaca" if dark else "#7f1d1d"} !important;
    }}
    """

    st.markdown(f"\n{css}\n<style>{narrow_metric_cards_css}{unified_contrast_css}</style>\n", unsafe_allow_html=True)

inject_css(st.session_state.get("dark_mode", False))

# ════════════════════════════════════════════════════════════════
# 헤더 배너
# ════════════════════════════════════════════════════════════════
st.markdown(f"""
<div class="app-header">
    <h1>🚀 급등주 실시간 검증기 V3</h1>
    <p>야후 파이낸스 · 스톡타이탄 Rhea-AI · 기술적 지표 통합 분석 &nbsp;|&nbsp; 환율 ₩{fetch_usd_to_krw():,.0f} (실시간)</p>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# 즐겨찾기 일괄 스캔 결과 표시
# ════════════════════════════════════════════════════════════════
if st.session_state.scan_results:
    alert_tickers = [r for r in st.session_state.scan_results if r["🔔신호"] != "—"]
    st.markdown(f"""
    <div class="scan-header">
        <span class="scan-title">⭐ 즐겨찾기 일괄 스캔 결과 &nbsp;·&nbsp; {len(st.session_state.scan_results)}개 종목</span>
        {'<span style="color:#fbbf24;font-size:0.82rem;font-weight:600;">🔔 신호 ' + str(len(alert_tickers)) + '건 감지</span>' if alert_tickers else ''}
    </div>
    """, unsafe_allow_html=True)

    scan_df = pd.DataFrame(st.session_state.scan_results)
    def highlight_signal(row):
        if row["🔔신호"] != "—":
            return ["background-color: rgba(52,211,153,0.08); color: #34d399"] * len(row)
        return [""] * len(row)
    st.dataframe(scan_df.style.apply(highlight_signal, axis=1), use_container_width=True, hide_index=True)

    if alert_tickers:
        chips = "".join([f'<span class="signal-chip">{r["티커"]} {r["🔔신호"]}</span>' for r in alert_tickers])
        st.markdown(f"""
        <div class="alert-banner">
            <div class="alert-icon">🔔</div>
            <div>
                <div class="alert-title">급등 신호 감지</div>
                <div class="alert-signals">{chips}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    if st.button("✕ 스캔 결과 닫기", key="close_scan"):
        st.session_state.scan_results = []
        st.rerun()
    st.markdown("---")

# ════════════════════════════════════════════════════════════════
# 사이드바 — 티커 입력 및 파라미터
# ════════════════════════════════════════════════════════════════
st.sidebar.header("🔍 주식 분석 설정")

# ── 다크/라이트 모드 토글 ────────────────────────────────────────
_is_dark = st.session_state.get("dark_mode", False)
_toggle_label = "☀️ 라이트 모드로 전환" if _is_dark else "🌙 다크 모드로 전환"
if st.sidebar.button(_toggle_label, use_container_width=True):
    st.session_state["dark_mode"] = not _is_dark
    st.rerun()
st.sidebar.markdown("")

# ── 섹터 히트맵 / 급등주 검색기 토글 (스크롤 없이 바로 보이도록 상단 배치) ──
tcol1, tcol2 = st.sidebar.columns(2)
with tcol1:
    st.checkbox(
        "📊 섹터 히트맵", key="show_heatmap",
        help="11개 섹터 ETF의 당일/1주/1개월 성과를 히트맵으로 표시합니다"
    )
with tcol2:
    st.checkbox(
        "🚀 급등주 검색기", key="show_screener",
        help="Yahoo Finance 실시간 스크리너로 조건에 맞는 급등 종목을 찾습니다"
    )
st.sidebar.markdown("---")

# ── 티커 입력 + 검색 (엔터키로도 실행 가능하도록 form으로 묶음) ──
with st.sidebar.form(key="ticker_search_form"):
    ticker_input = st.text_input(
        "티커명을 입력하세요 (예: NVDA, AAPL)",
        value=st.session_state.selected_ticker
    ).upper()

    col_btn, col_star = st.columns([3, 1])
    with col_btn:
        search_button = st.form_submit_button("실시간 정밀 검증 시작", use_container_width=True)
    with col_star:
        is_fav = ticker_input in st.session_state.favorites
        fav_button_clicked = st.form_submit_button(
            "★" if is_fav else "☆", use_container_width=True, help="즐겨찾기 추가/제거"
        )

if fav_button_clicked:
    if is_fav:
        st.session_state.favorites.remove(ticker_input)
    else:
        if ticker_input and ticker_input not in st.session_state.favorites:
            st.session_state.favorites.append(ticker_input)
    save_favorites(st.session_state.favorites)
    st.rerun()

# ── 즐겨찾기 목록 ────────────────────────────────────────────────
if st.session_state.favorites:
    st.sidebar.markdown("---")
    st.sidebar.markdown("**⭐ 즐겨찾기**")
    fav_count = len(st.session_state.favorites)
    for idx, fav in enumerate(st.session_state.favorites):
        fav_col, up_col, down_col, del_col = st.sidebar.columns([3, 1, 1, 1])
        with fav_col:
            with st.container(key=f"fav_ticker_{idx}"):
                if st.button(fav, key=f"fav_{fav}", use_container_width=True):
                    st.session_state.selected_ticker = fav
                    st.rerun()
        with up_col:
            with st.container(key=f"fav_action_up_{idx}"):
                if st.button("▲", key=f"up_{fav}", use_container_width=True,
                             help="위로 이동", disabled=(idx == 0)):
                    favs = st.session_state.favorites
                    favs[idx - 1], favs[idx] = favs[idx], favs[idx - 1]
                    save_favorites(favs)
                    st.rerun()
        with down_col:
            with st.container(key=f"fav_action_down_{idx}"):
                if st.button("▼", key=f"down_{fav}", use_container_width=True,
                             help="아래로 이동", disabled=(idx == fav_count - 1)):
                    favs = st.session_state.favorites
                    favs[idx + 1], favs[idx] = favs[idx], favs[idx + 1]
                    save_favorites(favs)
                    st.rerun()
        with del_col:
            with st.container(key=f"fav_action_del_{idx}"):
                if st.button("✕", key=f"del_{fav}", use_container_width=True, help=f"{fav} 삭제"):
                    st.session_state.favorites.remove(fav)
                    save_favorites(st.session_state.favorites)
                    st.rerun()

    # #5 즐겨찾기 일괄 스캔 — ThreadPoolExecutor로 병렬화
    st.sidebar.markdown("")
    if st.sidebar.button("🔍 즐겨찾기 전체 스캔", use_container_width=True,
                         help="즐겨찾기 종목을 한 번에 분석합니다"):
        scan_data  = []
        total      = len(st.session_state.favorites)
        progress   = st.sidebar.progress(0, text="스캔 중...")
        done_count = [0]   # 리스트로 감싸 클로저에서 변경 가능하게
        usd_krw    = fetch_usd_to_krw()   # 급등주 검색기와 동일한 거래대금 환산 기준

        def _scan_one(fav_ticker: str) -> dict:
            try:
                fav_hist = fetch_history(fav_ticker)
                if not fav_hist.empty and len(fav_hist) >= 2:
                    fav_hist   = calc_indicators(fav_hist.dropna())
                    t          = fav_hist.iloc[-1]
                    y          = fav_hist.iloc[-2]
                    pct        = (t['Close'] - y['Close']) / y['Close'] * 100
                    # #8 거래량 20일 MA 대비 비율
                    # #버그수정: 데이터 부족(20일 미만)으로 VOL_MA20이 NaN일 때 1로 나누면
                    # 거래량 수십만%가 되어 "🔥거래량" 신호가 오탐지됨 → 중립(100%) 처리.
                    vol_ma20   = t['VOL_MA20'] if pd.notna(t['VOL_MA20']) and t['VOL_MA20'] > 0 else t['Volume']
                    vol_r      = (t['Volume'] / vol_ma20) * 100 if vol_ma20 else 0
                    vol_ratio  = (t['Volume'] / y['Volume'] * 100) if y['Volume'] else 0
                    rsi        = t['RSI']
                    macd_cross = t['MACD'] > t['MACD_SIG'] and y['MACD'] <= y['MACD_SIG']
                    gap_up_pct = (t['Open'] - y['Close']) / y['Close'] * 100
                    trading_value_eok = round((t['Close'] * t['Volume'] * usd_krw) / 100_000_000, 1)

                    signals = []
                    if vol_r  >= 200:  signals.append("🔥거래량")   # MA20 대비 200%+
                    if macd_cross:     signals.append("⚡MACD")
                    if rsi    <= 35:   signals.append("📉과매도")
                    if t['Close'] > t['MA120'] and y['Close'] <= y['MA120']:
                                       signals.append("🚀120일선")
                    if gap_up_pct >= 5:
                                       signals.append("⬆️갭업")     # 시초가 전일종가 대비 5%+
                    alert = " ".join(signals) if signals else "—"

                    # 급등주 검색기와 동일한 종합점수 산출 기준 적용
                    score = calc_screener_score({
                        "pct_change":        pct,
                        "vol_ma20_ratio":    vol_r,
                        "trading_value_eok": trading_value_eok,
                        "vol_ratio":         vol_ratio,
                        "rsi":               round(float(rsi), 1) if pd.notna(rsi) else None,
                    })

                    return {
                        "티커":      fav_ticker,
                        "현재가":    f"${t['Close']:.2f}",
                        "등락(%)":   f"{pct:+.2f}%",
                        "종합점수":  f"{score:.1f}",
                        "거래량(MA비%)": f"{vol_r:.0f}%",
                        "RSI":       f"{rsi:.1f}",
                        "🔔신호":    alert,
                    }
            except Exception:
                pass
            return {"티커": fav_ticker, "현재가": "오류", "등락(%)": "-",
                    "종합점수": "-",
                    "거래량(MA비%)": "-", "RSI": "-", "🔔신호": "-"}

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(_scan_one, t): t for t in st.session_state.favorites}
            for future in as_completed(futures):
                scan_data.append(future.result())
                done_count[0] += 1
                progress.progress(done_count[0] / total, text=f"스캔 중... ({done_count[0]}/{total})")

        progress.empty()
        # 티커 순서 유지
        order = {t: i for i, t in enumerate(st.session_state.favorites)}
        scan_data.sort(key=lambda r: order.get(r["티커"], 999))
        st.session_state.scan_results = scan_data
        st.rerun()
else:
    st.sidebar.markdown("---")
    st.sidebar.caption("☆ 버튼으로 즐겨찾기를 추가하세요")

# ── 즐겨찾기 메모 사이드바 표시 ─────────────────────────────────
if st.session_state.memos:
    st.sidebar.markdown("---")
    st.sidebar.markdown("**📝 저장된 메모**")
    for t_key, memo_val in st.session_state.memos.items():
        if memo_val.strip():
            st.sidebar.caption(f"**{t_key}:** {memo_val[:40]}{'...' if len(memo_val)>40 else ''}")


# ════════════════════════════════════════════════════════════════
# #신규 AI 차트 해석 — Claude Vision API 키 설정
# 캡처한 차트 이미지를 업로드하면 Claude가 추세/지지·저항/패턴을
# 해석해주는 기능. Anthropic API 키가 필요하므로 사이드바에서
# 안전하게(비밀번호 입력창) 받아 세션에만 보관한다.
# ════════════════════════════════════════════════════════════════
st.sidebar.markdown("---")
with st.sidebar.expander("🤖 AI 차트 해석 설정", expanded=False):
    _secret_key = ""
    try:
        _secret_key = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        _secret_key = ""
    if _secret_key:
        st.session_state["gemini_api_key"] = _secret_key
        st.caption("✅ API 키가 앱 설정(secrets)에 등록되어 있습니다.")
    else:
        st.text_input(
            "Google AI (Gemini) API 키",
            type="password",
            key="gemini_api_key",
            help="aistudio.google.com/apikey 에서 무료로 발급받은 API 키를 입력하세요. "
                 "입력한 키는 저장되지 않고 현재 세션에서만 사용됩니다.",
            placeholder="AIza...",
        )
        st.caption("🔒 이 브라우저 세션에서만 사용되며 서버에 저장되지 않습니다. "
                   "무료 티어(분당 요청 제한)로 충분히 사용 가능합니다.")

# ════════════════════════════════════════════════════════════════
# #신규 레딧 공식 API(OAuth) 자격증명 설정 — 클라우드 IP 차단 우회
# 비인증 공개 JSON 엔드포인트(www.reddit.com/.../search.json)는 데이터센터 IP를
# 봇으로 간주해 403/429로 차단하는 경우가 흔함. 여기에 무료로 발급받은
# client_id/secret을 입력하면 레딧 공식 OAuth API(oauth.reddit.com)를 우선
# 사용해 이 문제를 근본적으로 회피한다. 입력하지 않으면 기존처럼 비인증
# 공개 엔드포인트로 자동 폴백.
#
# ⚠️ Reddit Responsible Builder Policy 준수 필요:
# https://support.reddithelp.com/hc/en-us/articles/42728983564564
# - 개인/비상업적 이용 목적 범위 내에서만 사용 (상업화·유료 서비스 전환 시
#   별도의 서면 승인이 Reddit으로부터 필요)
# - 수집한 데이터를 AI/ML 모델 학습에 사용하거나 재판매/재라이선싱 금지
# - REDDIT_USER_AGENT를 실제 계정명으로 바꿔 접근 주체를 투명하게 표시할 것
# - API 호출 한도를 초과하거나 우회하지 말 것 (현재 구현은 5분 캐시 +
#   서브레딧당 요청 1회로 낮은 호출량 유지)
# ════════════════════════════════════════════════════════════════
st.sidebar.markdown("---")
with st.sidebar.expander("🧵 Reddit API 설정 (선택사항)", expanded=False):
    _reddit_id_secret, _reddit_secret_secret = "", ""
    try:
        _reddit_id_secret     = st.secrets.get("REDDIT_CLIENT_ID", "")
        _reddit_secret_secret = st.secrets.get("REDDIT_CLIENT_SECRET", "")
    except Exception:
        pass

    if _reddit_id_secret and _reddit_secret_secret:
        st.session_state["reddit_client_id"]     = _reddit_id_secret
        st.session_state["reddit_client_secret"] = _reddit_secret_secret
        st.caption("✅ Reddit API 자격증명이 앱 설정(secrets)에 등록되어 있습니다.")
    else:
        st.text_input(
            "Client ID", key="reddit_client_id",
            help="reddit.com/prefs/apps 에서 'script' 타입 앱을 만들면 무료로 발급받습니다. "
                 "앱 이름 아래 표시되는 짧은 문자열입니다.",
            placeholder="예: aBcD1234efGh",
        )
        st.text_input(
            "Client Secret", type="password", key="reddit_client_secret",
            placeholder="secret 항목의 값",
        )
        st.caption(
            "🔒 입력한 값은 저장되지 않고 현재 세션에서만 사용됩니다. "
            "비워두면 비인증 공개 엔드포인트로 자동 동작하며, 지금은 이 방식만으로 "
            "충분히 사용 가능합니다. 참고로 레딧이 최근 정책을 강화해 신규 Data API "
            "앱 승인은 주로 모더레이션(서브레딧 운영) 용도에 한정하고 있어, 개인용 "
            "조회 목적으로는 승인이 안 날 수 있습니다 — 급하게 발급받으실 필요는 없습니다."
        )

# ════════════════════════════════════════════════════════════════
# #개선 악성매물대(저항선) 분석 파라미터 — 사이드바에서 조절 가능
# 기존엔 calc_supply_zones()의 n_bins/lookback_days/heavy_mult가
# 코드에 고정값으로 박혀 있어 종목별 민감도 조절이 불가능했음.
# 슬라이더로 노출해 급등주(변동성 큼)와 대형주(변동성 작음)에
# 서로 다른 민감도를 적용해볼 수 있도록 함.
# ════════════════════════════════════════════════════════════════
st.sidebar.markdown("---")
with st.sidebar.expander("⚙️ 매물대 분석 설정", expanded=False):
    supply_lookback_days = st.slider(
        "분석 기간 (거래일)", min_value=60, max_value=504, value=252, step=6,
        help="최근 몇 거래일의 거래량을 매물대 계산에 반영할지 설정합니다. "
             "값이 클수록 장기 매물대까지 포착하지만 최근 흐름 반영은 약해집니다."
    )
    supply_n_bins = st.slider(
        "가격 구간 개수 (Bin)", min_value=15, max_value=80, value=40, step=5,
        help="가격 범위를 몇 개 구간으로 나눌지 설정합니다. 값이 클수록 "
             "매물대가 더 촘촘하게(좁은 가격대로) 표시됩니다."
    )
    supply_heavy_mult = st.slider(
        "매물대 판정 민감도 (평균 대비 배수)", min_value=1.0, max_value=2.5, value=1.3, step=0.1,
        help="평균 거래량 대비 몇 배 이상 몰려 있어야 매물대로 판정할지 설정합니다. "
             "값이 작을수록 더 많은 구간이 매물대로 잡힙니다."
    )
    supply_max_zones = st.slider(
        "표시할 매물대 개수", min_value=2, max_value=8, value=4, step=1,
    )
    supply_max_width_pct = st.slider(
        "매물대 최대 폭 (현재가 대비 %)", min_value=1.0, max_value=10.0, value=3.0, step=0.5,
        help="하나의 매물대가 가질 수 있는 최대 가격 폭을 현재가 대비 %로 제한합니다. "
             "거래량이 넓은 가격대에 걸쳐 몰린 종목은 이 값을 넘는 매물대를 여러 개의 "
             "좁은 매물대로 자동 분할해서 보여줍니다. 값이 작을수록 더 잘게 쪼개집니다."
    )

# ════════════════════════════════════════════════════════════════
# 렌더링 함수 — 상단 주요 지표 요약
# ════════════════════════════════════════════════════════════════
def build_top_summary_cards_html(today_data, yesterday_data, df_calculated, vol_ma20_ratio, score=None) -> tuple:
    """상단 주요 지표 카드의 HTML을 (앞쪽 그룹, 뒤쪽 그룹) 튜플로 반환.

    render_technical_analysis()의 metric-grid 맨 앞/맨 뒤에 각각 끼워 넣어,
    요청된 카드 순서(현재가 → 거래량(MA20대비) → 당일거래량 → 시가총액 →
    유통주식수 → 52주 최고가 → 52주 최저가)를 만들고, 순서 지정 대상이 아닌
    RSI/종합점수는 맨 뒤로 보낸다."""
    price_chg   = ((today_data['Close'] - yesterday_data['Close']) / yesterday_data['Close']) * 100
    current_rsi = df_calculated['RSI'].iloc[-1]
    rsi_available = pd.notna(current_rsi)
    # #버그수정: 상장 14일 미만 종목은 RSI가 NaN → 예전엔 "보통"으로 잘못 표시되고
    # {:.1f} 포맷팅 시 "nan"이 그대로 찍혔음. 데이터 부족 상태를 명시적으로 분기.
    rsi_status  = ("과매수" if current_rsi >= 70 else ("과매도" if current_rsi <= 30 else "보통")) if rsi_available else "데이터 부족"
    score_label = None
    if score is not None:
        score_label = "강세" if score >= 70 else ("보통" if score >= 40 else "약세")

    pct_color = "delta-up" if price_chg >= 0 else "delta-down"
    pct_arrow = "▲" if price_chg >= 0 else "▼"
    rsi_color = ("delta-down" if current_rsi >= 70 else ("delta-up" if current_rsi <= 30 else "delta-neu")) if rsi_available else "delta-neu"
    rsi_value_html = f"{current_rsi:.1f}" if rsi_available else "—"

    score_card_html = ""
    if score is not None:
        score_color = "delta-up" if score_label == "강세" else ("delta-neu" if score_label == "보통" else "delta-down")
        # 한 줄짜리 HTML로 만들어 줄바꿈/들여쓰기로 인한 마크다운 오인식을 방지
        score_card_html = (
            f'<div class="metric-card mc-amber" style="grid-column: span 3;">'
            f'<div class="metric-label">종합점수</div>'
            f'<div class="metric-value">{score:.1f}점</div>'
            f'<div class="metric-delta {score_color}">{score_label}</div>'
            f'</div>'
        )

    front_html = (
        f'<div class="metric-card mc-violet" style="grid-column: span 4;">'
        f'<div class="metric-label">현재가</div>'
        f'<div class="metric-value">${today_data["Close"]:.2f}</div>'
        f'<div class="metric-delta {pct_color}">{pct_arrow} {abs(price_chg):.2f}%</div>'
        f'</div>'
        f'<div class="metric-card mc-teal" style="grid-column: span 4;">'
        f'<div class="metric-label">거래량 (MA20 대비)</div>'
        f'<div class="metric-value">{vol_ma20_ratio:.0f}%</div>'
        f'<div class="metric-delta {"delta-up" if vol_ma20_ratio >= 200 else "delta-neu"}">'
        f'{"🔥 폭증" if vol_ma20_ratio >= 200 else ("보통" if vol_ma20_ratio >= 80 else "저조")}</div>'
        f'</div>'
        f'<div class="metric-card mc-rose" style="grid-column: span 4;">'
        f'<div class="metric-label">당일 거래량</div>'
        f'<div class="metric-value" style="font-size:1.15rem;">{int(today_data["Volume"]):,}주</div>'
        f'</div>'
    )
    end_html = (
        f'<div class="metric-card mc-cyan" style="grid-column: span 3;">'
        f'<div class="metric-label">RSI (14)</div>'
        f'<div class="metric-value">{rsi_value_html}</div>'
        f'<div class="metric-delta {rsi_color}">{rsi_status}</div>'
        f'</div>'
        f'{score_card_html}'
    )
    return front_html, end_html




# ════════════════════════════════════════════════════════════════
# 렌더링 함수 — 기술적 분석
# ════════════════════════════════════════════════════════════════
def render_technical_analysis(ticker_input, hist, today, yesterday, vol_ratio,
                               vol_ma20_ratio, trading_value_krw_eok, threshold_eok,
                               high_52w, low_52w, spike_df=None, offering_list=None,
                               nasdaq_compliance=None, top_cards_front="", top_cards_end="",
                               short_interest=None, execution_strength=None):
    """기술적 조건 & 수급 점검 + 차트 (탭1 또는 좌측 컬럼)

    top_cards_front/top_cards_end이 주어지면(모바일) 상단 요약 카드들을 이 함수의
    metric-grid 앞/뒤에 각각 끼워 넣어 하나의 섹션으로 렌더링하고,
    중국계/급등신호 배너는 그 뒤로 미뤄서 카드 섹션이 끊기지 않게 한다.
    """

    # ── 종목 정보 조회 (국적 판별 등에 사용) ─────────────────────
    info = fetch_ticker_info(ticker_input)
    country = str(info.get("country") or "").strip()
    is_china = country in {"China", "Hong Kong"}

    china_banner_html = ""
    if is_china:
        china_banner_html = f"""
        <div class="china-banner">
            <div class="china-banner-icon">🇨🇳⚠️</div>
            <div>
                <div class="china-banner-text">중국 기업 (China-based Company)</div>
                <div class="china-banner-sub">본사 소재지: {country} — VIE 구조, 회계 투명성, 규제 리스크 등을 반드시 확인하세요</div>
            </div>
        </div>
        """

    if not top_cards_front:
        # 비병합(데스크탑) 경로 — 기존과 동일하게 카드 섹션 이전에 바로 렌더링
        if china_banner_html:
            st.markdown(china_banner_html, unsafe_allow_html=True)

    # ── 변수 계산 ────────────────────────────────────────────────
    pct_chg      = (today['Close'] - yesterday['Close']) / yesterday['Close'] * 100
    rsi_val      = today['RSI']
    macd_val     = today['MACD']
    macd_sig_val = today['MACD_SIG']
    macd_cross   = macd_val > macd_sig_val and yesterday['MACD'] <= yesterday['MACD_SIG']
    macd_dead    = macd_val < macd_sig_val and yesterday['MACD'] >= yesterday['MACD_SIG']
    gap_up_pct   = (today['Open'] - yesterday['Close']) / yesterday['Close'] * 100

    # ── 🔔 급등 신호 배너 ────────────────────────────────────────
    alert_signals = []
    if vol_ma20_ratio >= 200:    alert_signals.append(f"🔥 거래량 MA20 대비 {vol_ma20_ratio:.0f}%")
    if macd_cross:               alert_signals.append("⚡ MACD 골든크로스")
    if rsi_val <= 35:            alert_signals.append("📉 RSI 과매도")
    if today['Close'] > today['MA120'] and yesterday['Close'] <= yesterday['MA120']:
                                  alert_signals.append("🚀 120일선 돌파")
    if pct_chg >= 5:             alert_signals.append(f"📈 당일 +{pct_chg:.1f}%")
    if gap_up_pct >= 5:          alert_signals.append(f"⬆️ 갭업 시초가 +{gap_up_pct:.1f}%")

    alert_banner_html = ""
    if alert_signals:
        chips = "".join([f'<span class="signal-chip">{s}</span>' for s in alert_signals])
        alert_banner_html = f"""
        <div class="alert-banner">
            <div class="alert-icon">🔔</div>
            <div>
                <div class="alert-title">급등 신호 감지!</div>
                <div class="alert-signals">{chips}</div>
            </div>
        </div>
        """

    if not top_cards_front and alert_banner_html:
        st.markdown(alert_banner_html, unsafe_allow_html=True)

    # ── 메트릭 카드 (#개선 상단 요약 스코어보드와 겹치던 현재가/RSI(14) 카드 제거) ──
    # #7 52주 최저가 추가
    gap_52w_high = ((high_52w - today['Close']) / high_52w) * 100
    gap_52w_low  = ((today['Close'] - low_52w) / low_52w) * 100

    # ── 시가총액 & 유통주식수 조회 ───────────────────────────────
    MC_LOW  = 4_000_000     # $4M
    MC_HIGH = 500_000_000   # $500M
    FLOAT_MAX = 20_000_000  # 20M주

    try:
        market_cap_raw   = info.get("marketCap") or 0
        shares_float_raw = info.get("floatShares") or info.get("sharesOutstanding") or 0
        if market_cap_raw >= 1_000_000_000_000:
            market_cap_str = f"${market_cap_raw / 1_000_000_000_000:.2f}T"
        elif market_cap_raw >= 1_000_000_000:
            market_cap_str = f"${market_cap_raw / 1_000_000_000:.2f}B"
        elif market_cap_raw > 0:
            market_cap_str = f"${market_cap_raw / 1_000_000:.1f}M"
        else:
            market_cap_str = "N/A"
        if shares_float_raw >= 1_000_000_000:
            shares_str = f"{shares_float_raw / 1_000_000_000:.2f}B주"
        elif shares_float_raw > 0:
            shares_str = f"{shares_float_raw / 1_000_000:.1f}M주"
        else:
            shares_str = "N/A"
        # 별표 조건 판정
        mc_star     = (market_cap_raw > 0) and (MC_LOW <= market_cap_raw <= MC_HIGH)
        shares_star = (shares_float_raw > 0) and (shares_float_raw <= FLOAT_MAX)
    except Exception:
        market_cap_str = "N/A"
        shares_str     = "N/A"
        mc_star        = False
        shares_star    = False

    mc_star_html     = ' <span style="color:#e0943a;font-size:1rem;vertical-align:middle;" title="소형주 최적 구간 ($4M~$500M)">⭐</span>' if mc_star else ""
    shares_star_html = ' <span style="color:#e0943a;font-size:1rem;vertical-align:middle;" title="저부동주 조건 (20M주 이하)">⭐</span>' if shares_star else ""

    # ── 공매도 수량 카드 문자열 준비 ──────────────────────────────
    short_interest = short_interest or {}
    if short_interest.get("shares_short"):
        ss = short_interest["shares_short"]
        if ss >= 1_000_000_000:
            short_str = f"{ss / 1_000_000_000:.2f}B주"
        elif ss >= 1_000_000:
            short_str = f"{ss / 1_000_000:.1f}M주"
        else:
            short_str = f"{ss:,.0f}주"
        pct_mom = short_interest.get("pct_change_mom")
        if pct_mom is not None:
            short_delta_cls  = "delta-up" if pct_mom >= 0 else "delta-down"
            short_delta_text = f"전월 대비 {'▲' if pct_mom >= 0 else '▼'} {abs(pct_mom):.1f}%"
        else:
            short_delta_cls, short_delta_text = "delta-neu", "공매도 수량 (Short Interest)"
        short_sub = f"기준일: {short_interest['date']}" if short_interest.get("date") else ""
    else:
        short_str, short_delta_cls, short_delta_text, short_sub = "N/A", "delta-neu", "데이터 없음", ""

    short_pct_float = short_interest.get("short_pct_float")
    short_ratio     = short_interest.get("short_ratio")
    if short_pct_float is not None or short_ratio is not None:
        float_pct_str = f"{short_pct_float * 100:.1f}%" if short_pct_float is not None else "N/A"
        dtc_str       = f"{short_ratio:.1f}일" if short_ratio is not None else "N/A"
        short_ratio_star = (short_pct_float is not None) and (short_pct_float >= 0.20)
        short_ratio_html = (
            f'유통주식 대비 <strong style="font-size:1em;">{float_pct_str}</strong>'
            + (' <span style="color:#e0943a;" title="숏스퀴즈 가능 구간(20%↑)">⭐</span>' if short_ratio_star else "")
            + f' · Days-to-Cover <strong style="font-size:1em;">{dtc_str}</strong>'
        )
        short_ratio_delta_cls = "delta-up" if short_ratio_star else "delta-neu"
    else:
        short_ratio_html, short_ratio_delta_cls = "데이터 없음", "delta-neu"

    # ── 체결강도 카드 문자열 준비 (당일 3분봉 양봉/음봉 거래량 비율 근사치) ──
    execution_strength = execution_strength or {}
    if execution_strength.get("strength") is not None:
        es_val = execution_strength["strength"]
        es_capped_mark = "+" if execution_strength.get("capped") else ""
        es_delta_cls = "delta-up" if es_val >= 100 else "delta-down"
        es_delta_txt = "매수 우위" if es_val >= 100 else "매도 우위"
        es_str = f"{es_val:.0f}{es_capped_mark}"
    else:
        es_str, es_delta_cls, es_delta_txt = "N/A", "delta-neu", "장중 데이터 없음"

    st.markdown(f"""
    <div class="metric-grid metric-grid-12">
        {top_cards_front}
        <div class="metric-card mc-indigo" style="grid-column: span 6;">
            <div class="metric-label">시가총액</div>
            <div class="metric-value" style="font-size:1.2rem;">{market_cap_str}{mc_star_html}</div>
            <div class="metric-delta {"delta-up" if mc_star else "delta-neu"}">{"$4M~$500M 최적 구간 ✓" if mc_star else "Market Cap"}</div>
        </div>
        <div class="metric-card mc-rose" style="grid-column: span 6;">
            <div class="metric-label">유통주식수 (Float Shares)</div>
            <div class="metric-value" style="font-size:1.2rem;">{shares_str}{shares_star_html}</div>
            <div class="metric-delta {"delta-up" if shares_star else "delta-neu"}">{"20M주 이하 저부동주 ✓" if shares_star else "Float Shares"}</div>
        </div>
        <div class="metric-card mc-rose" style="grid-column: span 3;">
            <div class="metric-label">52주 최고가</div>
            <div class="metric-value">${high_52w:.2f}</div>
            <div class="metric-delta delta-neu">↓ {gap_52w_high:.1f}% 하단</div>
        </div>
        <div class="metric-card mc-cyan" style="grid-column: span 3;">
            <div class="metric-label">52주 최저가</div>
            <div class="metric-value">${low_52w:.2f}</div>
            <div class="metric-delta delta-up">↑ {gap_52w_low:.1f}% 상단</div>
        </div>
        {top_cards_end}
        <div class="metric-card mc-rose" style="grid-column: span 4;">
            <div class="metric-label">공매도 수량 (Short Interest)</div>
            <div class="metric-value" style="font-size:1.15rem;">{short_str}</div>
            <div class="metric-delta {short_delta_cls}">{short_delta_text}</div>
            {f'<div style="font-size:0.65rem;color:rgba(148,163,184,0.55);margin-top:0.15rem;">{short_sub}</div>' if short_sub else ''}
        </div>
        <div class="metric-card mc-amber" style="grid-column: span 4;">
            <div class="metric-label">공매도 비율 · Days-to-Cover</div>
            <div class="metric-value" style="font-size:1.0rem;">{short_ratio_html}</div>
            <div class="metric-delta {short_ratio_delta_cls}">FINRA 격주 집계 기준</div>
        </div>
        <div class="metric-card mc-teal" style="grid-column: span 4;">
            <div class="metric-label">체결강도 (당일, 근사치)</div>
            <div class="metric-value">{es_str}</div>
            <div class="metric-delta {es_delta_cls}">{es_delta_txt}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # top_cards_front이 있는 경로(모바일)에서는 중국계/급등신호 배너를
    # 카드 섹션 뒤로 미뤄 카드 섹션이 끊기지 않게 한다.
    if top_cards_front:
        if china_banner_html:
            st.markdown(china_banner_html, unsafe_allow_html=True)
        if alert_banner_html:
            st.markdown(alert_banner_html, unsafe_allow_html=True)

    # ── ⚠️ 나스닥 $1 최소 호가 규정 준수 체크 ───────────────────────
    if nasdaq_compliance and nasdaq_compliance.get("applicable"):
        if nasdaq_compliance["phase"] == "notice_issued_est":
            days_left = nasdaq_compliance["days_left"]
            if days_left > 0:
                dl_dot  = "dot-red" if days_left <= 30 else "dot-yellow"
                dl_text = (
                    f"<strong>나스닥 최소 호가($1) 결핍 상태 — 약 {nasdaq_compliance['streak_days']}영업일 연속 "
                    f"$1 미만</strong><br>"
                    f"결핍통지 추정일: <strong>{nasdaq_compliance['notice_date_est']}</strong> · "
                    f"유예기간(180일) 만료 추정일: <strong>{nasdaq_compliance['deadline_est']}</strong> "
                    f"(<strong>약 {days_left}일</strong> 남음)"
                )
            else:
                dl_dot  = "dot-red"
                dl_text = (
                    f"<strong>나스닥 최소 호가($1) 유예기간 만료 추정일 경과</strong> "
                    f"(추정 만료일: {nasdaq_compliance['deadline_est']}, {abs(days_left)}일 경과) — "
                    f"상장폐지 절차 또는 역병합(reverse split) 등 조치 여부 확인 필요"
                )
            st.markdown(f"""
            <div class="glass-card">
                <div class="status-row">
                    <div class="status-item"><div class="status-dot {dl_dot}"></div><div class="status-text">{dl_text}</div></div>
                </div>
                <div style="font-size:0.7rem;color:rgba(148,163,184,0.55);margin-top:0.35rem;">
                    ⚠️ 실제 결핍통지 발송일은 공개 시세 데이터로 확인할 수 없어 30영업일 연속 미달 시점을 기준으로 추정한 값입니다. 참고용으로만 사용하세요.
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            days_to_notice = nasdaq_compliance["days_to_notice"]
            st.markdown(f"""
            <div class="glass-card">
                <div class="status-row">
                    <div class="status-item"><div class="status-dot dot-yellow"></div>
                    <div class="status-text"><strong>$1 미만 거래 중</strong> — 연속 {nasdaq_compliance['streak_days']}영업일째.
                    나스닥 결핍통지 기준(연속 30영업일)까지 <strong>약 {days_to_notice}영업일</strong> 남음</div></div>
                </div>
                <div style="font-size:0.7rem;color:rgba(148,163,184,0.55);margin-top:0.35rem;">
                    ⚠️ Nasdaq Listing Rule 5550(a)(2) 기준 추정치이며, 실제 결핍통지 여부는 공식 공시를 확인하세요.
                </div>
            </div>
            """, unsafe_allow_html=True)

    # ── 🧱 악성매물대 분석 + 🎯 돌파 가능성 점검 (좌우 배열) ──────────
    supply_data = calc_supply_zones(
        hist, float(today['Close']),
        n_bins=supply_n_bins,
        lookback_days=supply_lookback_days,
        heavy_mult=supply_heavy_mult,
        max_zones=supply_max_zones,
        max_zone_width_pct=supply_max_width_pct,
    )
    breakout_calc = calc_breakout_probability(
        float(today['Close']), supply_data,
        rsi_val=rsi_val, vol_ma20_ratio=vol_ma20_ratio,
        macd_val=macd_val, macd_sig_val=macd_sig_val, macd_cross=macd_cross,
    )
    col_supply, col_breakout = st.columns(2, gap="medium")
    with col_supply:
        render_supply_zones(float(today['Close']), supply_data)

        # ── 수급 체크 ────────────────────────────────────────────
        ui_section_header(mono_icon_badge("bulb", color="var(--c-amber)"), "실시간 자금 유입 체크", "icon-amber", "title-amber")

        # #8 거래량: 전일 대비 + MA20 대비 둘 다 표시
        vol_dot  = "dot-green"  if vol_ma20_ratio >= 200 else "dot-yellow"
        vol_text = (f"<strong>거래량 폭증!</strong> MA20 대비 <strong>{vol_ma20_ratio:.0f}%</strong> "
                    f"(전일 대비 {vol_ratio:.0f}%)"
                    if vol_ma20_ratio >= 200
                    else f"거래량 MA20 대비 {vol_ma20_ratio:.0f}% (전일 대비 {vol_ratio:.0f}%)")
        tv_dot   = "dot-green"  if trading_value_krw_eok >= threshold_eok else "dot-yellow"
        tv_text  = (f"<strong>거래대금 통과!</strong> 약 <strong>{trading_value_krw_eok:.0f}억 원</strong> 유입 "
                    f"<span style='color:rgba(148,163,184,0.5);font-size:0.75em;'>(₩{fetch_usd_to_krw():,.0f} 기준)</span>"
                    if trading_value_krw_eok >= threshold_eok
                    else f"거래대금 {trading_value_krw_eok:.0f}억 원 ({threshold_eok}억 이상 추천)")

        st.markdown(f"""
        <div class="glass-card">
            <div class="status-row">
                <div class="status-item"><div class="status-dot {vol_dot}"></div><div class="status-text">{vol_text}</div></div>
                <div class="status-item"><div class="status-dot {tv_dot}"></div><div class="status-text">{tv_text}</div></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── 이동평균선 배열 ──────────────────────────────────────
        ui_section_header(mono_icon_badge("trend", color="var(--c-teal)"), "이동평균선 배열", "icon-teal", "title-teal")

        # #버그수정: 상장 120일 미만 종목은 MA120이 NaN이라 아래 조건이 모두 False가 되어
        # 예전엔 "이평선 밀집" 문구로 얼버무려졌음(값도 nan으로 찍힘) → 데이터 부족을 명시.
        if pd.isna(today['MA120']):
            ma_dot, ma_text = "dot-blue", "상장 120거래일 미만 — MA120 데이터 부족 (신뢰도 낮은 구간)"
        elif today['MA5'] > today['MA20'] > today['MA120']:
            ma_dot, ma_text = "dot-green", "<strong>완전 정배열</strong> — 강력한 상승 추세 유지 중"
        elif today['Close'] > today['MA120'] and yesterday['Close'] <= yesterday['MA120']:
            ma_dot, ma_text = "dot-green", "<strong>120일선 돌파!</strong> — 급등 초입 타점"
        else:
            ma_dot, ma_text = "dot-blue", f"이평선 밀집 — 에너지 응축 횡보 구간 &nbsp;|&nbsp; MA5 <strong>${today['MA5']:.1f}</strong> / MA20 <strong>${today['MA20']:.1f}</strong>"

        # ── RSI ──────────────────────────────────────────────────
        if pd.isna(rsi_val):
            rsi_dot, rsi_txt = "dot-blue", "상장 14거래일 미만 — RSI 데이터 부족"
        elif rsi_val >= 70:
            rsi_dot, rsi_txt = "dot-yellow", f"<strong>RSI {rsi_val:.1f} — 과매수</strong> 단기 조정 가능성 주의"
        elif rsi_val <= 30:
            rsi_dot, rsi_txt = "dot-green",  f"<strong>RSI {rsi_val:.1f} — 과매도</strong> 반등 매수 타점"
        else:
            rsi_dot, rsi_txt = "dot-blue",   f"RSI <strong>{rsi_val:.1f}</strong> — 중립 구간 (30~70)"

        # ── 볼린저밴드 ─────────────────────────────────────────────
        if pd.isna(today['BB_UPPER']) or pd.isna(today['BB_LOWER']):
            bb_dot, bb_txt = "dot-blue", "상장 20거래일 미만 — 볼린저밴드 데이터 부족"
        else:
            bb_range = today['BB_UPPER'] - today['BB_LOWER']
            bb_pct   = (today['Close'] - today['BB_LOWER']) / bb_range * 100 if bb_range else 50
            if today['Close'] >= today['BB_UPPER']:
                bb_dot, bb_txt = "dot-yellow", f"<strong>볼린저 상단 터치 ({bb_pct:.0f}%)</strong> — 과열 구간"
            elif today['Close'] <= today['BB_LOWER']:
                bb_dot, bb_txt = "dot-green",  f"<strong>볼린저 하단 터치 ({bb_pct:.0f}%)</strong> — 반등 구간"
            else:
                bb_dot, bb_txt = "dot-blue",   f"밴드 내부 <strong>{bb_pct:.0f}%</strong> 위치 &nbsp;|&nbsp; 밴드폭 {today['BB_WIDTH']:.1f}%"


        # ── MACD ───────────────────────────────────────────────────
        hist_val  = today['MACD_HIST']
        prev_hist = yesterday['MACD_HIST']
        if macd_cross:
            mc_dot, mc_txt = "dot-green",  "<strong>MACD 골든크로스 발생!</strong> — 상승 전환 신호"
        elif macd_dead:
            mc_dot, mc_txt = "dot-red",    "<strong>MACD 데드크로스 발생</strong> — 하락 전환 주의"
        elif hist_val > 0 and hist_val > prev_hist:
            mc_dot, mc_txt = "dot-blue",   "MACD 히스토그램 확대 — 상승 모멘텀 강화"
        else:
            mc_dot, mc_txt = "dot-yellow", f"MACD <strong>{macd_val:.3f}</strong> / Signal <strong>{macd_sig_val:.3f}</strong> / Hist {hist_val:.3f}"

        st.markdown(f"""
        <div class="glass-card">
            <div class="status-row">
                <div class="status-item"><div class="status-dot {ma_dot}"></div><div class="status-text">{ma_text}</div></div>
                <div class="status-item"><div class="status-dot {rsi_dot}"></div><div class="status-text">{rsi_txt}</div></div>
                <div class="status-item"><div class="status-dot {bb_dot}"></div><div class="status-text">{bb_txt}</div></div>
                <div class="status-item"><div class="status-dot {mc_dot}"></div><div class="status-text">{mc_txt}</div></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col_breakout:
        render_breakout_probability(breakout_calc)

    # ── 🚀 급등 이력 / 📜 오퍼링 이력 (좌우 배치) ─────────────────
    col_spike, col_offering = st.columns(2, gap="medium")

    with col_spike:
        ui_section_header(mono_icon_badge("rocket", color="var(--c-rose)"), "하루 100%+ 급등 이력", "icon-rose", "title-rose")
        if spike_df is not None and not spike_df.empty:
            rows_html = ""
            for dt_idx, row in spike_df.head(15).iterrows():
                rows_html += (
                    f"<div class='status-item'><div class='status-dot dot-green'></div>"
                    f"<div class='status-text'>{dt_idx.date()} — 종가 ${row['Close']:.2f} "
                    f"<strong style='color:#34d399;'>▲ {row['PctChange']:.1f}%</strong> "
                    f"(거래량 {int(row['Volume']):,})</div></div>"
                )
            more_note = (f"<div style='font-size:0.7rem;color:rgba(148,163,184,0.55);margin-top:0.35rem;'>"
                          f"총 {len(spike_df)}회 중 최근 15건 표시</div>" if len(spike_df) > 15 else "")
            st.markdown(f"""
            <div class="glass-card">
                <div class="status-row" style="flex-direction:column;align-items:stretch;gap:0.5rem;">
                    {rows_html}
                </div>
                {more_note}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="glass-card">
                <div class="status-row">
                    <div class="status-item"><div class="status-dot dot-blue"></div>
                    <div class="status-text">상장 이후 하루 +100% 이상 급등 이력이 없습니다 (조회 가능한 전체 기간 기준)</div></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    with col_offering:
        ui_section_header(mono_icon_badge("doc", color="var(--c-amber)"), "오퍼링(유상증자) 관련 공시 이력", "icon-amber", "title-amber")
        if offering_list:
            rows_html = ""
            for o in offering_list[:3]:
                link_html = f"<a class='news-link' href='{o['url']}' target='_blank'>공시 원문 →</a>" if o.get("url") else ""
                rows_html += (
                    f"<div class='status-item'><div class='status-dot dot-yellow'></div>"
                    f"<div class='status-text'>📅 {o['date']} &nbsp;<strong>{o['type']}</strong> — {o['title']} {link_html}</div></div>"
                )
            more_note = (f"<div style='font-size:0.7rem;color:rgba(148,163,184,0.55);margin-top:0.35rem;'>"
                          f"총 {len(offering_list)}건 중 최근 3건 표시</div>" if len(offering_list) > 3 else "")
            st.markdown(f"""
            <div class="glass-card">
                <div class="status-row" style="flex-direction:column;align-items:stretch;gap:0.5rem;">
                    {rows_html}
                </div>
                {more_note}
            </div>
            """, unsafe_allow_html=True)

            # ── 최근 오퍼링(ATM 등) 이후 추정 희석 물량 ──────────────
            dilution = calc_dilution_since_offering(ticker_input, offering_list[0]["date"])
            if dilution and dilution.get("diluted_shares") is not None:
                d_shares = dilution["diluted_shares"]
                d_pct    = dilution.get("diluted_pct")
                if d_shares > 0:
                    d_dot  = "dot-red" if (d_pct or 0) >= 5 else "dot-yellow"
                    d_text = (
                        f"최근 공시(<strong>{offering_list[0]['date']}</strong>) 이후 유통주식수 약 "
                        f"<strong>{d_shares:,.0f}주</strong> 증가"
                        + (f" (<strong>+{d_pct:.1f}%</strong>)" if d_pct is not None else "")
                        + " — 이미 시장에 풀린 것으로 추정되는 희석 물량입니다."
                    )
                elif d_shares < 0:
                    d_dot, d_text = "dot-green", (
                        f"최근 공시(<strong>{offering_list[0]['date']}</strong>) 이후 유통주식수는 오히려 "
                        f"약 {abs(d_shares):,.0f}주 감소했습니다 (자사주 매입/역병합 등의 영향일 수 있음)."
                    )
                else:
                    d_dot, d_text = "dot-blue", f"최근 공시(<strong>{offering_list[0]['date']}</strong>) 이후 유통주식수 변화가 감지되지 않았습니다."
                st.markdown(f"""
                <div class="glass-card" style="margin-top:0.6rem;">
                    <div class="status-row">
                        <div class="status-item"><div class="status-dot {d_dot}"></div><div class="status-text">{d_text}</div></div>
                    </div>
                    <div style="font-size:0.7rem;color:rgba(148,163,184,0.55);margin-top:0.35rem;">
                        ⚠️ ATM(시장가발행) 프로그램의 승인·잔여 한도(달러 기준)는 공시 원문에서만 확인 가능합니다.
                        위 수치는 공시일 이후 실제 유통주식수 증감을 근사 추적한 것이며, 잔여 한도 자체가 아닙니다.
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="glass-card">
                <div class="status-row">
                    <div class="status-item"><div class="status-dot dot-blue"></div>
                    <div class="status-text">S-1 / S-3 / 424B 계열 오퍼링 관련 공시 이력이 조회되지 않았습니다</div></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # ── 📝 분석 메모 ─────────────────────────────────────────────
    ui_section_header(mono_icon_badge("note", color="var(--c-violet)"), "분석 메모", "icon-violet", "title-violet")
    existing_memo = st.session_state.memos.get(ticker_input, "")
    new_memo = st.text_area(
        "memo",
        value=existing_memo,
        placeholder="매수 근거, 목표가, 손절선 등 자유롭게 기록하세요...",
        height=95,
        key=f"memo_input_{ticker_input}",
        label_visibility="collapsed",
    )
    memo_col1, memo_col2 = st.columns([3, 1])
    with memo_col1:
        if st.button("💾 메모 저장", key=f"save_memo_{ticker_input}", use_container_width=True):
            st.session_state.memos[ticker_input] = new_memo
            save_memos(st.session_state.memos)   # #9 파일 저장
            st.success("✅ 저장 완료! (앱 재시작 후에도 유지됩니다)")
    with memo_col2:
        if st.button("🗑️ 삭제", key=f"del_memo_{ticker_input}", use_container_width=True):
            st.session_state.memos.pop(ticker_input, None)
            save_memos(st.session_state.memos)   # #9 파일 동기화
            st.rerun()


# ════════════════════════════════════════════════════════════════
# 렌더링 함수 — 섹터 히트맵
# ════════════════════════════════════════════════════════════════
def _sector_color(pct: float) -> tuple[str, str]:
    """등락률에 따른 배경색·텍스트색 반환"""
    if pct >= 3.0:
        return "rgba(52,211,153,0.30)", "#34d399"
    elif pct >= 1.5:
        return "rgba(52,211,153,0.18)", "#6ee7b7"
    elif pct >= 0.3:
        return "rgba(52,211,153,0.09)", "#a7f3d0"
    elif pct >= -0.3:
        return "rgba(148,163,184,0.10)", "#94a3b8"
    elif pct >= -1.5:
        return "rgba(248,113,113,0.09)", "#fca5a5"
    elif pct >= -3.0:
        return "rgba(248,113,113,0.18)", "#f87171"
    else:
        return "rgba(248,113,113,0.30)", "#ef4444"

def render_sector_heatmap():
    """S&P 500 섹터 히트맵 (당일/1주/1개월 탭)"""
    ui_section_header(mono_icon_badge("grid", color="var(--c-cyan)"), "S&P 500 섹터 히트맵")

    with st.spinner("섹터 ETF 데이터 로딩 중..."):
        sector_data = fetch_sector_data()

    if not sector_data:
        st.warning("섹터 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해 주세요.")
        return

    view_tab1, view_tab2, view_tab3 = st.tabs(["📅 당일", "📆 1주", "🗓️ 1개월"])

    def _render_grid(key: str, label: str):
        sorted_data = sorted(sector_data, key=lambda x: x[key], reverse=True)
        cells_html = ""
        for s in sorted_data:
            pct = s[key]
            bg, color = _sector_color(pct)
            arrow = "▲" if pct >= 0 else "▼"
            cells_html += f"""
            <div class="sector-cell" style="background:{bg}; border-color:{color}33;">
                <div class="sector-name">{s['sector']}</div>
                <div class="sector-ticker">{s['ticker']}</div>
                <div class="sector-pct" style="color:{color};">{arrow} {abs(pct):.2f}%</div>
                <div class="sector-sub" style="color:{color};">${s['price']}</div>
            </div>"""

        legend_html = """
        <div class="sector-legend">
            <span style="font-size:0.72rem;color:rgba(148,163,184,0.6);font-weight:600;">강도:</span>
            <div class="legend-item"><div class="legend-dot" style="background:rgba(52,211,153,0.30);border:1px solid #34d399;"></div>강세 (+3%↑)</div>
            <div class="legend-item"><div class="legend-dot" style="background:rgba(52,211,153,0.12);border:1px solid #6ee7b7;"></div>약강세</div>
            <div class="legend-item"><div class="legend-dot" style="background:rgba(148,163,184,0.10);border:1px solid #94a3b8;"></div>보합</div>
            <div class="legend-item"><div class="legend-dot" style="background:rgba(248,113,113,0.12);border:1px solid #f87171;"></div>약약세</div>
            <div class="legend-item"><div class="legend-dot" style="background:rgba(248,113,113,0.30);border:1px solid #ef4444;"></div>약세 (-3%↓)</div>
        </div>"""

        # 강세/약세 상위 섹터 요약
        top = sorted_data[0]
        bot = sorted_data[-1]
        top_bg, top_c = _sector_color(top[key])
        bot_bg, bot_c = _sector_color(bot[key])
        summary_html = f"""
        <div style="display:flex;gap:0.6rem;margin-bottom:0.9rem;flex-wrap:wrap;">
            <div style="flex:1;min-width:120px;background:{top_bg};border:1px solid {top_c}44;border-radius:10px;padding:0.6rem 0.8rem;">
                <div style="font-size:0.65rem;color:rgba(255,255,255,0.5);font-weight:700;text-transform:uppercase;margin-bottom:0.2rem;">🏆 최강 섹터</div>
                <div style="font-size:0.9rem;font-weight:800;color:{top_c};">{top['sector']} ({top['ticker']})</div>
                <div style="font-size:0.8rem;color:{top_c};">▲ {top[key]:.2f}%</div>
            </div>
            <div style="flex:1;min-width:120px;background:{bot_bg};border:1px solid {bot_c}44;border-radius:10px;padding:0.6rem 0.8rem;">
                <div style="font-size:0.65rem;color:rgba(255,255,255,0.5);font-weight:700;text-transform:uppercase;margin-bottom:0.2rem;">📉 최약 섹터</div>
                <div style="font-size:0.9rem;font-weight:800;color:{bot_c};">{bot['sector']} ({bot['ticker']})</div>
                <div style="font-size:0.8rem;color:{bot_c};">▼ {abs(bot[key]):.2f}%</div>
            </div>
        </div>"""

        st.markdown(summary_html + legend_html + f'<div class="sector-grid">{cells_html}</div>', unsafe_allow_html=True)

    with view_tab1:
        _render_grid("d1", "당일")
    with view_tab2:
        _render_grid("w1", "1주")
    with view_tab3:
        _render_grid("m1", "1개월")


# ════════════════════════════════════════════════════════════════
# 렌더링 함수 — 급등주 검색기 (Yahoo Finance 실시간 스크리너)
# ════════════════════════════════════════════════════════════════
def render_surge_screener():
    """
    조건(상승률/주가/거래량/거래대금/기술지표/리스크)에 맞는 급등주를 검색합니다.
    1차: Yahoo Finance 공식 스크리너로 후보 종목 수집
    2차: ThreadPoolExecutor로 RSI·거래량비율·거래대금·국가·나스닥 컴플라이언스 병렬 병합
    3차: 유저가 선택한 신호/리스크 필터 및 정렬 기준 적용
    """
    ui_section_header(mono_icon_badge("rocket", color="var(--c-rose)"), "급등주 검색기", "icon-rose", "title-rose")
    st.caption("Yahoo Finance 실시간(지연 가능) 시세 + RSI·거래대금·리스크 지표를 결합한 정밀 검색기입니다.")

    # ── 1차 검색 조건 ────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        min_pct = st.slider(
            "최소 상승률 (%)", min_value=3, max_value=100, value=10, step=1,
            key="screener_min_pct"
        )
    with c2:
        price_range = st.slider(
            "주가 범위 ($)", min_value=0.0, max_value=200.0, value=(1.0, 20.0), step=0.5,
            key="screener_price_range"
        )
    with c3:
        min_volume = st.number_input(
            "최소 거래량", min_value=0, value=500_000, step=100_000,
            key="screener_min_vol"
        )

    # ── 정렬 기준 & 기술 시그널 필터 ─────────────────────────────
    d1, d2 = st.columns(2)
    with d1:
        sort_option = st.radio(
            "정렬 기준", ["종합점수 순", "등락률 순", "거래대금 순", "거래량 순"],
            horizontal=True, key="screener_sort"
        )
    with d2:
        signal_filter = st.selectbox(
            "기술 시그널 필터",
            ["전체", "RSI 30 이하 (과매도)", "RSI 70 이상 (과매수)", "거래량 200%+ 돌파"],
            key="screener_signal_filter"
        )

    # ── 리스크 스크리닝 필터 ─────────────────────────────────────
    e1, e2, e3 = st.columns(3)
    with e1:
        require_trading_value = st.checkbox(
            f"💰 거래대금 {TRADING_THRESHOLD}억 이상만", value=False,
            key="screener_min_trading_value"
        )
    with e2:
        exclude_penny = st.checkbox(
            "🪙 동전주($1 미만) 제외", value=False, key="screener_exclude_penny"
        )
    with e3:
        exclude_china = st.checkbox(
            "⚠️ 중국계 기업 제외", value=False, key="screener_exclude_china"
        )

    if st.button("🔍 검색 실행", key="run_screener", use_container_width=True):
        with st.spinner("Yahoo Finance에서 급등주 검색 및 상세 지표 병렬 수집 중..."):
            base = fetch_top_gainers(min_pct, price_range[0], price_range[1], int(min_volume))
            tickers = tuple(r["ticker"] for r in base if r.get("ticker"))
            enriched_map = enrich_screener_results(tickers) if tickers else {}

            merged = []
            for r in base:
                extra = enriched_map.get(r["ticker"], {})
                if extra.get("error"):
                    continue   # 상세 지표 수집 실패 종목은 리스트에서 제외
                combined = {**r, **extra}
                combined["score"] = calc_screener_score(combined)
                merged.append(combined)
            st.session_state["screener_results"] = merged

    results = st.session_state.get("screener_results", [])
    if not results:
        st.info("조건을 설정하고 '🔍 검색 실행' 버튼을 눌러주세요.")
        return

    # ── 후속 필터 적용 (병합된 상세 지표 기반) ──────────────────
    filtered = list(results)
    if require_trading_value:
        filtered = [r for r in filtered if r.get("trading_value_eok", 0) >= TRADING_THRESHOLD]
    if exclude_penny:
        filtered = [r for r in filtered if r.get("price", 0) >= NASDAQ_MIN_BID]
    if exclude_china:
        filtered = [r for r in filtered if not r.get("is_china")]
    if signal_filter == "RSI 30 이하 (과매도)":
        filtered = [r for r in filtered if r.get("rsi") is not None and r["rsi"] <= 30]
    elif signal_filter == "RSI 70 이상 (과매수)":
        filtered = [r for r in filtered if r.get("rsi") is not None and r["rsi"] >= 70]
    elif signal_filter == "거래량 200%+ 돌파":
        filtered = [r for r in filtered if r.get("vol_ma20_ratio", 0) >= 200]

    # ── 정렬 ─────────────────────────────────────────────────────
    sort_key_map = {
        "종합점수 순": lambda r: r.get("score", 0) or 0,
        "등락률 순":   lambda r: r.get("pct_change", 0) or 0,
        "거래대금 순": lambda r: r.get("trading_value_eok", 0) or 0,
        "거래량 순":   lambda r: r.get("volume", 0) or 0,
    }
    filtered.sort(key=sort_key_map[sort_option], reverse=True)

    if not filtered:
        st.warning("조건에 맞는 종목이 없습니다. 필터를 완화해 보세요.")
        return

    st.markdown(f"**{len(filtered)}개 종목** (1차 후보 {len(results)}개 중 필터링 결과)")

    # ── 상장 리스크 요약 텍스트 (calc_nasdaq_compliance 응용) ───
    def _risk_text(r: dict) -> str:
        risk = r.get("nasdaq_risk") or {}
        if not risk.get("applicable"):
            return "—"
        if risk.get("phase") == "notice_issued_est":
            return f"⛔ 유예 D-{risk.get('days_left', '?')}"
        return f"🟡 미달 {risk.get('streak_days', 0)}일째"

    rows = []
    for r in filtered:
        is_fav = r["ticker"] in st.session_state.favorites
        rows.append({
            "⭐":            "★" if is_fav else "",
            "티커":          ("⚠️ " if r.get("is_china") else "") + r["ticker"],
            "종목명":        (r.get("name") or "")[:26],
            "현재가":        r.get("price", 0),
            "등락률(%)":     r.get("pct_change", 0),
            "종합점수":      r.get("score", 0),
            "거래량":        r.get("volume", 0),
            "거래대금(억)":  r.get("trading_value_eok", 0),
            "RSI":           r.get("rsi"),
            "거래량비율(%)":  r.get("vol_ratio", 0),
            "20일MA비율(%)": r.get("vol_ma20_ratio", 0),
            "상장리스크":     _risk_text(r),
        })

    df_display = pd.DataFrame(rows)

    event = st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "현재가":        st.column_config.NumberColumn(format="$%.2f"),
            "등락률(%)":     st.column_config.NumberColumn(format="%+.2f%%"),
            "종합점수":      st.column_config.ProgressColumn(format="%.1f", min_value=0, max_value=100),
            "거래량":        st.column_config.NumberColumn(format="%d"),
            "거래대금(억)":  st.column_config.NumberColumn(format="%.1f억"),
            "RSI":           st.column_config.NumberColumn(format="%.1f"),
            "거래량비율(%)":  st.column_config.NumberColumn(format="%.0f%%"),
            "20일MA비율(%)": st.column_config.NumberColumn(format="%.0f%%"),
        },
        key="screener_df",
    )

    st.caption("⚠️ = 중국/홍콩 소재 기업 · ⭐ = 즐겨찾기 등록 종목 · 상장리스크는 나스닥 최소호가($1) 규정 기준 추정치입니다. "
               "행을 클릭하면 해당 종목의 정밀 분석 화면으로 이동합니다. 종합점수는 절대적 매매 신호가 아닌 상대 비교용 참고 지표입니다.")

    # ── 검색 결과에서 바로 즐겨찾기 추가/제거 ───────────────────
    fav_candidates = [r["ticker"] for r in filtered]
    current_fav_in_results = [t for t in fav_candidates if t in st.session_state.favorites]

    def _on_screener_fav_change():
        selected = st.session_state.get("screener_fav_multiselect", [])
        changed = False
        for t in fav_candidates:
            if t in selected and t not in st.session_state.favorites:
                st.session_state.favorites.append(t)
                changed = True
            elif t not in selected and t in st.session_state.favorites:
                st.session_state.favorites.remove(t)
                changed = True
        if changed:
            save_favorites(st.session_state.favorites)

    st.multiselect(
        "⭐ 검색 결과 중 즐겨찾기에 추가/제거할 종목",
        options=fav_candidates,
        default=current_fav_in_results,
        key="screener_fav_multiselect",
        on_change=_on_screener_fav_change,
        help="선택하면 즐겨찾기에 추가되고, 선택 해제하면 즐겨찾기에서 제거됩니다.",
    )

    # ── 검색 결과 CSV 다운로드 ───────────────────────────────────
    csv_bytes = df_display.to_csv(index=False).encode("utf-8-sig")   # 엑셀 한글 깨짐 방지
    st.download_button(
        "📥 검색 결과 CSV 다운로드",
        data=csv_bytes,
        file_name=f"screener_results_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    sel_rows = []
    if event is not None:
        try:
            sel_rows = event.selection["rows"]
        except Exception:
            sel_rows = []

    if sel_rows:
        picked_ticker = filtered[sel_rows[0]]["ticker"]
        st.session_state["selected_ticker"] = picked_ticker
        st.session_state["active_ticker"]   = picked_ticker
        st.session_state["has_searched"]    = True
        st.rerun()



# ════════════════════════════════════════════════════════════════
# 렌더링 함수 — 뉴스
# ════════════════════════════════════════════════════════════════
def _render_reverse_split_banner(splits: list):
    """감지된 리버스 스플릿(주식병합) 뉴스를 경고 배너로 표시합니다."""
    if not splits:
        return
    for s in splits:
        ratio_html = f" &nbsp;·&nbsp; 비율(추정): <strong>{s['ratio']}</strong>" if s["ratio"] else ""
        if s["effective_date"]:
            date_html = f"시행(effective) 예정일: <strong>{s['effective_date']}</strong>"
        else:
            date_html = "시행일이 뉴스 원문에 명시되지 않음 — 원문 링크에서 정확한 일정을 확인하세요"
        pub_html = f" (게재일: {s['date']})" if s["date"] else ""
        link_html = f"<br><a class='news-link' href='{s['link']}' target='_blank'>관련 뉴스 원문 보기 →</a>" if s["link"] else ""
        st.markdown(f"""
        <div class="split-banner">
            <div class="split-banner-title">⚠️ 주식병합(리버스 스플릿) 관련 뉴스 감지{pub_html}</div>
            <div class="split-banner-body">{date_html}{ratio_html}<br>{s['title']}{link_html}</div>
        </div>
        """, unsafe_allow_html=True)

def render_news_section(ticker_input):
    """스톡타이탄 뉴스 & Rhea-AI 호재 검증 (탭2 또는 우측 컬럼)"""
    ui_section_header(mono_icon_badge("fire", color="var(--c-rose)"), "스톡타이탄 실시간 호재 & Rhea-AI 분석", "icon-rose", "title-rose")

    news_data = get_stock_titan_data(ticker_input)[:3]

    if not news_data:
        st.markdown("""
        <div class="glass-card">
            <div class="status-row">
                <div class="status-item"><div class="status-dot dot-yellow"></div>
                <div class="status-text">스톡타이탄 크롤링 불가 — 야후 파이낸스 뉴스로 대체합니다.</div></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # #6 fallback 뉴스 병렬 번역
        raw_news_list = fetch_yahoo_news(ticker_input)[:3]
        parsed_list   = [parse_yahoo_news_item(r) for r in raw_news_list]
        titles_en     = [n["title"] for n in parsed_list]

        _translations = translate_texts_batch(titles_en)
        translated    = [_translations.get(t, t) for t in titles_en]

        # ── ⚠️ 주식병합(리버스 스플릿) 예정 뉴스 감지 ────────────────
        split_source = [
            {"date": "", "title": t_ko, "title_en": n["title"], "link": n["link"]}
            for n, t_ko in zip(parsed_list, translated)
        ]
        _render_reverse_split_banner(detect_reverse_split_news(split_source))

        for news_item, title_ko in zip(parsed_list, translated):
            st.markdown(f"""
            <div class="news-card">
                <div class="news-meta">📰 {news_item['publisher']}</div>
                <div class="news-title">{title_ko}</div>
                <a class="news-link" href="{news_item['link']}" target="_blank">기사 원문 보기 →</a>
            </div>
            """, unsafe_allow_html=True)
    else:
        # ── ⚠️ 주식병합(리버스 스플릿) 예정 뉴스 감지 ────────────────
        _render_reverse_split_banner(detect_reverse_split_news(news_data))

        for n in news_data:
            if n['sentiment'] == "Positive":
                card_cls  = "news-card pos-card"
                sent_html = '<span class="sentiment-badge sent-pos">🟢 호재</span>'
            elif n['sentiment'] == "Negative":
                card_cls  = "news-card neg-card"
                sent_html = '<span class="sentiment-badge sent-neg">🔴 악재</span>'
            elif n['sentiment'] == "Neutral":
                card_cls  = "news-card neu-card"
                sent_html = '<span class="sentiment-badge sent-neu">🟡 중립</span>'
            else:
                card_cls  = "news-card"
                sent_html = '<span style="color:rgba(148,163,184,0.6);font-size:0.72rem;">⚪ 분석 대기</span>'

            impact_html = ' <span class="impact-badge">⚡ HIGH IMPACT</span>' if n['impact'] == "High Impact" else ""

            st.markdown(f"""
            <div class="{card_cls}">
                <div class="news-meta">📅 {n['date']} &nbsp;{sent_html}{impact_html}</div>
                <div class="news-title">{n['title']}</div>
                <div class="news-orig">{n['title_en']}</div>
                <a class="news-link" href="{n['link']}" target="_blank">스톡타이탄 원문 보기 →</a>
            </div>
            """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# 섹터 히트맵 (토글)
# ════════════════════════════════════════════════════════════════
if st.session_state.get("show_heatmap", False):
    render_sector_heatmap()
    st.markdown("---")

if st.session_state.get("show_screener", False):
    render_surge_screener()
    st.markdown("---")

# ════════════════════════════════════════════════════════════════
# 메인 대시보드 로직
# ════════════════════════════════════════════════════════════════
if search_button:
    # #15 버튼은 클릭된 그 순간에만 True — 차트 기간 라디오 등 다른 위젯과
    # 상호작용하면 다음 리렌더링에서 search_button이 다시 False가 되어
    # 아래 분석 결과 블록이 통째로 사라지는 문제가 있었음.
    # → session_state에 "검색됨" 상태와 티커를 저장해 리렌더링 후에도 유지.
    st.session_state["active_ticker"] = ticker_input
    st.session_state["has_searched"]  = True

if st.session_state.get("has_searched"):
    active_ticker = st.session_state.get("active_ticker", ticker_input)

    with st.spinner("야후 파이낸스 및 스톡타이탄에서 실시간 데이터를 분석 중입니다..."):
        # ── 성능 개선: 서로 의존관계 없는 네트워크 호출을 동시에 실행 ──
        # 기존엔 history → spike_history → offering_history → 환율 이 순차 대기라
        # 체감 속도가 느렸음. fetch_ticker_info는 이후 render_technical_analysis에서
        # 다시 호출되지만 1시간 캐시라 여기서 미리 예열해두면 그때는 즉시 반환됨.
        with ThreadPoolExecutor(max_workers=7) as _prefetch_ex:
            _fut_hist     = _prefetch_ex.submit(fetch_history, active_ticker)
            _fut_spike    = _prefetch_ex.submit(fetch_spike_history, active_ticker)
            _fut_offering = _prefetch_ex.submit(fetch_offering_history, active_ticker)
            _fut_info     = _prefetch_ex.submit(fetch_ticker_info, active_ticker)
            _fut_fx       = _prefetch_ex.submit(fetch_usd_to_krw)
            _fut_short    = _prefetch_ex.submit(fetch_short_interest, active_ticker)
            _fut_intraday = _prefetch_ex.submit(fetch_intraday_3min, active_ticker)

            hist          = _fut_hist.result()
            spike_df      = _fut_spike.result()
            offering_list = _fut_offering.result()
            _fut_info.result()   # 캐시 예열 목적 — 결과는 render_technical_analysis에서 재조회
            usd_krw        = _fut_fx.result()
            short_interest = _fut_short.result()
            intraday_3min  = _fut_intraday.result()
            execution_strength = calc_execution_strength(intraday_3min)

        if hist.empty:
            st.error("❌ 올바르지 않은 티커명이거나 데이터를 불러올 수 없습니다. 영문 티커를 확인해 주세요.")
        else:
            hist = hist.dropna()

            if len(hist) < 2:
                st.error("❌ 데이터가 너무 적습니다. 상장된 지 얼마 안 된 종목이거나 거래 정지 상태일 수 있습니다.")
                st.stop()

            hist      = calc_indicators(hist)
            today     = hist.iloc[-1]
            yesterday = hist.iloc[-2]

            # 거래량 — 전일 대비 + MA20 대비
            vol_ratio      = (today['Volume'] / yesterday['Volume']) * 100 if yesterday['Volume'] else 0
            # #버그수정: 상장 20일 미만 종목은 VOL_MA20이 NaN → 1로 나누면 "거래량(MA20 대비)"
            # 카드에 수백만%가 찍히는 오류가 있었음. 데이터 부족 시 중립(100%)으로 처리.
            vol_ma20       = today['VOL_MA20'] if pd.notna(today['VOL_MA20']) and today['VOL_MA20'] > 0 else today['Volume']
            vol_ma20_ratio = (today['Volume'] / vol_ma20) * 100 if vol_ma20 else 0   # #8

            # 거래대금 (실시간 환율 적용 — 위에서 병렬로 이미 받아온 값 재사용)
            trading_value_usd     = today['Close'] * today['Volume']
            trading_value_krw_eok = (trading_value_usd * usd_krw) / 100_000_000   # #2 실시간 환율

            # #7 52주 최고/최저
            high_52w = hist['High'].max()
            low_52w  = hist['Low'].min()

            # 나스닥 $1 컴플라이언스 추정 (spike_df/offering_list는 위에서 병렬로 이미 수집됨)
            nasdaq_compliance = calc_nasdaq_compliance(hist, today['Close'])

            # 급등주 검색기·즐겨찾기 스캔과 동일 기준의 종합점수 산출
            pct_change_now = ((today['Close'] - yesterday['Close']) / yesterday['Close']) * 100
            current_rsi_val = today['RSI']
            current_rsi = round(float(current_rsi_val), 1) if pd.notna(current_rsi_val) else None
            ticker_score = calc_screener_score({
                "pct_change":        pct_change_now,
                "vol_ma20_ratio":    vol_ma20_ratio,
                "trading_value_eok": trading_value_krw_eok,
                "vol_ratio":         vol_ratio,
                "rsi":               current_rsi,
            })

            # #개선 PC 와이드 모드 제거에 따라 단일 컬럼 레이아웃만 사용 —
            # 상단 요약 카드는 build_top_summary_cards_html()로 뽑아 기술분석
            # 카드와 합쳐서 하나의 metric-grid로 렌더링한다.
            top_cards_front, top_cards_end = build_top_summary_cards_html(today, yesterday, hist, vol_ma20_ratio, score=ticker_score)
            render_technical_analysis(
                active_ticker, hist, today, yesterday,
                vol_ratio, vol_ma20_ratio,
                trading_value_krw_eok, TRADING_THRESHOLD,
                high_52w, low_52w,
                spike_df, offering_list, nasdaq_compliance,
                top_cards_front=top_cards_front, top_cards_end=top_cards_end,
                short_interest=short_interest, execution_strength=execution_strength,
            )
            st.markdown("---")
            info_view = st.segmented_control(
                "정보 보기",
                ["📰 뉴스 & 호재", "💬 소셜 미디어", "📷 차트 해석"],
                default="📰 뉴스 & 호재",
                required=True,
                key="info_view",
                label_visibility="collapsed",
            )
            if info_view == "📰 뉴스 & 호재":
                render_news_section(active_ticker)
            elif info_view == "💬 소셜 미디어":
                render_social_section(active_ticker)
            else:
                render_chart_interpretation(active_ticker, hist, float(today['Close']))