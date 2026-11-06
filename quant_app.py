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
    [style*="color:#34d399"],  [style*="color: #34d399"]  { color: #047857 !important; }
    [style*="color:#6ee7b7"],  [style*="color: #6ee7b7"]  { color: #059669 !important; }
    [style*="color:#a7f3d0"],  [style*="color: #a7f3d0"]  { color: #0d9488 !important; }
    [style*="color:#f87171"],  [style*="color: #f87171"]  { color: #dc2626 !important; }
    [style*="color:#ef4444"],  [style*="color: #ef4444"]  { color: #b91c1c !important; }
    [style*="color:#fca5a5"],  [style*="color: #fca5a5"]  { color: #b91c1c !important; }
    [style*="color:#fecaca"],  [style*="color: #fecaca"]  { color: #991b1b !important; }
    [style*="color:#fbbf24"],  [style*="color: #fbbf24"]  { color: #92600a !important; }
    [style*="color:#e0943a"],  [style*="color: #e0943a"]  { color: #92600a !important; }
    [style*="color:#9c7ff2"],  [style*="color: #9c7ff2"]  { color: #6d28d9 !important; }
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
    "show_vol_surge":   False,          # 거래량 급증 스크리너 토글
    "screener_results": [],
    "has_searched":     False,          # #15 검색 실행 여부 — 기간 변경 등 리렌더링 후에도 결과 유지
    "active_ticker":    "",             # #15 마지막으로 검색을 실행한 티커
    "dark_mode":        False,          # (미사용) 뉴브루탈리즘 단일 테마
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
def fetch_volume_surge_candidates(min_price: float, max_price: float,
                                   min_day_volume: int, limit: int = 250) -> list:
    """
    거래량 급증(최근 3일 평균 / 최근 3개월 평균 비율) 스크리너의 1차 후보군을 조회합니다.

    Yahoo 공식 스크리너(yf.screen)에는 "N일 평균 대비 배율" 같은 비율 필드가
    없으므로, 1차로는 나스닥 상장(NMS/NGM/NCM) 종목 중 당일 거래량이 많은
    순으로 넉넉히(기본 250개) 후보를 뽑아온 뒤, enrich_screener_results()에서
    실제 과거 OHLCV를 내려받아 3일/3개월 평균 거래량 비율을 정밀 계산합니다.
    """
    try:
        query = EquityQuery('and', [
            EquityQuery('is-in', ['exchange', 'NMS', 'NGM', 'NCM']),
            EquityQuery('gte', ['intradayprice', min_price]),
            EquityQuery('lte', ['intradayprice', max_price]),
            EquityQuery('gt',  ['dayvolume',     min_day_volume]),
        ])
        result = yf.screen(query, sortField='dayvolume', sortAsc=False, size=limit)
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
            vol_ma20  = today['VOL_MA20'] if today['VOL_MA20'] > 0 else 1
            vol_ma20_ratio = (today['Volume'] / vol_ma20) * 100

            # #신규 최근 3일 평균 거래량 vs 최근 3개월(약 63거래일) 평균 거래량 비율
            # — 거래량 급증 스크리너("3개월 평균 대비 3일 거래량 N배") 용.
            vol_3d = float(hist['Volume'].tail(3).mean()) if len(hist) >= 3 else 0.0
            vol_3m_window = hist['Volume'].tail(63) if len(hist) >= 20 else hist['Volume']
            vol_3m = float(vol_3m_window.mean()) if len(vol_3m_window) > 0 else 0.0
            vol_surge_ratio = round(vol_3d / vol_3m, 2) if vol_3m > 0 else 0.0

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
                "vol_3d":            round(vol_3d, 0),
                "vol_3m":            round(vol_3m, 0),
                "vol_surge_ratio":   vol_surge_ratio,
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
    df['MA5']   = c.rolling(5,   min_periods=1).mean()
    df['MA20']  = c.rolling(20,  min_periods=1).mean()
    df['MA120'] = c.rolling(120, min_periods=1).mean()

    # #8 거래량 20일 이동평균
    df['VOL_MA20'] = df['Volume'].rolling(20, min_periods=1).mean()

    # RSI (14일)
    delta = c.diff()
    gain  = delta.clip(lower=0).rolling(14, min_periods=1).mean()
    loss  = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
    rs    = gain / loss.replace(0, float('nan'))
    df['RSI'] = 100 - (100 / (1 + rs))

    # 볼린저밴드 (20일, ±2σ)
    mid            = c.rolling(20, min_periods=1).mean()
    std            = c.rolling(20, min_periods=1).std()
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
                       heavy_mult: float = 1.3, max_zones: int = 4) -> dict:
    """
    최근 lookback_days(기본 1년) 동안의 일별 High~Low 구간에 그날의 거래량을
    균등 분산시켜 '거래량 프로파일(Volume Profile)'을 만든 뒤, 현재가보다 위쪽에서
    평균 대비 거래량이 몰려있는 가격대(=매물대, 이전 매수자들의 평단가 밀집구간)를
    현재가에 가까운 순으로 추출한다.

    #개선 render_technical_analysis()와 render_chart_interpretation()이
    동일한 (hist, current_price, 파라미터) 조합으로 매번 이 함수를 중복 호출하고
    있었음 → st.cache_data로 캐싱해 같은 화면 렌더링 내 중복 계산을 제거.
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
    for group in zones:
        g_low  = bin_edges[group[0]]
        g_high = bin_edges[group[-1] + 1]
        g_vol  = bin_vols[group].sum()
        g_mid  = float((bin_mids[group] * bin_vols[group]).sum() / g_vol) if g_vol > 0 else float(np.mean([g_low, g_high]))
        pct_of_total = g_vol / total_volume * 100
        gap_pct = (g_mid - current_price) / current_price * 100
        avg_bin_in_zone = avg_vol * len(group)
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
    if 50 <= rsi_val <= 75:
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
            ("수급 압력",     pressure_score, 30.0, f"거래량 MA20 대비 {vol_ma20_ratio:.0f}% · RSI {rsi_val:.0f}"),
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
# 소셜 미디어 — StockTwits & Reddit
# ════════════════════════════════════════════════════════════════
@st.cache_data(ttl=300, show_spinner=False)
def fetch_reddit(ticker: str) -> list:
    """
    Reddit 공개 검색 API(로그인 불필요)로 주요 투자 서브레딧에서 티커 언급
    게시물을 수집. StockTwits 메시지와 동일한 스키마(user/body/body_en/
    sentiment/likes/date/link)로 정규화해 render_social_section에서
    같은 카드 UI로 그대로 렌더링할 수 있게 한다.

    Reddit은 OAuth 앱 등록 없이도 www.reddit.com/.../search.json 형태의
    공개 read-only 엔드포인트를 제공하지만, User-Agent가 없거나 너무
    범용적이면 429(rate limit)를 반환하는 경우가 있어 구체적인 UA를 지정.
    """
    subreddits = "wallstreetbets+stocks+investing+StockMarket+options"
    url = f"https://www.reddit.com/r/{subreddits}/search.json"
    params = {"q": ticker, "restrict_sr": "on", "sort": "new", "limit": 15, "t": "week"}
    headers = {"User-Agent": "quant-app-dashboard/1.0 (personal research tool; contact via app)"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=6)
        if resp.status_code != 200:
            return []
        posts = resp.json().get("data", {}).get("children", [])
    except Exception:
        return []

    # #참고 StockTwits처럼 감성 라벨을 API가 주지 않으므로, 제목+본문에 대한
    # 간단한 키워드 휴리스틱으로 Bullish/Bearish를 근사 분류한다.
    POS_KW = {"bull", "bullish", "moon", "calls", "buy", "long", "squeeze",
              "breakout", "rip", "printing", "green", "upgrade", "beat", "yolo"}
    NEG_KW = {"bear", "bearish", "puts", "short", "sell", "dump", "crash",
              "red", "downgrade", "miss", "bagholder", "rug", "tank"}

    ticker_lower = ticker.lower()
    entries = []
    for child in posts:
        d = child.get("data", {}) or {}
        title = (d.get("title") or "").strip()
        if not title:
            continue
        selftext = (d.get("selftext") or "").strip()
        haystack = f"{title} {selftext}".lower()
        # 검색 API가 가끔 티커와 무관한 결과를 섞어 반환하므로 재확인
        if ticker_lower not in haystack and f"${ticker_lower}" not in haystack:
            continue
        words   = set(re.findall(r"[a-z']+", haystack))
        is_bull = bool(words & POS_KW)
        is_bear = bool(words & NEG_KW)
        sentiment = "Bullish" if (is_bull and not is_bear) else ("Bearish" if (is_bear and not is_bull) else "")
        body_en = title if len(selftext) < 5 else f"{title} — {selftext[:220]}".strip()
        created = d.get("created_utc")
        entries.append({
            "user":      d.get("author", "익명"),
            "subreddit": d.get("subreddit", ""),
            "body_en":   body_en[:400],
            "sentiment": sentiment,
            "likes":     d.get("ups", 0) or 0,
            "comments":  d.get("num_comments", 0) or 0,
            "date":      datetime.utcfromtimestamp(created).strftime("%Y-%m-%d") if created else "",
            "link":      f"https://reddit.com{d.get('permalink')}" if d.get("permalink") else "",
        })
        if len(entries) >= 8:
            break

    if not entries:
        return []

    translations = translate_texts_batch([e["body_en"] for e in entries])
    for e in entries:
        e["body"] = translations.get(e["body_en"], e["body_en"])
    return entries


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
    POS_KW = {"beat", "bullish", "surge", "soar", "rally", "up", "gain", "buy",
              "upgrade", "strong", "growth", "profit", "record", "positive"}
    NEG_KW = {"miss", "bearish", "drop", "fall", "decline", "cut", "downgrade",
              "loss", "weak", "lawsuit", "fraud", "sell", "negative", "concern"}

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

    # ── Reddit (wallstreetbets / stocks / investing 등) ──────────
    st.markdown(
        f'''<div class="section-header" style="margin-top:1rem;">
            {mono_icon_badge("rocket", color="var(--c-orange)", size=26, glyph_size=13)}
            <div class="section-title" style="color:var(--c-orange);font-size:0.88rem;">Reddit 투자자 의견</div>
        </div>''',
        unsafe_allow_html=True,
    )

    with st.spinner("Reddit 실시간 데이터 수집 중..."):
        reddit_posts = fetch_reddit(ticker_input)

    if not reddit_posts:
        st.markdown(
            '''<div class="glass-card"><div class="status-row"><div class="status-item">
                <div class="status-dot dot-yellow"></div>
                <div class="status-text">최근 1주일 내 관련 Reddit 게시물을 찾지 못했습니다 (wallstreetbets · stocks · investing · StockMarket · options 서브레딧 기준).</div>
            </div></div></div>''',
            unsafe_allow_html=True,
        )
    else:
        for post in reddit_posts:
            sent = post["sentiment"]
            if sent == "Bullish":
                card_cls = "social-card social-bull"
                badge    = '<span class="bull-badge">🟢 Bullish</span>'
            elif sent == "Bearish":
                card_cls = "social-card social-bear"
                badge    = '<span class="bear-badge">🔴 Bearish</span>'
            else:
                card_cls = "social-card"
                badge    = ""

            likes_val    = post.get("likes", 0)
            comments_val = post.get("comments", 0)
            stats_bits = []
            if likes_val:
                stats_bits.append(f'<span>⬆️ {likes_val}</span>')
            if comments_val:
                stats_bits.append(f'<span>💬 {comments_val}</span>')
            stats_html = "".join(stats_bits)

            sub_name    = post.get("subreddit", "")
            user_name   = post.get("user", "익명")
            post_date   = post.get("date", "")
            post_body   = post.get("body", "")
            post_body_en = post.get("body_en", "")
            post_link   = post.get("link", "")

            date_html = f'<span>·</span><span>{post_date}</span>' if post_date else ""
            body_en_html = (f'<div style="font-size:0.75rem;color:rgba(148,163,184,0.45);margin-top:0.25rem;font-style:italic;">{post_body_en}</div>'
                            if post_body_en else "")
            source_html = (f'<span class="reddit-badge">r/{sub_name}</span>{badge}'
                            f'<span>u/{user_name}</span>{date_html}')

            card_html = (
                f'<div class="{card_cls}">' +
                f'<div class="social-meta">{source_html}</div>' +
                f'<div class="social-body">{post_body}</div>' +
                body_en_html +
                f'<div class="social-stats">' +
                stats_html +
                (f'<a href="{post_link}" target="_blank" style="color:rgba(148,163,184,0.4);text-decoration:none;font-size:0.72rem;">원문 보기 →</a>' if post_link else "") +
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
CSS_TEMPLATE = r"""<style>
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
        color: ${text_muted};
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
        color: ${text_muted};
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
    .metric-label { font-size: 0.7rem; color: ${metric_label}; font-weight: 600; letter-spacing: 0.8px; text-transform: uppercase; margin-bottom: 0.35rem; }
    .metric-value { font-size: 1.6rem; font-weight: 800; color: ${text_primary}; line-height: 1; font-family: var(--font-mono); }
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
    .status-text { font-size: 0.82rem; color: ${text_status}; flex: 1; line-height: 1.4; }
    .status-text strong { color: ${text_primary}; }

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
    .news-meta { font-size: 0.7rem; color: ${text_muted}; margin-bottom: 0.4rem; display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
    .news-title { font-size: 0.9rem; font-weight: 600; color: ${text_primary}; line-height: 1.45; margin-bottom: 0.35rem; }
    .news-orig  { font-size: 0.72rem; color: ${text_dimmed}; margin-bo