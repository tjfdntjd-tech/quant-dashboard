# ════════════════════════════════════════════════════════════════
# Part 1 / 파일 시작 ~ 환율 조회
# ════════════════════════════════════════════════════════════════
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
import threading
from datetime import datetime, timedelta, timezone
from deep_translator import GoogleTranslator, MyMemoryTranslator
from concurrent.futures import ThreadPoolExecutor, as_completed
from string import Template
import time
import logging
import html as _html_lib

_logger = logging.getLogger("quant_app")


def _redact(text) -> str:
    """오류 문구에 섞여 들어갈 수 있는 API 키(?key=..., AIza...)를 가린다."""
    s = str(text)
    s = re.sub(r"(key=)[^&\s'\")]+", r"\1***", s)
    s = re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "AIza***", s)
    return s


def _log_err(where: str, exc: Exception) -> None:
    """삼키던 예외를 서버 로그(Manage app → Logs)에 남긴다. 화면 동작은 바꾸지 않는다."""
    try:
        _logger.warning("[%s] %s: %s", where, type(exc).__name__, _redact(exc))
    except Exception:
        pass


def _safe_error_text(exc: Exception) -> str:
    """화면(HTML)에 출력해도 안전하도록 키를 가리고 특수문자를 이스케이프한 오류 문구."""
    return _html_lib.escape(_redact(exc))


def _classify_error(exc: Exception) -> str:
    """예외를 사용자가 이해할 수 있는 종류로 분류한다."""
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    if "ratelimit" in name or "too many requests" in msg or "429" in msg or "rate limit" in msg:
        return "요청 제한(잠시 후 재시도)"
    if (isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError))
            or "timed out" in msg or "connection" in msg or "max retries" in msg):
        return "네트워크 오류"
    if isinstance(exc, (KeyError, IndexError, ValueError, ZeroDivisionError, TypeError, AttributeError)):
        return "계산 오류"
    return "분석 오류"


def _safe_html(text) -> str:
    """외부에서 온 텍스트를 HTML에 안전하게 넣기 위한 변환.
    - <, >, &, 따옴표 이스케이프
    - $ 를 엔티티로 바꿔 마크다운이 $...$ 를 수식으로 오인식하는 것 방지"""
    return _html_lib.escape(str(text if text is not None else ""), quote=True).replace("$", "&#36;")


def _safe_url(url) -> str:
    """http(s) 링크만 허용하고 속성값으로 안전하게 이스케이프. 그 외(javascript: 등)는 빈 문자열."""
    u = str(url or "").strip()
    return _html_lib.escape(u, quote=True) if u.lower().startswith(("http://", "https://")) else ""


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
    except Exception as _e:
        _log_err("fetch_usd_to_krw", _e)
        return 1400.0  # 폴백: 조회 실패 시 고정값 사용

# 거래대금 기준 (억 원)
# 기존 500억(약 $3,700만)은 소형주 단타에는 문턱이 너무 높아서 70억(약 $500만)으로 낮춤.
# (환율 1,400원 기준 $500만 ≈ 70억 원. 포지션이 크면 270억(≈$2천만) 이상을 권장)
TRADING_THRESHOLD = 70

# 스윙용 신호(MACD·RSI 과매도·120일선·20일선 돌파)를 "급등 신호 알림 칩"에 표시할지 여부.
# 단타(소형 급등주)에서는 후행/장기 지표라 기본 False. True로 바꾸면 예전처럼 칩에 다시 표시됩니다.
SHOW_SWING_SIGNALS = False

# ════════════════════════════════════════════════════════════════
# #개선 번역 캐시 영구 저장 파일 (TTL 만료로 인한 재번역 방지)
# ════════════════════════════════════════════════════════════════
TRANSLATE_CACHE_FILE = "translate_cache.json"
# ════════════════════════════════════════════════════════════════
# Part 2 / 라이트 모드 CSS ~ 메모·즐겨찾기 저장
# ════════════════════════════════════════════════════════════════

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
# 즐겨찾기 영구 저장 헬퍼
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
    except Exception as _e:
        _log_err("load_favorites", _e)
        pass
    return []

def save_favorites(favorites: list) -> None:
    """즐겨찾기를 JSON 파일로 저장합니다."""
    try:
        with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(favorites, f, ensure_ascii=False, indent=2)
    except Exception as _e:
        _log_err("save_favorites", _e)
        pass
# ════════════════════════════════════════════════════════════════
# Part 3 / 페이지 설정 ~ 나스닥 $1 규정 추정
# ════════════════════════════════════════════════════════════════

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
    "scan_results":     [],
    "show_heatmap":     False,          # 섹터 히트맵 토글 (사이드바 버튼보다 먼저 초기화)
    "show_screener":    False,          # 급등주 검색기 토글
    "show_vol_surge":   False,          # 거래량 급증 스크리너 토글
    "show_prebreak":    False,          # 급등 전 매집 스캐너 토글
    "excl_delisted":    True,           # 상장폐지 확정·청산·OTC 이전 종목 제외
    "excl_acquired":    True,           # 피인수(합병 확정) 종목 제외
    "excel_scan":       None,           # 엑셀 종목 일괄 분석 결과
    "screener_results": [],
    "has_searched":     False,          # #15 검색 실행 여부 — 기간 변경 등 리렌더링 후에도 결과 유지
    "active_ticker":    "",             # #15 마지막으로 검색을 실행한 티커
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
    except Exception as _e:
        _log_err("fetch_top_gainers", _e)
        return []

@st.cache_data(ttl=60, show_spinner=False)
def fetch_premarket_gappers(min_gap: float, min_price: float, max_price: float,
                            min_pm_volume: int, max_cap_m: int = 0, limit: int = 150) -> list:
    """
    프리마켓(04:00~09:30 ET) 갭 상승 종목을 찾습니다.

    왜 따로 만들었나? 기존 1차 검색(yf.screen의 등락률)은 정규장 기준이라
    장 시작 전에는 '어제' 등락률이 나옵니다. 그래서 다음 2단계로 찾습니다.
      1단계) 야후 스크리너로 후보 종목 수집 (주가 범위 · 3개월 평균거래량 20만 주 이상 · 시총 상한)
             - 어제 상승률 순 + 평균거래량 순, 두 목록을 합쳐 넉넉히 모음
      2단계) 후보마다 프리마켓 1분봉을 받아 '전일 종가 대비 갭 %'와 '프리마켓 누적 거래량'을 직접 계산
    반환 행의 pct_change = 프리마켓 갭(%), volume = 프리마켓 거래량 → 기존 표/점수 로직을 그대로 재사용.
    ⚠️ 야후 필드/응답이 바뀌면 후보 수가 줄 수 있어, 실패 시 서버 로그에 원인을 남깁니다.
    """
    conds = [
        EquityQuery('eq', ['region', 'us']),
        EquityQuery('is-in', ['exchange', 'NMS', 'NGM', 'NCM', 'NYQ', 'ASE']),
        EquityQuery('gte', ['intradayprice', min_price]),
        EquityQuery('lte', ['intradayprice', max_price * 1.5]),   # 갭 전 가격이 범위 밖일 수 있어 여유를 둠
        EquityQuery('gt', ['avgdailyvol3m', 200_000]),
    ]
    if max_cap_m and max_cap_m > 0:
        conds.append(EquityQuery('lte', ['intradaymarketcap', int(max_cap_m) * 1_000_000]))
    query = EquityQuery('and', conds)

    cand = {}
    for sort_field in ('percentchange', 'avgdailyvol3m'):
        try:
            res = yf.screen(query, sortField=sort_field, sortAsc=False, size=100)
            for q in (res or {}).get('quotes', []):
                sym = q.get('symbol')
                if sym and sym not in cand:
                    cand[sym] = q
        except Exception as _e:
            _log_err("fetch_premarket_gappers:screen:" + sort_field, _e)
    if not cand:
        return []

    def _pm_stats(sym: str):
        """한 종목의 프리마켓 갭/거래량 계산. 프리마켓 거래가 없으면 None."""
        try:
            raw = yf.Ticker(sym).history(period="5d", interval="1m", prepost=True)
            if raw is None or raw.empty:
                return None
            raw.index = pd.to_datetime(raw.index)
            mins = raw.index.hour * 60 + raw.index.minute      # 하루 중 몇 분째인지 (ET)
            dates = np.array(raw.index.date)
            latest = dates.max()
            is_latest = dates == latest
            pre = raw[is_latest & (mins >= 240) & (mins < 570)]          # 04:00~09:30
            prev_reg = raw[(dates < latest) & (mins >= 570) & (mins < 960)]  # 이전 거래일 정규장
            if pre.empty or prev_reg.empty:
                return None
            prev_close = float(prev_reg["Close"].iloc[-1])
            if prev_close <= 0:
                return None
            last_px = float(pre["Close"].iloc[-1])
            return {
                "pm_gap": (last_px / prev_close - 1) * 100,
                "pm_price": last_px,
                "pm_high": float(pre["High"].max()),
                "pm_volume": int(pre["Volume"].sum()),
                "prev_close": prev_close,
            }
        except Exception as _e:
            _log_err("fetch_premarket_gappers:" + sym, _e)
            return None

    syms = list(cand.keys())[:limit * 2]
    with ThreadPoolExecutor(max_workers=12) as ex:
        stats = list(ex.map(_pm_stats, syms))

    out = []
    for sym, st_ in zip(syms, stats):
        if not st_:
            continue
        # 프리마켓 현재가가 요청한 가격 범위 안인 종목만, 갭/거래량 기준 통과만
        if not (min_price <= st_["pm_price"] <= max_price):
            continue
        if st_["pm_gap"] < min_gap or st_["pm_volume"] < min_pm_volume:
            continue
        q = cand[sym]
        out.append({
            "ticker": sym,
            "name": q.get("shortName") or q.get("longName") or "",
            "price": st_["pm_price"],
            "pct_change": st_["pm_gap"],        # 표/점수에서 등락률 자리에 프리마켓 갭을 넣는다
            "volume": st_["pm_volume"],         # 거래량 자리에 프리마켓 거래량
            "market_cap": q.get("marketCap", 0) or 0,
            "exchange": q.get("fullExchangeName", ""),
            "pm_gap": st_["pm_gap"],
            "pm_volume": st_["pm_volume"],
            "pm_high": st_["pm_high"],
        })
    out.sort(key=lambda r: r["pm_gap"], reverse=True)
    return out[:limit]


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
    except Exception as _e:
        _log_err("fetch_volume_surge_candidates", _e)
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

            # ── 소형 저유통주 단타용 지표 ─────────────────────────
            # 유통주식수(floatShares): 없으면 None으로 두어 "모름"을 표시한다
            float_shares = info.get("floatShares") or None
            market_cap = info.get("marketCap") or None
            # 플로트 회전율(%) = 당일 거래량 ÷ 유통주식수 × 100
            float_turnover = (float(today['Volume']) / float(float_shares) * 100) if float_shares else None
            # 공매도 비율(%) — yfinance는 0.12 같은 소수로 주므로 100을 곱한다 (갱신이 느려 참고용)
            _spf = info.get("shortPercentOfFloat")
            short_pct = round(float(_spf) * 100, 1) if _spf else None

            # 호가 스프레드(%) — 넓으면 체결 손실이 커서 단타에 불리 (장 마감 후에는 값이 없을 수 있음)
            _bid, _ask = info.get("bid") or 0, info.get("ask") or 0
            spread_pct = ((_ask - _bid) / ((_ask + _bid) / 2) * 100) if (_bid and _ask and _ask >= _bid) else None

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
                "float_shares":      float_shares,
                "market_cap_info":   market_cap,
                "float_turnover":    round(float_turnover, 1) if float_turnover is not None else None,
                "short_pct":         short_pct,
                # ── 셋업 점수용: 일봉 마지막 2개 행 정보 (장 시작 전/후에 따라 '전일'이 달라 둘 다 저장) ──
                "atr":               calc_atr(hist),
                "avg_vol20":         float(today['VOL_MA20']) if pd.notna(today['VOL_MA20']) else None,
                "last_high":         float(today['High']),
                "prev2_high":        float(yesterday['High']),
                "last_close":        float(today['Close']),
                "prev2_close":       float(yesterday['Close']),
                "last_pct":          float((today['Close'] / yesterday['Close'] - 1) * 100),
                "last_date":         pd.to_datetime(hist.index[-1]).date(),
                "spread_pct":        spread_pct,
                "error":             False,
            }
        except Exception as _e:
            _log_err("enrich_screener_results", _e)
            return {"ticker": ticker, "error": True, "reason": _classify_error(_e)}

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
        except Exception as _e:
            _log_err("fetch_sector_data", _e)
            return None

    with ThreadPoolExecutor(max_workers=11) as ex:
        results = list(ex.map(_fetch_one, SECTOR_ETFS))
    return [r for r in results if r is not None]

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yahoo_news(ticker: str) -> list:
    """yfinance 뉴스 목록 캐싱 — #14 try/except 추가"""
    try:
        return yf.Ticker(ticker).news or []
    except Exception as _e:
        _log_err("fetch_yahoo_news", _e)
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
    except Exception as _e:
        _log_err("fetch_ticker_info", _e)
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
    except Exception as _e:
        _log_err("fetch_spike_history", _e)
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
    except Exception as _e:
        _log_err("fetch_offering_history", _e)
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
# Part 4 / 리버스 스플릿 감지 ~ 종합점수 계산
# ════════════════════════════════════════════════════════════════

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
# 🤝 합병 · 🏢 인수 · 💀 파산 이벤트 신호
#   뉴스 제목(최근 14일)과 SEC 공시 서식(최근 30일)에서 키워드·서식 종류로 자동 감지한다.
#   키워드 기반이라 다른 회사 소식이 섞이거나 오탐이 있을 수 있어 원문 확인이 필요하다.
# ════════════════════════════════════════════════════════════════
EVENT_NEWS_DAYS = 14
EVENT_SEC_DAYS = 30
EVENT_ORDER = ["bankruptcy", "distress", "target", "merger", "acquisition"]   # 심각도 순
EVENT_LABELS = {          # (신호 토큰, 한글명)
    "bankruptcy":  ("💀파산", "파산"),
    "distress":    ("⚠️파산위험", "파산위험"),
    "target":      ("🎯피인수", "피인수"),
    "merger":      ("🤝합병", "합병"),
    "acquisition": ("🏢인수", "인수"),
}

# 'Foo Acquisition Corp'(SPAC 이름), 'Merger Sub' 같은 상호는 합병·인수 소식이 아니므로 먼저 지운다
_EV_STRIP = re.compile(
    r"\b[\w&.'\-]+\s+(?:acquisition|merger)\s+(?:corp(?:oration)?|co|company|holdings?|ltd|limited|inc|sub(?:sidiary)?)\b\.?",
    re.I)
_EV_BANKRUPT = [re.compile(p, re.I) for p in (
    r"\bbankrupt(?:cy|cies)?\b", r"\bchapter\s*(?:7|11)\b", r"\binsolven(?:cy|t)\b",
    r"\breceivership\b", r"\bvoluntary liquidation\b", r"\bplan of (?:complete )?liquidation\b",
    r"\bliquidat(?:e|ing) (?:the )?company\b")]
_EV_DISTRESS = [re.compile(p, re.I) for p in (
    r"\bgoing[\s-]concern\b", r"\bsubstantial doubt\b", r"\bdelist(?:ing|ed|s)?\b",
    r"\bwind(?:ing)?[\s-]*(?:down|up)\b", r"\bcease[sd]? operations\b")]
_EV_TARGET = [re.compile(p, re.I) for p in (
    r"\bto be (?:acquired|bought|purchased|taken private)\b", r"\bacquired by\b",
    r"\btake[\s-]private\b", r"\bgo(?:ing)?[\s-]private\b", r"\bbuyout\b", r"\btender offer\b",
    r"\bunsolicited (?:offer|proposal|bid)\b")]
_EV_MERGER = [re.compile(p, re.I) for p in (
    r"\bmerg(?:e|er|ers|es|ed|ing)\b", r"\bbusiness combination\b")]
_EV_ACQ_ACTIVE = re.compile(
    r"\b(?:to|will|agrees to|agreed to|completes?|completed|completing|announces?|announced)\s+(?:the\s+)?acquir(?:e|es|ing|ed)\b"
    r"|\bacquires\b|\bacquisition of\b", re.I)
_EV_ACQ_ANY = re.compile(r"\bacquir(?:e|es|ed|ing)\b|\bacquisitions?\b|\btakeover\b", re.I)


def classify_event_text(text) -> list:
    """뉴스 제목 한 줄에서 이벤트 종류(bankruptcy/distress/target/merger/acquisition)를 찾는다."""
    t = _EV_STRIP.sub(" ", str(text or ""))
    cats = []
    if any(p.search(t) for p in _EV_BANKRUPT):
        cats.append("bankruptcy")
    elif any(p.search(t) for p in _EV_DISTRESS):          # 파산이 확정이면 위험 표시는 생략
        cats.append("distress")
    is_target = any(p.search(t) for p in _EV_TARGET)
    if is_target:
        cats.append("target")
    if any(p.search(t) for p in _EV_MERGER):
        cats.append("merger")
    if _EV_ACQ_ACTIVE.search(t) or (not is_target and _EV_ACQ_ANY.search(t)):
        cats.append("acquisition")
    return cats


def classify_sec_form(form_type):
    """SEC 공시 서식 종류로 이벤트를 분류한다. 해당 없으면 None.
    · 합병: S-4/F-4(합병 주식 등록), PREM14A/DEFM14A(합병 위임장), 425(합병 관련 커뮤니케이션)
    · 피인수: 공개매수(SC TO-T/TO-C), 대상회사 의견(SC 14D9), 비상장 전환(SC 13E3)
    · 파산위험: Form 25(상장폐지 통지), Form 15(등록 말소)"""
    t = re.sub(r"[\s\-_/]", "", str(form_type or "").upper())
    if not t:
        return None
    if t.startswith(("S4", "F4", "DEFM14", "PREM14", "425")):
        return "merger"
    if t.startswith(("SCTOT", "SCTOC", "SC14D9", "SC13E3", "SCHEDULETOT", "SCHEDULETOC",
                     "SCHEDULE14D9", "SCHEDULE13E3")):
        return "target"
    if t in {"25", "25NSE", "25NSEA"} or t.startswith(("1512", "1515", "15F")):
        return "distress"
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_sec_filings(ticker: str) -> list:
    """야후가 제공하는 최근 SEC 공시 목록을 (date, type, title, url)로 정리해 캐싱."""
    try:
        filings = yf.Ticker(ticker).sec_filings or []
    except Exception as _e:
        _log_err("fetch_sec_filings:" + ticker, _e)
        return []
    out = []
    for f in filings:
        exhibits = f.get("exhibits") or []
        url = f.get("edgarUrl") or (exhibits[0].get("url") if exhibits else "") or ""
        out.append({"date": f.get("date"), "type": f.get("type") or "",
                    "title": f.get("title") or "", "url": url})
    return out


def _news_dt(raw):
    """yfinance 뉴스 항목의 게재 시각(UTC Timestamp). 알 수 없으면 None."""
    try:
        content = raw.get("content", raw) if isinstance(raw, dict) else {}
        v = content.get("pubDate") or content.get("displayTime")
        if v:
            return pd.to_datetime(v, utc=True)
        ts = raw.get("providerPublishTime") or content.get("providerPublishTime")
        if ts:
            return pd.to_datetime(int(ts), unit="s", utc=True)
    except Exception:
        pass
    return None


def detect_corporate_events(ticker: str, news_days: int = EVENT_NEWS_DAYS,
                            sec_days: int = EVENT_SEC_DAYS) -> dict:
    """최근 뉴스 제목 + SEC 공시 서식에서 합병·인수·피인수·파산·파산위험 이벤트를 감지한다.
    반환: {"signals": ["💀파산", ...], "counts": {카테고리: 건수}, "items": [{category, date, title, source, link}]}"""
    now = pd.Timestamp.now(tz="UTC")
    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    items = []
    try:
        for raw in fetch_yahoo_news(ticker) or []:
            p = parse_yahoo_news_item(raw)
            dt = _news_dt(raw)
            if dt is not None and (now - dt) > pd.Timedelta(days=news_days):
                continue
            for cat in classify_event_text(p.get("title", "")):
                items.append({"category": cat, "date": dt.strftime("%Y-%m-%d") if dt is not None else "",
                              "title": p.get("title", ""), "source": "뉴스",
                              "link": p.get("link", ""), "_dt": dt})
    except Exception as _e:
        _log_err("detect_events_news:" + ticker, _e)
    try:
        for f in fetch_sec_filings(ticker) or []:
            cat = classify_sec_form(f.get("type"))
            if not cat:
                continue
            dt = pd.to_datetime(f.get("date"), utc=True, errors="coerce")
            dt = None if pd.isna(dt) else dt
            if dt is not None and (now - dt) > pd.Timedelta(days=sec_days):
                continue
            ftype = str(f.get("type") or "").strip()
            title = f"SEC {ftype}" + (f" — {f.get('title')}" if f.get("title") else "")
            items.append({"category": cat, "date": dt.strftime("%Y-%m-%d") if dt is not None else "",
                          "title": title, "source": "SEC 공시", "link": f.get("url", ""), "_dt": dt})
    except Exception as _e:
        _log_err("detect_events_sec:" + ticker, _e)

    seen, uniq = set(), []
    for it in sorted(items, key=lambda x: x["_dt"] if x["_dt"] is not None else epoch, reverse=True):
        key = (it["category"], it["title"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    for it in uniq:
        it.pop("_dt", None)
    counts = {c: sum(1 for i in uniq if i["category"] == c) for c in EVENT_ORDER}
    counts = {c: n for c, n in counts.items() if n}
    return {"signals": [EVENT_LABELS[c][0] for c in EVENT_ORDER if c in counts],
            "counts": counts, "items": uniq}


def build_event_banner_html(ev: dict) -> str:
    """이벤트가 감지됐을 때 상단 배너(HTML). 없으면 빈 문자열."""
    if not ev or not ev.get("signals"):
        return ""
    chips = "".join(
        f'<span class="signal-chip">{_html_lib.escape(EVENT_LABELS[c][0])} {ev["counts"][c]}건</span>'
        for c in EVENT_ORDER if c in ev["counts"])
    return (f'<div class="alert-banner"><div class="alert-icon">📰</div><div>'
            f'<div class="alert-title">이벤트 감지 — 합병·인수·파산</div>'
            f'<div class="alert-signals">{chips}</div></div></div>')


def render_event_signals(ev: dict):
    """합병·인수·파산 이벤트 목록 카드 (감지된 뉴스/공시 제목과 링크)."""
    ui_section_header(mono_icon_badge("fire", color="var(--c-rose)"),
                      "합병·인수·파산 이벤트 신호", "icon-rose", "title-rose")
    if not ev or not ev.get("items"):
        st.caption(f"최근 뉴스 {EVENT_NEWS_DAYS}일 · SEC 공시 {EVENT_SEC_DAYS}일 안에 "
                   "합병·인수·파산 관련 키워드는 감지되지 않았습니다.")
        return
    dots = {"bankruptcy": "dot-red", "distress": "dot-yellow", "target": "dot-blue",
            "merger": "dot-blue", "acquisition": "dot-blue"}
    rows = ""
    for it in ev["items"][:8]:
        title = _html_lib.escape(str(it.get("title", "")))
        link = str(it.get("link") or "")
        if link.startswith(("http://", "https://")):
            title = (f'<a href="{_html_lib.escape(link, quote=True)}" target="_blank" rel="noopener" '
                     f'style="color:inherit;text-decoration:underline;">{title}</a>')
        label = _html_lib.escape(EVENT_LABELS[it["category"]][1])
        rows += (f"<div class='status-item'><div class='status-dot {dots[it['category']]}'></div>"
                 f"<div class='status-text'><strong>{label}</strong> · {it.get('date') or '날짜 미상'} · "
                 f"{_html_lib.escape(it.get('source', ''))} — {title}</div></div>")
    st.markdown(
        '<div class="glass-card"><div class="status-row" '
        f'style="flex-direction:column;align-items:stretch;gap:0.5rem;">{rows}</div></div>',
        unsafe_allow_html=True)
    st.caption("키워드·공시 서식 기반 자동 감지입니다. 다른 회사 소식이 섞이거나 오탐일 수 있으니 원문을 확인하세요.")


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
    except Exception as _e:
        _log_err("_load_translate_cache", _e)
        pass
    return {}

def _save_translate_cache(cache: dict) -> None:
    try:
        with open(TRANSLATE_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception as _e:
        _log_err("_save_translate_cache", _e)
        pass

def _needs_translation(text: str) -> bool:
    """티커($XXX)·URL을 뺀 뒤 영어 단어가 남아 있고 한글이 없을 때만 번역 대상."""
    plain = re.sub(r"\$[A-Za-z.\-]+|https?://\S+", " ", text or "")
    return bool(re.search(r"[A-Za-z]{3,}", plain)) and not re.search(r"[가-힣]", plain)

def _translate_via_gemini(texts: list, api_key: str) -> dict:
    """구글/마이메모리 번역이 모두 실패했을 때의 최후 수단 — Gemini로 한 번에 일괄 번역."""
    if not texts or not api_key:
        return {}
    prompt = ("다음 영어 투자자 글 목록을 자연스러운 한국어로 번역하세요. "
              "티커($XXX), 숫자, 고유명사는 그대로 두세요. "
              "입력과 같은 길이·순서의 JSON 문자열 배열만 출력하세요.\n"
              + json.dumps(texts, ensure_ascii=False))
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json",
                             "maxOutputTokens": 4000,
                             "thinkingConfig": {"thinkingBudget": 0}},
    }
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{CHART_ANALYSIS_MODEL}:generateContent")
    try:
        r = requests.post(url, json=payload, timeout=40,
                          headers={"x-goog-api-key": api_key})
        if r.status_code != 200:
            return {}
        parts = r.json()["candidates"][0]["content"]["parts"]
        arr = json.loads("".join(p.get("text", "") for p in parts))
        if isinstance(arr, list) and len(arr) == len(texts):
            return {t: str(k).strip() for t, k in zip(texts, arr) if str(k).strip()}
    except Exception as _e:
        _log_err("_translate_via_gemini", _e)
        pass
    return {}

@st.cache_resource
def _get_translate_store() -> dict:
    """번역 캐시 저장소 — 세션이 아닌 프로세스 전역(스레드에서도 접근 가능)."""
    loaded = _load_translate_cache()
    data = {k: v for k, v in loaded.items() if not (k == v and _needs_translation(k))}
    return {"data": data, "lock": threading.Lock()}


def translate_texts_batch(texts: list, api_key=None) -> dict:
    """
    여러 문장을 병렬 번역하고 {원문: 번역문}을 반환합니다.
    워커 스레드에서도 호출되므로 st.session_state를 쓰지 않습니다.
    api_key는 호출부(메인 스레드)에서 넘겨주세요. None이면 세션에서 읽기를 시도합니다.

    번역 API가 실패해도 원문을 성공한 번역처럼 캐시하지 않습니다.
    구글 번역 → MyMemory → (Gemini 키가 있으면) Gemini 순으로 폴백.
    """
    if api_key is None:
        try:
            api_key = st.session_state.get("gemini_api_key", "")
        except Exception:
            api_key = ""

    store = _get_translate_store()
    cache, lock = store["data"], store["lock"]

    unique_texts = list(dict.fromkeys(t for t in texts if t))
    with lock:
        to_translate = [t for t in unique_texts if t not in cache and _needs_translation(t)]

    if to_translate:
        def _do(t: str):
            try:
                out = GoogleTranslator(source='en', target='ko').translate(t)
                if out and out.strip() and out.strip() != t.strip():
                    return t, out
            except Exception as _e:
                _log_err("translate_texts_batch", _e)
            if len(t) <= 480:
                try:
                    out = MyMemoryTranslator(source='en-US', target='ko-KR').translate(t)
                    if out and out.strip() and out.strip() != t.strip():
                        return t, out
                except Exception as _e:
                    _log_err("translate_texts_batch", _e)
            return t, None

        results, failed = {}, []
        with ThreadPoolExecutor(max_workers=min(8, len(to_translate))) as ex:
            for original, translated in ex.map(_do, to_translate):
                if translated:
                    results[original] = translated
                else:
                    failed.append(original)
        if failed:
            results.update(_translate_via_gemini(failed, api_key or ""))

        with lock:
            cache.update(results)
            snapshot = dict(cache)
        _save_translate_cache(snapshot)   # 배치당 1회 저장

    with lock:
        return {t: cache.get(t, t) for t in unique_texts}

def translate_text(text: str) -> str:
    """단일 문장 번역 — 내부적으로 translate_texts_batch()를 재사용합니다."""
    if not text:
        return text
    return translate_texts_batch([text]).get(text, text)

# ════════════════════════════════════════════════════════════════
# 이벤트 빔(병합빔 / 인수빔 / 파산빔) 감지
# strong = 확정적 표현, weak = 관련 가능성(주체 확인 필요)
# ════════════════════════════════════════════════════════════════
_BEAM_RULES = {
    "병합빔": {
        "desc": "주식병합(리버스 스플릿)",
        "strong": [r"reverse\s+(?:stock\s+)?split", r"share\s+consolidation",
                   r"주식\s*병합", r"역병합", r"리버스\s*스플릿"],
        "weak": [],
    },
    "인수빔": {
        "desc": "인수·합병·공개매수",
        "strong": [r"to\s+be\s+acquired", r"acquired\s+by", r"merger\s+agreement",
                   r"tender\s+offer", r"take[-\s]?private", r"\bbuyout\b",
                   r"go(?:ing)?\s+private", r"공개매수"],
        "weak": [r"\bacquisition\b", r"\bto\s+acquire\b", r"\bacquires?\b", r"takeover",
                 r"definitive\s+agreement", r"business\s+combination", r"\bmerger\b",
                 r"인수", r"합병"],
    },
    "파산빔": {
        "desc": "파산·회생 절차",
        "strong": [r"chapter\s+(?:7|11)\b", r"files?\s+for\s+bankruptcy",
                   r"\bbankruptcy\b", r"파산", r"법정관리", r"회생\s*절차"],
        "weak": [r"insolvency", r"receivership", r"\bbankrupt\b", r"liquidation"],
    },
}
_BEAM_COMPILED = {
    k: {"desc": v["desc"],
        "strong": [re.compile(p, re.I) for p in v["strong"]],
        "weak":   [re.compile(p, re.I) for p in v["weak"]]}
    for k, v in _BEAM_RULES.items()
}


def get_beam_news(ticker: str) -> list:
    """빔 감지용 뉴스 수집: 스톡타이탄(최대 3건) + 야후 헤드라인(최대 10건, 14일 이내)."""
    items, seen = [], set()
    for n in (get_stock_titan_data(ticker) or []):
        key = (n.get("title_en") or "").lower()
        if key and key not in seen:
            seen.add(key)
            items.append({"title": n.get("title", ""), "title_en": n.get("title_en", ""),
                          "link": n.get("link", ""), "date": n.get("date", "")})
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    for raw in (fetch_yahoo_news(ticker) or [])[:10]:
        p = parse_yahoo_news_item(raw)
        title = p["title"]
        if not title or title == "제목 없음" or title.lower() in seen:
            continue
        pub = (raw.get("content", raw) or {}).get("pubDate") or ""
        try:
            if pub and datetime.fromisoformat(pub.replace("Z", "+00:00")) < cutoff:
                continue
        except Exception:
            pass
        seen.add(title.lower())
        items.append({"title": title, "title_en": title, "link": p["link"], "date": pub[:10]})
    return items


def detect_event_beams(news_items: list) -> list:
    """뉴스 제목에서 병합/인수/파산 이슈를 찾는다. 종류별로 가장 확실한(strong 우선) 1건씩 반환."""
    found = {}
    for n in news_items:
        text = " ".join(filter(None, [n.get("title", ""), n.get("title_en", "")]))
        if not text:
            continue
        for kind, rule in _BEAM_COMPILED.items():
            strong = any(p.search(text) for p in rule["strong"])
            weak = (not strong) and any(p.search(text) for p in rule["weak"])
            if not (strong or weak):
                continue
            cur = found.get(kind)
            if cur is None or (strong and not cur["strong"]):
                found[kind] = {"kind": kind, "desc": rule["desc"], "strong": strong,
                               "title": n.get("title") or n.get("title_en", ""),
                               "link": n.get("link", ""), "date": n.get("date", "")}
    return list(found.values())


def fetch_beam_titles(ticker: str) -> list:
    """스캔용 경량 뉴스 수집: 야후 헤드라인만(14일 이내). 워커 스레드에서도 호출 가능."""
    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    for raw in (fetch_yahoo_news(ticker) or [])[:10]:
        p = parse_yahoo_news_item(raw)
        title = p["title"]
        if not title or title == "제목 없음":
            continue
        pub = (raw.get("content", raw) or {}).get("pubDate") or ""
        try:
            if pub and datetime.fromisoformat(pub.replace("Z", "+00:00")) < cutoff:
                continue
        except Exception:
            pass
        items.append({"title": title, "title_en": title, "link": p["link"], "date": pub[:10]})
    return items


def beam_signal_text(ticker: str) -> str:
    """종목 하나의 빔 신호 문자열. 없으면 ''. 예: '🧨병합빔 🧨파산빔(?)'  (?)=관련 가능성"""
    try:
        evs = detect_event_beams(fetch_beam_titles(ticker))
    except Exception as _e:
        _log_err("beam_signal_text:" + ticker, _e)
        return ""
    return " ".join(f"🧨{e['kind']}" + ("" if e["strong"] else "(?)") for e in evs)


def is_surge_candidate(pct: float, vol_ma20_r: float, gap_pct: float = 0.0) -> bool:
    return pct >= 5 or vol_ma20_r >= 200 or gap_pct >= 5


def attach_beams(rows: list, ticker_key: str, signal_key: str, cand_flags: list,
                 max_workers: int = 6, limit: int = 40) -> None:
    """cand_flags[i]가 True인 행만 병렬로 뉴스를 조회해 rows[i][signal_key]에 빔 문자열을 덧붙인다."""
    idxs = [i for i, f in enumerate(cand_flags) if f][:limit]
    if not idxs:
        return

    def _one(i):
        t = str(rows[i][ticker_key]).replace("⚠️ ", "").strip()
        return i, beam_signal_text(t)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for i, txt in ex.map(_one, idxs):
            if txt:
                cur = rows[i].get(signal_key, "—")
                rows[i][signal_key] = txt if cur in ("—", "", None) else f"{cur} {txt}"
# ════════════════════════════════════════════════════════════════
# 재료(촉매) 분류 + 뉴스 신선도 — 단타는 "재료가 있는 종목"만 후보로 본다
# 야후 뉴스 제목의 영어 키워드로 종류를 나누고, 몇 시간 전 뉴스인지 함께 계산합니다.
# ⚠️ 키워드 기반 자동 분류라 오분류가 있을 수 있어 원문 확인이 필요합니다.
# ════════════════════════════════════════════════════════════════
# (분류 키, 표시 이름, 호재 여부, 정규식 목록) — 위에 있을수록 우선순위가 높다(오퍼링은 악재라 맨 앞)
_CATALYST_RULES = [
    ("offering", "💸오퍼링", False, [r"\boffering\b", r"\bregistered direct\b", r"\bprivate placement\b",
                                    r"\bat[\s-]the[\s-]market\b", r"\bwarrants?\b.*\bpric", r"\bpricing of\b",
                                    r"\bshelf (?:registration|offering)\b"]),
    ("fda", "🧬FDA·임상", True, [r"\bFDA\b", r"\bclinical (?:trial|data|study)\b", r"\bphase\s*(?:1|2|3|I|II|III)\b",
                                r"\btopline\b", r"\bPDUFA\b", r"\bNDA\b", r"\bBLA\b", r"\borphan drug\b",
                                r"\bbreakthrough therapy\b", r"\bfast track\b"]),
    ("contract", "📝계약·수주", True, [r"\bcontracts?\b", r"\bawarded?\b", r"\bpurchase order\b", r"\bagreement\b",
                                      r"\bpartnership\b", r"\bcollaborat", r"\blicens(?:e|ing) (?:deal|agreement)\b",
                                      r"\bsecures?\b", r"\bwins?\b.*\b(?:order|contract)\b"]),
    ("earnings", "📊실적", True, [r"\bearnings\b", r"\bquarter(?:ly)? (?:results|revenue)\b", r"\bQ[1-4]\b",
                                r"\bguidance\b", r"\brevenue (?:grew|rose|jumps|up)\b", r"\bEPS\b"]),
    ("analyst", "🎯애널리스트", True, [r"\bupgrad", r"\bprice target\b", r"\binitiates? coverage\b"]),
]
_CATALYST_COMPILED = [(k, label, good, [re.compile(p, re.I) for p in pats])
                      for k, label, good, pats in _CATALYST_RULES]


def classify_catalyst(text: str):
    """뉴스 제목 한 줄 → (분류 키, 표시 이름, 호재 여부). 해당 없으면 None."""
    t = str(text or "")
    for key, label, good, pats in _CATALYST_COMPILED:
        if any(p.search(t) for p in pats):
            return key, label, good
    return None


def _age_text(hours: float) -> str:
    """몇 시간 전인지 사람이 읽기 쉬운 문자열로 (예: 3시간 전, 2일 전)."""
    if hours < 1:
        return "1시간 이내"
    if hours < 48:
        return f"{hours:.0f}시간 전"
    return f"{hours / 24:.0f}일 전"


def detect_catalysts(ticker: str, days: int = 7) -> list:
    """최근 days일 야후 뉴스에서 재료를 분류해 최신순으로 반환.
    각 항목: {key, label, good, hours(몇 시간 전), age(문자열), title, link}"""
    now = pd.Timestamp.now(tz="UTC")
    out = []
    try:
        for raw in fetch_yahoo_news(ticker) or []:
            p = parse_yahoo_news_item(raw)
            dt = _news_dt(raw)
            if dt is None:
                continue
            hours = (now - dt).total_seconds() / 3600
            if hours < 0 or hours > days * 24:
                continue
            c = classify_catalyst(p.get("title", ""))
            if not c:
                continue
            out.append({"key": c[0], "label": c[1], "good": c[2], "hours": hours,
                        "age": _age_text(hours), "title": p.get("title", ""), "link": p.get("link", "")})
    except Exception as _e:
        _log_err("detect_catalysts:" + ticker, _e)
    out.sort(key=lambda x: x["hours"])
    return out


def attach_catalysts(rows: list, limit: int = 30, max_workers: int = 6) -> None:
    """검색 결과 상위 limit개에 재료 정보를 병렬로 붙인다.
    - r["catalyst"]       : "🧬FDA·임상 3시간 전 · 📝계약·수주 1일 전" 형태 요약 (없으면 "—")
    - r["catalyst_ok"]    : 최근 48시간 안에 '호재성' 재료가 있으면 True (재료 필터용)
    - r["offering_days"]  : 가장 최근 오퍼링 관련 SEC 공시가 며칠 전인지 (없으면 None)
    - 종합점수 보정       : 오퍼링 공시가 7일 이내면 -10점, 30일 이내면 -5점 (희석 리스크)
    ⚠️ 오퍼링 공시 일자는 SEC 서식 기반 추정이며 실제 공모 여부·규모는 원문 확인이 필요합니다."""
    targets = rows[:limit]

    def _one(r):
        t = str(r.get("ticker", "")).replace("⚠️ ", "").strip()
        cats = detect_catalysts(t)
        off_days = None
        try:
            offs = fetch_offering_history(t)
            if offs:
                d = pd.to_datetime(offs[0].get("date"), errors="coerce", utc=True)
                if pd.notna(d):
                    off_days = max((pd.Timestamp.now(tz="UTC") - d).days, 0)
        except Exception as _e:
            _log_err("attach_catalysts:offering:" + t, _e)
        return r, cats, off_days

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for r, cats, off_days in ex.map(_one, targets):
            # 종류별로 가장 최신 1건만 남기고, 최신 2종류만 요약에 표시
            seen, pick = set(), []
            for c in cats:
                if c["key"] not in seen:
                    seen.add(c["key"])
                    pick.append(c)
            r["catalyst"] = " · ".join(f"{c['label']} {c['age']}" for c in pick[:2]) or "—"
            r["catalyst_ok"] = any(c["good"] and c["hours"] <= 48 for c in cats)
            r["offering_days"] = off_days
            r["catalyst_checked"] = True
            # 재료 품질(0~1) = 종류 가중치 × 신선도 가중치 중 가장 높은 호재. 호재가 없으면 0.
            # 오퍼링은 이제 점수 차감이 아니라 '게이트(점수 상한)'로 처리한다 (calc_trade_setup 참고)
            tier = {"fda": 1.0, "contract": 1.0, "earnings": 0.85, "analyst": 0.65}
            def _fresh(h):
                return 1.0 if h <= 6 else 0.9 if h <= 24 else 0.75 if h <= 48 else 0.6 if h <= 72 else 0.4
            good_scores = [tier.get(c["key"], 0.6) * _fresh(c["hours"]) for c in cats if c["good"]]
            r["catalyst_score"] = max(good_scores) if good_scores else 0.0
            r["catalyst_offering_news"] = any((not c["good"]) and c["hours"] <= 72 for c in cats)


def catalyst_summary_text(ticker: str, top: int = 2) -> str:
    """종목 하나의 재료 요약 문자열 (예: '🧬FDA·임상 3시간 전 · 📝계약·수주 1일 전'). 없으면 '—'.
    스캔(엑셀·즐겨찾기)처럼 종목별로 한 줄 요약만 필요할 때 사용합니다."""
    seen, pick = set(), []
    for c in detect_catalysts(ticker):
        if c["key"] not in seen:
            seen.add(c["key"])
            pick.append(c)
    return " · ".join(f"{c['label']} {c['age']}" for c in pick[:top]) or "—"


def calc_float_turnover(ticker: str, volume: float):
    """플로트 회전율(%) = 당일 거래량 ÷ 유통주식수 × 100. 유통주식수를 모르면 None."""
    try:
        fl = fetch_ticker_info(ticker).get("floatShares")
        return round(float(volume) / float(fl) * 100, 1) if fl else None
    except Exception as _e:
        _log_err("calc_float_turnover:" + ticker, _e)
        return None


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

    # RSI (14일, Wilder 방식 — EWM alpha=1/14)
    delta = c.diff()
    gain  = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
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


def calc_ma20_breakout(df, vol_mult: float = 1.5, recent_days: int = 3) -> dict:
    """일봉(calc_indicators 적용 결과)에서 20일선 돌파 상태를 판정한다.

    · breakout   : 오늘 종가가 MA20 위로 올라선 날 (전일 종가 <= 전일 MA20 → 오늘 종가 > 오늘 MA20)
    · breakdown  : 반대로 오늘 MA20 아래로 내려온 날 (이탈)
    · recent     : 돌파 후 아직 MA20 위에 머물고 있고, 돌파한 지 1~recent_days일 이내
    · days_since : 가장 최근 돌파일로부터 지난 봉 수 (오늘=0, 돌파 이력 없으면 None)
    · days_above : 종가가 MA20 위에 연속으로 머문 봉 수
    · gap_pct    : 20일선 이격도 (종가/MA20 - 1) × 100
    · vol_confirm: 돌파일 거래량이 20일 평균의 vol_mult배 이상인지
    · ma20_rising: MA20이 5봉 전보다 높은지
    MA20은 min_periods=1로 계산돼 초반 19개 값은 20일 평균이 아니므로, 21봉 미만이면 valid=False."""
    n = 0 if df is None else len(df)
    out = {"valid": False, "breakout": False, "breakdown": False, "recent": False,
           "days_since": None, "days_above": 0, "gap_pct": None, "vol_confirm": False,
           "ma20_rising": False, "ma20": None, "close": None, "n": n}
    if df is None or n < 21 or "MA20" not in df.columns:
        return out

    close = df["Close"].astype(float).to_numpy()
    ma20 = df["MA20"].astype(float).to_numpy()
    pos = np.arange(n)
    above = (close > ma20) & (pos >= 19)               # NaN 비교는 False
    prev_above = np.concatenate(([False], above[:-1]))
    cross_up = above & ~prev_above & (pos >= 20)
    cross_dn = (~above) & prev_above & (close < ma20)

    idx = np.flatnonzero(cross_up)
    days_since = int(n - 1 - idx[-1]) if len(idx) else None
    days_above = 0
    for v in above[::-1]:
        if v:
            days_above += 1
        else:
            break

    last_close, last_ma = float(close[-1]), float(ma20[-1])
    ref = int(idx[-1]) if len(idx) else n - 1          # 거래량은 (가장 최근) 돌파일 기준
    vol_confirm = False
    if "VOL_MA20" in df.columns and "Volume" in df.columns:
        vm = float(df["VOL_MA20"].iloc[ref])
        vol_confirm = bool(vm > 0 and float(df["Volume"].iloc[ref]) >= vm * vol_mult)

    out.update({
        "valid": True,
        "breakout": bool(cross_up[-1]),
        "breakdown": bool(cross_dn[-1]),
        "recent": bool(above[-1] and days_since is not None and 1 <= days_since <= recent_days),
        "days_since": days_since, "days_above": days_above,
        "gap_pct": (last_close / last_ma - 1) * 100 if last_ma else None,
        "vol_confirm": vol_confirm,
        "ma20_rising": bool(n >= 25 and last_ma > float(ma20[-6])),
        "ma20": last_ma, "close": last_close,
    })
    return out


def ma20_status(m: dict) -> tuple:
    """20일선 판정 결과를 (상태등 클래스, HTML 문구)로 변환."""
    if not m.get("valid"):
        return "dot-blue", f"20일선: 데이터 부족 ({m.get('n', 0)}일 / 최소 21일 필요)"
    gap, ma = m["gap_pct"], m["ma20"]
    trend = "MA20 상승 중" if m["ma20_rising"] else "MA20 하락·횡보"
    vol = "거래량 동반" if m["vol_confirm"] else "거래량 부족"
    heat = " · ⚠️ 이격 과대(추격 주의)" if gap is not None and gap >= 20 else ""
    if m["breakout"]:
        return "dot-green", f"<strong>20일선 돌파!</strong> 이격 {gap:+.1f}% · {vol} · {trend}{heat}"
    if m["breakdown"]:
        return "dot-red", f"<strong>20일선 이탈</strong> — 종가가 MA20({ma:,.2f}) 아래로 내려옴 ({gap:+.1f}%)"
    if m["recent"]:
        return "dot-green", (f"20일선 돌파 {m['days_since']}일 경과 · 이격 {gap:+.1f}% · "
                             f"돌파일 {vol} · {trend}{heat}")
    if gap is not None and gap > 0:
        if gap >= 20:
            return "dot-yellow", f"20일선 위 {gap:+.1f}% — 이격 과대, 단기 과열·눌림 주의"
        return "dot-blue", f"20일선 위 {m['days_above']}일째 유지 · 이격 {gap:+.1f}% · {trend}"
    need = (ma / m["close"] - 1) * 100 if m["close"] else 0.0
    return "dot-yellow", f"20일선 아래 ({gap:+.1f}%) — 돌파까지 +{need:.1f}% 필요 (MA20 {ma:,.2f})"

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
    # 급등주는 일봉 RSI 75 초과도 정상이라 과매수 감점을 없앴다 (50 이상이면 만점)
    if rsi_val >= 50:
        rsi_score = 15.0
    else:
        rsi_score = 15.0 * max(0.0, rsi_val / 50.0)
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
    검색 결과 여러 지표를 가중 합산해 0~100점 종합 점수를 산출합니다. (단타·소형 급등주 기준)
    급등주 검색기와 즐겨찾기 일괄 스캔 양쪽에서 동일한 기준으로 사용합니다.
    - 등락률               25% (50% 상승 시 만점)
    - 상대거래량(20일MA비율) 30% (500% = 5배 도달 시 만점)  ← 소형주 단타의 핵심 지표
    - 거래대금(억원)        15% (270억 ≈ $2천만 도달 시 만점)
    - 플로트 회전율         15% (유통주식 대비 당일 거래량 100% 도달 시 만점, 값이 없으면 중립 점수)
    - RSI 모멘텀            10% (50 이상이면 만점. 급등주는 RSI 70 이상이 정상이라 감점하지 않음)
    - 거래량 전일비          5% (전일 거래량이 적은 날은 값이 과장되므로 비중을 낮춤)
    단순 산식이며 절대적 매수·매도 신호가 아닌 상대 비교용 참고 지표입니다.
    """
    pct        = r.get("pct_change") or 0
    vol_ma20_r = r.get("vol_ma20_ratio") or 0
    trading_v  = r.get("trading_value_eok") or 0
    vol_r      = r.get("vol_ratio") or 0
    rsi        = r.get("rsi")
    turnover   = r.get("float_turnover")   # 플로트 회전율(%) — 없으면 None

    pct_score       = min(max(pct, 0) / 50, 1) * 25
    vol_ma20_score  = min(max(vol_ma20_r, 0) / 500, 1) * 30
    trading_score   = min(max(trading_v, 0) / 270, 1) * 15
    vol_ratio_score = min(max(vol_r, 0) / 300, 1) * 5

    # 플로트 회전율: 유통주식수를 모르면 감점도 가점도 하지 않도록 중간값(7.5점)을 준다
    if turnover is None:
        turnover_score = 7.5
    else:
        turnover_score = min(max(turnover, 0) / 100, 1) * 15

    # RSI: 급등주는 일봉 RSI가 70 이상이어도 정상이므로 과매수 감점을 없앴다
    if rsi is None:
        rsi_score = 5.0
    elif rsi >= 50:
        rsi_score = 10.0
    else:
        rsi_score = max(0.0, rsi / 50 * 5.0)   # 50 미만이면 모멘텀 약함

    total = (pct_score + vol_ma20_score + trading_score
             + vol_ratio_score + turnover_score + rsi_score)
    return round(min(total, 100.0), 1)
    # ════════════════════════════════════════════════════════════════
# Part 5 / 스톡타이탄 크롤링 ~ 소셜 미디어 렌더링
# ════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════
# 스톡타이탄 크롤링 함수
# #3 render_news_section 위로 이동 / #13 User-Agent 랜덤 순환
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
    except Exception as _e:
        _log_err("_fetch_detail", _e)
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
        # 서로 의존관계가 없으므로 같은 스레드풀에 번역 작업도 함께 제출해 병렬로 겹쳐 실행.
        # 번역 API 키는 메인 스레드(여기)에서 읽어 인자로 넘긴다(워커 스레드에서 session_state 접근 금지).
        api_key = st.session_state.get("gemini_api_key", "")
        detail_results = {}
        with ThreadPoolExecutor(max_workers=6) as executor:
            future_to_link = {
                executor.submit(_fetch_detail, item["link"], _random_headers()): item["link"]
                for item in raw_list
            }
            translate_future = executor.submit(
                translate_texts_batch, [item["title_en"] for item in raw_list], api_key
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
    except Exception as _e:
        _log_err("get_stock_titan_data", _e)
        return []

# ════════════════════════════════════════════════════════════════
# 소셜 미디어 — StockTwits
# ════════════════════════════════════════════════════════════════
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
                # 원문 보기 클릭 없이 바로 한글로 보이도록 StockTwits 본문도 일괄 번역
                _translations = translate_texts_batch([m["body_en"] for m in messages])
                for m in messages:
                    m["body"] = _translations.get(m["body_en"], m["body_en"])
                return {"bull": bull, "bear": bear, "messages": messages, "source": "stocktwits"}
    except Exception as _e:
        _log_err("fetch_stocktwits", _e)
        pass

    # ── 2차 fallback: yfinance 뉴스 + 키워드 감성 분류 ──────────
    POS_KW = {"beat", "bullish", "surge", "soar", "rally", "up", "gain", "buy",
              "upgrade", "strong", "growth", "profit", "record", "positive"}
    NEG_KW = {"miss", "bearish", "drop", "fall", "decline", "cut", "downgrade",
              "loss", "weak", "lawsuit", "fraud", "sell", "negative", "concern"}

    try:
        raw_news = yf.Ticker(ticker).news or []
    except Exception as _e:
        _log_err("fetch_stocktwits", _e)
        raw_news = []

    # 후보를 모두 추린 뒤 한 번에 병렬 번역 (배치 캐시 저장도 배치당 1회).
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
            user_name  = _safe_html(msg["user"])
            msg_date   = _safe_html(msg.get("date", ""))
            msg_body   = _safe_html(msg["body"])
            msg_body_en = _safe_html(msg.get("body_en", ""))
            msg_link   = _safe_url(msg["link"])

            # 날짜 표시 (yahoo fallback은 date 없음)
            date_html = f'<span>·</span><span>{msg_date}</span>' if msg_date else ""
            # yahoo fallback은 영문 원제목도 표시
            body_en_html = (f'<div style="font-size:0.75rem;color:rgba(148,163,184,0.45);margin-top:0.25rem;font-style:italic;">{msg_body_en}</div>'
                            if msg_body_en and msg_body_en != msg_body else "")
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


# ════════════════════════════════════════════════════════════════
# Part 6 / AI 차트 해석 (5분봉·1시간봉 추세, Gemini 호출, 탭 렌더링)
# ════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════
# #신규 AI 차트 해석 — 5분봉 + 1시간봉 단기추세 자동 분석 (진입 여부 / 저항선 돌파 가능성)
# ════════════════════════════════════════════════════════════════
CHART_ANALYSIS_MODEL = "gemini-2.5-flash"

CHART_ANALYSIS_SYSTEM_PROMPT = """당신은 단타/스윙 트레이더를 돕는 숙련된 기술적 분석가입니다.
사용자가 제공하는 '당일 5분봉 데이터', '1시간봉 단기 추세', '악성매물대(저항 구간) 분석 결과'를 근거로
한국어로 짧고 명료하게 답변하세요.

#개선 기존 5개 항목(흐름 요약/모멘텀/진입 판단/저항 돌파 가능성/리스크)을
읽는 데 오래 걸린다는 피드백을 반영해 3개 소제목으로 통합하고,
항목별 분량 상한(글머리 기호 1~2줄)을 명시함.

아래 3개 소제목만 이모지와 함께 사용하고, 각 항목은 글머리 기호 1~2줄로 핵심만 쓰세요.
전체 답변은 250자를 넘기지 마세요.

1. 📊 현재 상황 — 시가 대비 등락률, 5분봉·1시간봉 추세 방향(일치/불일치), 저항 구간 돌파 가능성을 한 줄로
2. 🎯 진입 판단 — 매수 / 관망 중 하나를 고르고 핵심 근거 1가지만
3. ⚠️ 리스크 — 가장 중요한 리스크 요인 1가지만 (5분봉 신호가 1시간봉 추세와 반대 방향이면 이를 우선 언급, 합병·인수·파산 이벤트가 있으면 최우선 언급)

숫자는 주어진 데이터 범위 안에서만 근거로 사용하고, 데이터에 없는 값은 추측하지 마세요.
마지막 줄에 반드시 "이 분석은 참고용이며 투자 조언이 아닙니다."
라는 문구만 짧게 포함하세요."""


@st.cache_data(ttl=60, show_spinner=False)
def fetch_intraday_5min(ticker: str) -> pd.DataFrame:
    """당일 1분봉(프리·애프터마켓 포함)을 5분봉으로 리샘플링합니다.
    Session 열: 'REG'=정규장, 'EXT'=프리·애프터마켓 (미국 거래소 시간대일 때만 구분)."""
    try:
        raw = yf.Ticker(ticker).history(period="1d", interval="1m", prepost=True)
    except Exception as _e:
        _log_err("fetch_intraday_5min:" + ticker, _e)
        return pd.DataFrame()
    if raw is None or raw.empty:
        return pd.DataFrame()

    # 거래가 뜸한 종목은 period="1d" 요청에도 며칠치 데이터가 섞여 올 수 있어
    # 가장 최근 거래일 데이터만 남긴다(차트 x축이 늘어지는 문제 방지).
    raw.index = pd.to_datetime(raw.index)
    latest_date = raw.index.date.max()
    raw = raw[raw.index.date == latest_date]
    if raw.empty:
        return pd.DataFrame()

    ohlc = raw.resample("5min").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    }).dropna(subset=["Open"])

    # 세션 구분: 미국 시간대면 09:30~16:00(ET)만 정규장, 나머지는 프리·애프터마켓
    ohlc["Session"] = "REG"
    if "America/" in str(raw.index.tz):
        mins = ohlc.index.hour * 60 + ohlc.index.minute
        ohlc.loc[(mins < 570) | (mins >= 960), "Session"] = "EXT"
    return ohlc


@st.cache_data(ttl=300, show_spinner=False)
def fetch_hourly(ticker: str) -> pd.DataFrame:
    """최근 약 1개월 1시간봉(정규장). 단기 추세 판단용. 마지막 봉은 진행 중일 수 있음."""
    try:
        raw = yf.Ticker(ticker).history(period="1mo", interval="1h")
    except Exception as _e:
        _log_err("fetch_hourly:" + ticker, _e)
        return pd.DataFrame()
    if raw is None or raw.empty:
        return pd.DataFrame()
    return raw[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])


def calc_short_term_trend(df, fast: int = 9, slow: int = 21) -> dict:
    """봉 데이터(OHLC)로 단기 추세를 규칙 기반으로 판정한다.
    점수(-4~+4) = 종가 vs EMA(fast) ±1 + EMA(fast) vs EMA(slow) ±1
                  + EMA(fast) 3봉 기울기 ±1/0 + 최근 6봉 vs 직전 6봉 고점·저점 구조 ±1/0
    4=강한 상승, 3=상승, -3=하락, -4=강한 하락, 그 외=횡보·혼조. (slow+4봉 미만이면 '데이터 부족')"""
    need = slow + 4
    n = 0 if df is None else len(df)
    if df is None or df.empty or n < need:
        return {"label": "데이터 부족", "score": 0, "n": n, "need": need}

    close = df["Close"].astype(float)
    ema_f = close.ewm(span=fast, adjust=False).mean()
    ema_s = close.ewm(span=slow, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    g, l = float(gain.iloc[-1]), float(loss.iloc[-1])
    rsi = 100.0 if l == 0 and g > 0 else (50.0 if l == 0 else 100 - 100 / (1 + g / l))

    last, ef, es = float(close.iloc[-1]), float(ema_f.iloc[-1]), float(ema_s.iloc[-1])
    ef_prev = float(ema_f.iloc[-4])
    slope_pct = (ef / ef_prev - 1) * 100 if ef_prev else 0.0

    recent, prev = df.tail(6), df.iloc[-12:-6]
    hh = float(recent["High"].max()) > float(prev["High"].max())
    hl = float(recent["Low"].min()) > float(prev["Low"].min())
    lh = float(recent["High"].max()) < float(prev["High"].max())
    ll = float(recent["Low"].min()) < float(prev["Low"].min())
    struct = 1 if (hh and hl) else (-1 if (lh and ll) else 0)
    struct_txt = {1: "고점·저점 상승", -1: "고점·저점 하락", 0: "고점·저점 혼조"}[struct]

    score = (1 if last > ef else -1) + (1 if ef > es else -1) \
            + (1 if slope_pct > 0 else (-1 if slope_pct < 0 else 0)) + struct
    if score >= 4:
        label = "강한 상승"
    elif score == 3:
        label = "상승"
    elif score <= -4:
        label = "강한 하락"
    elif score == -3:
        label = "하락"
    else:
        label = "횡보·혼조"

    hi20, lo20 = float(df["High"].tail(20).max()), float(df["Low"].tail(20).min())
    pos20 = (last - lo20) / (hi20 - lo20) * 100 if hi20 > lo20 else 50.0
    return {"label": label, "score": score, "n": n, "fast": fast, "slow": slow,
            "close": last, "ema_fast": ef, "ema_slow": es, "rsi": rsi,
            "slope_pct": slope_pct, "structure": struct_txt,
            "hi20": hi20, "lo20": lo20, "pos20": pos20}


def _trend_line(name: str, t: dict) -> str:
    """추세 판정 결과를 한 줄 문장으로."""
    if t.get("label") == "데이터 부족":
        return f"{name}: 데이터 부족 ({t.get('n', 0)}봉 / 최소 {t.get('need', 25)}봉 필요)"
    rel = ">" if t["ema_fast"] > t["ema_slow"] else "<"
    return (f"{name}: {t['label']} · EMA{t['fast']} {rel} EMA{t['slow']} · "
            f"RSI {t['rsi']:.0f} · {t['structure']}")


def _trend_alignment(t5: dict, t1h: dict) -> str:
    """5분봉과 1시간봉의 방향이 맞는지 한 줄로."""
    def d(t):
        lab = t.get("label", "")
        if lab == "데이터 부족":
            return None
        return 1 if "상승" in lab else (-1 if "하락" in lab else 0)
    a, b = d(t5), d(t1h)
    if a is None or b is None:
        return ""
    if a == b == 1:
        return "5분봉·1시간봉 모두 상승 — 단기 방향 일치"
    if a == b == -1:
        return "5분봉·1시간봉 모두 하락 — 단기 방향 일치(약세)"
    if a == 1 and b == -1:
        return "⚠️ 1시간봉은 하락 추세인데 5분봉만 반등 — 추세 역행 반등일 수 있음"
    if a == -1 and b == 1:
        return "1시간봉 상승 추세 중 5분봉 눌림 — 조정 구간일 수 있음"
    if b == 0:
        return "1시간봉이 횡보·혼조 — 방향성이 약함"
    if a == 0:
        return "5분봉 횡보·혼조 — 1시간봉 방향 재확인 필요"
    return ""


def build_chart_analysis_prompt(ticker: str, candles: pd.DataFrame, supply_data: dict,
                                 extra_question: str = "", hourly=None, events=None) -> str:
    """5분봉 요약 통계 + 최근 캔들 목록 + 1시간봉 단기 추세 + 저항 구간 정보를 텍스트 프롬프트로 조립."""
    c = candles.copy()
    # 프리·애프터마켓 구분 열(Session)은 지표 계산에서 분리했다가 다시 붙인다
    _sess = c["Session"] if "Session" in c.columns else pd.Series("REG", index=c.index)
    c = calc_indicators(c.drop(columns=["Session"], errors="ignore"))  # RSI/MA 등 재사용 (5분봉 기준)
    c["Session"] = _sess.reindex(c.index).fillna("REG")

    reg = c[c["Session"] == "REG"]
    has_reg = not reg.empty
    ext_now = c["Session"].iloc[-1] == "EXT"
    base = reg if has_reg else c                 # 시가·VWAP 기준: 정규장 (아직 미개장이면 전체)

    day_open   = float(base["Open"].iloc[0])
    day_high   = float(c["High"].max())          # 고가/저가는 프리·애프터 포함
    day_low    = float(c["Low"].min())
    last_close = float(c["Close"].iloc[-1])
    total_vol  = float(c["Volume"].sum())
    base_vol   = float(base["Volume"].sum())
    typical    = (base["High"] + base["Low"] + base["Close"]) / 3
    vwap       = float((typical * base["Volume"]).sum() / base_vol) if base_vol > 0 else last_close
    pct_open   = (last_close - day_open) / day_open * 100 if day_open else 0.0
    last_rsi   = c["RSI"].iloc[-1]
    last_rsi_s = f"{last_rsi:.1f}" if pd.notna(last_rsi) else "N/A"

    session_label = "프리·애프터마켓" if ext_now else "정규장"
    open_label    = "정규장 시가" if has_reg else "프리마켓 첫 가격(정규장 미개장)"
    vwap_label    = "정규장" if has_reg else "프리마켓"
    pre = c[(c["Session"] == "EXT") & (c.index < reg.index[0])] if has_reg else c[c["Session"] == "EXT"]
    if not pre.empty:
        pre_line = (f"프리마켓 구간: 고가 ${pre['High'].max():.2f} / 저가 ${pre['Low'].min():.2f} / "
                    f"거래량 {int(pre['Volume'].sum()):,}주")
    else:
        pre_line = "프리마켓 구간: 거래 없음"

    recent = c.tail(5)
    up_count = int((recent["Close"] > recent["Open"]).sum())

    # 단기 추세: 5분봉(당일) + 1시간봉(최근 1개월) 규칙 기반 판정
    t5 = calc_short_term_trend(c)
    trend5_line = _trend_line("5분봉", t5)
    if hourly is not None and not hourly.empty:
        t1h = calc_short_term_trend(hourly)
        hourly_block = _trend_line("1시간봉", t1h)
        if t1h.get("label") != "데이터 부족":
            hourly_block += (f"\n최근 20개 1시간봉 고점 ${t1h['hi20']:.2f} / 저점 ${t1h['lo20']:.2f} "
                             f"(현재가 위치 {t1h['pos20']:.0f}%)")
        h_lines = [f"[{ts.strftime('%m-%d %H:%M')}] O:{r.Open:.2f} H:{r.High:.2f} L:{r.Low:.2f} C:{r.Close:.2f}"
                   for ts, r in hourly.tail(6).iterrows()]
        hourly_block += "\n최근 6개 1시간봉 (오래된 순, 마지막 봉은 진행 중일 수 있음):\n" + "\n".join(h_lines)
        align_line = _trend_alignment(t5, t1h)
    else:
        hourly_block = "1시간봉 데이터를 가져오지 못했습니다."
        align_line = ""

    lines = [f"[{ts.strftime('%H:%M')}{' 프리/애프터' if row.Session == 'EXT' else ''}] "
             f"O:{row.Open:.2f} H:{row.High:.2f} L:{row.Low:.2f} C:{row.Close:.2f} V:{int(row.Volume):,}"
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

    if events and events.get("items"):
        ev_lines = [f"[{it.get('date') or '날짜 미상'}] {EVENT_LABELS[it['category']][1]}: {it['title']}"
                    for it in events["items"][:5]]
        events_block = "[최근 이벤트 (뉴스·SEC 공시 키워드 자동 감지, 오탐 가능)]\n" + "\n".join(ev_lines)
    else:
        events_block = "[최근 이벤트] 합병·인수·파산 관련 뉴스/공시는 감지되지 않음"

    prompt = f"""티커: {ticker}
현재 세션: {session_label}
{open_label}: ${day_open:.2f} / 당일 고가(프리·애프터 포함): ${day_high:.2f} / 당일 저가(프리·애프터 포함): ${day_low:.2f}
{pre_line}
현재가(최근 5분봉 종가): ${last_close:.2f} ({open_label} 대비 {pct_open:+.2f}%)
VWAP(거래량가중평균가, {vwap_label} 기준): ${vwap:.2f}
누적 거래량(프리·애프터 포함): {int(total_vol):,}주
5분봉 RSI(14): {last_rsi_s}
최근 5개 5분봉 중 양봉 개수: {up_count}/5

[5분봉 단기 추세 (규칙 기반 판정)]
{trend5_line}

[1시간봉 단기 추세 (규칙 기반 판정, 최근 약 1개월)]
{hourly_block}
{align_line}

{events_block}

[악성매물대(저항 구간) 분석 결과]
{resistance_block}

[최근 5분봉 목록 (오래된 순)]
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
            # gemini-2.5-flash는 내부 thinking 토큰을 maxOutputTokens에서 함께 소모하므로
            # thinkingBudget=0으로 끄고 출력 예산을 넉넉히 둔다.
            "maxOutputTokens": 3000,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{CHART_ANALYSIS_MODEL}:generateContent"
    )
    resp = requests.post(url, json=payload, timeout=60,
                         headers={"x-goog-api-key": api_key})
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


_TV_EXCHANGE_MAP = {"NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NYQ": "NYSE", "ASE": "AMEX", "PCX": "AMEX", "BTS": "CBOE"}


def tradingview_chart_url(ticker: str, exchange_code: str = "") -> str:
    """TradingView 차트 주소. 거래소 코드(야후 기준: NMS·NYQ·ASE 등)를 NASDAQ:/NYSE:/AMEX: 접두어로 바꾸고,
    클래스주(BRK-B)는 점 표기(BRK.B)로 바꾼다. 거래소를 모르면 접두어 없이 티커만 넘긴다(TradingView가 알아서 찾음).
    로그인한 본인 계정의 실시간 데이터·저장한 지표 템플릿이 그대로 적용된다."""
    from urllib.parse import quote
    sym = (ticker or "").strip().upper().replace("-", ".")
    prefix = _TV_EXCHANGE_MAP.get((exchange_code or "").upper())
    return "https://www.tradingview.com/chart/?symbol=" + quote(f"{prefix}:{sym}" if prefix else sym, safe="")


def render_chart_interpretation(ticker: str, hist_daily: pd.DataFrame, current_price: float):
    """AI 차트 해석 탭 — 5분봉 + 1시간봉 추세를 자동으로 받아 진입 여부·저항선 돌파 가능성을 분석."""
    ui_section_header(mono_icon_badge("camera", color="var(--c-cyan)"), "AI 차트 해석 (5분봉 + 1시간봉 추세)")

    # TradingView 열기 — 본인 계정(실시간 데이터·지표 템플릿)으로 새 탭에서 차트를 연다. API 키 없이도 사용 가능.
    _tv_url = tradingview_chart_url(ticker, (fetch_ticker_info(ticker) or {}).get("exchange", ""))
    st.link_button(f"📈 TradingView에서 {ticker} 차트 열기", _tv_url, use_container_width=True)

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

    with st.spinner("5분봉·1시간봉 데이터를 불러오는 중..."):
        candles = fetch_intraday_5min(ticker)
        hourly = fetch_hourly(ticker)

    if candles.empty or len(candles) < 3:
        st.markdown(
            '''<div class="glass-card"><div class="status-row"><div class="status-item">
                <div class="status-dot dot-blue"></div>
                <div class="status-text">프리·애프터마켓 포함 당일 5분봉 데이터를 가져올 수 없습니다.
                휴장 중이거나 아직 거래가 시작되지 않았거나, 데이터 제공이 제한된 종목일 수 있습니다.</div>
            </div></div></div>''',
            unsafe_allow_html=True,
        )
        return

    # 좌측 컬럼에서 이미 계산된 악성매물대와 동일 기준·파라미터로 저항 구간을 다시 산출
    supply_data = calc_supply_zones(
        hist_daily, current_price,
        n_bins=supply_n_bins, lookback_days=supply_lookback_days,
        heavy_mult=supply_heavy_mult, max_zones=supply_max_zones,
    )

    # 단기 추세 요약 카드 — AI 호출 없이 규칙 기반으로 즉시 표시
    _t5 = calc_short_term_trend(candles)
    _t1 = calc_short_term_trend(hourly)

    def _trend_dot(t: dict) -> str:
        lab = t.get("label", "")
        return "dot-green" if "상승" in lab else ("dot-red" if "하락" in lab else "dot-yellow")

    _rows = ""
    for _nm, _tt in (("5분봉", _t5), ("1시간봉", _t1)):
        _rows += ('<div class="status-row"><div class="status-item">'
                  f'<div class="status-dot {_trend_dot(_tt)}"></div>'
                  f'<div class="status-text">{_html_lib.escape(_trend_line(_nm, _tt))}</div>'
                  '</div></div>')
    _al = _trend_alignment(_t5, _t1)
    if _al:
        _rows += ('<div class="status-row"><div class="status-item">'
                  '<div class="status-dot dot-blue"></div>'
                  f'<div class="status-text">{_html_lib.escape(_al)}</div>'
                  '</div></div>')
    st.markdown(f'<div class="glass-card">{_rows}</div>', unsafe_allow_html=True)

    extra_question = st.text_input(
        "추가로 궁금한 점이 있다면 적어주세요 (선택)",
        key="chart_ai_question",
        placeholder="예: 손절선은 어디로 잡는 게 좋을까?",
    )

    last_ts = candles.index[-1]
    run_clicked = st.button("🔍 지금 진입 여부 분석하기", use_container_width=True, key="chart_analysis_run_btn")

    # 결과는 티커 기준으로 보관한다 — 새 5분봉이 생기거나 질문 입력칸을 건드려도 지워지지 않는다.
    if run_clicked:
        with st.spinner("Gemini가 당일 흐름과 저항 구간을 분석하는 중..."):
            try:
                prompt_text = build_chart_analysis_prompt(ticker, candles, supply_data, extra_question, hourly,
                                                          detect_corporate_events(ticker))
                result_text = analyze_price_action(prompt_text, api_key)
                st.session_state["chart_analysis_result"] = result_text
                st.session_state["chart_analysis_error"] = None
            except Exception as e:
                _log_err("chart_analysis", e)
                st.session_state["chart_analysis_result"] = None
                st.session_state["chart_analysis_error"] = _safe_error_text(e)
        st.session_state["chart_analysis_meta"] = {
            "ticker": ticker, "ts": datetime.now().timestamp(),
            "candle": last_ts, "question": (extra_question or "").strip(),
        }

    meta = st.session_state.get("chart_analysis_meta") or {}
    same_ticker = meta.get("ticker") == ticker
    error_msg = st.session_state.get("chart_analysis_error")
    result_txt = st.session_state.get("chart_analysis_result")

    if same_ticker and error_msg:
        st.markdown(
            f'''<div class="glass-card"><div class="status-row"><div class="status-item">
                <div class="status-dot dot-red"></div>
                <div class="status-text">분석 중 오류가 발생했습니다: {error_msg}</div>
            </div></div></div>''',
            unsafe_allow_html=True,
        )
    elif same_ticker and result_txt:
        # 결과 전체를 하나의 st.markdown 안에서 흰 박스 + 검정 글씨로 표시
        # (st.markdown을 나눠 호출하면 div가 분리되어 빈 박스가 생기므로 한 번에 출력)
        _ai_html = (
            "<style>"
            ".ai-result{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px 18px;margin:8px 0 16px 0;box-shadow:0 1px 2px rgba(17,24,39,.04);}"
            ".ai-result, .ai-result *{color:#111827 !important;}"
            "</style>"
            '<div class="ai-result">\n\n'
            + _safe_html(result_txt)
            + "\n\n</div>"
        )
        st.markdown(_ai_html, unsafe_allow_html=True)

        age_min = int((datetime.now().timestamp() - meta.get("ts", 0)) // 60)
        age_txt = "방금 전" if age_min < 1 else f"{age_min}분 전"
        try:
            base_ts = meta["candle"]
            new_n = int((candles.index > base_ts).sum())
            base_txt = pd.Timestamp(base_ts).strftime("%H:%M")
        except Exception:
            new_n, base_txt = 0, "?"
        note = f"🕒 {age_txt} 분석 (기준 5분봉 {base_txt})"
        if new_n > 0:
            note += f" · 이후 새 5분봉 {new_n}개 — 최신 기준으로 보려면 다시 분석하세요"
        if meta.get("question", "") != (extra_question or "").strip():
            note += " · 질문이 바뀌었습니다. 버튼을 누르면 새 질문으로 분석합니다"
        st.caption(note)
    else:
        st.caption("버튼을 누르면 최신 5분봉(프리·애프터마켓 포함)과 1시간봉 추세를 기준으로 분석합니다.")
        # ════════════════════════════════════════════════════════════════
# Part 7-1 / CSS 템플릿 (CSS_TEMPLATE)
# ════════════════════════════════════════════════════════════════

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
    .news-orig  { font-size: 0.72rem; color: ${text_dimmed}; margin-bottom: 0.5rem; font-style: italic; }
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
        color: ${text_muted} !important;
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
        color: ${text_primary} !important;
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
        color: ${text_muted} !important;
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
"""
# ════════════════════════════════════════════════════════════════
# Part 7-2 / MINIMAL_CSS · inject_css() · 헤더 배너 · 즐겨찾기 스캔 결과
# ════════════════════════════════════════════════════════════════

MINIMAL_CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+KR:wght@400;500;700&display=swap');
:root{
  --m-bg:#fafafa; --m-card:#ffffff; --m-line:#e5e7eb; --m-line-2:#f1f2f4;
  --m-ink:#111827; --m-sub:#4b5563; --m-mute:#6b7280;
  --m-accent:#111827;
  --m-up:#047857;  --m-up-bg:#ecfdf5;  --m-up-line:#a7f3d0;
  --m-down:#b91c1c;--m-down-bg:#fef2f2;--m-down-line:#fecaca;
  --m-warn:#92600a;--m-warn-bg:#fffbeb;--m-warn-line:#fde68a;
  --m-info:#1d4ed8;--m-info-bg:#eff6ff;--m-info-line:#bfdbfe;
  --font-body:"Inter","Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;
  --font-display:"Inter","Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;
  --radius-card:12px; --radius-card-sm:10px; --radius-pill:999px;
}

/* 배경 · 타이포 */
html,body,.stApp,[data-testid="stAppViewContainer"]{background:var(--m-bg)!important;background-image:none!important;animation:none!important;font-family:var(--font-body);}
[data-testid="stHeader"]{background:transparent!important;}
[data-testid="stMainBlockContainer"],.main .block-container{padding-bottom:3rem!important;}
h1,h2,h3,h4{color:var(--m-ink)!important;font-family:var(--font-display)!important;font-weight:600!important;letter-spacing:-0.01em;}
[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] *{color:var(--m-mute)!important;font-weight:400;}
hr{border:0!important;border-top:1px solid var(--m-line)!important;opacity:1!important;}

/* 카드 — 흰 면 + 1px 테두리, 그림자는 거의 없음 */
.glass-card,.metric-card,.news-card,.social-card,.status-item,.sentiment-bar-wrap,.scan-header{
  background:var(--m-card)!important;color:var(--m-ink);
  border:1px solid var(--m-line)!important;border-radius:var(--radius-card)!important;
  box-shadow:0 1px 2px rgba(17,24,39,.04)!important;backdrop-filter:none!important;}
.glass-card:hover,.news-card:hover,.social-card:hover,.metric-card:hover{
  transform:none!important;border-color:#d1d5db!important;box-shadow:0 2px 6px rgba(17,24,39,.06)!important;}
.status-item{background:#fcfcfd!important;border-radius:var(--radius-card-sm)!important;box-shadow:none!important;}
.metric-card{border-left:1px solid var(--m-line)!important;background-image:none!important;}
.mc-amber,.mc-violet,.mc-rose,.mc-cyan,.mc-indigo,.mc-teal{background-image:none!important;border-left-color:var(--m-line)!important;}
.pos-card,.social-bull{border-left:3px solid var(--m-up)!important;background-image:none!important;}
.neg-card,.social-bear{border-left:3px solid var(--m-down)!important;background-image:none!important;}
.neu-card{border-left:3px solid #d1a43a!important;background-image:none!important;}
.metric-card .metric-label,.glass-card-title,.news-meta,.social-meta,.social-stats,.news-orig{color:var(--m-mute)!important;}
.metric-label{font-weight:500!important;letter-spacing:.04em!important;}
.metric-value,.news-title,.social-body,.status-text,.status-text strong,.scan-title,.sector-name,.sector-ticker{color:var(--m-ink)!important;}
.metric-value{font-family:var(--font-mono)!important;font-weight:600!important;}
.news-link,.news-link:hover{color:var(--m-info)!important;text-decoration:none;font-weight:600;}
.news-link:hover{text-decoration:underline;}
.scan-header{border-left:1px solid var(--m-line)!important;}
.delta-up{color:var(--m-up)!important;} .delta-down{color:var(--m-down)!important;} .delta-neu{color:var(--m-mute)!important;}
.sector-cell{border:1px solid var(--m-line)!important;border-radius:var(--radius-card-sm)!important;box-shadow:none!important;}

/* 배지 · 칩 — 옅은 틴트 + 얇은 테두리 */
.sentiment-badge,.impact-badge,.bull-badge,.bear-badge,.platform-badge,.signal-chip{
  border:1px solid var(--m-line)!important;border-radius:var(--radius-pill)!important;font-weight:600!important;box-shadow:none!important;}
.sent-pos,.bull-badge{background:var(--m-up-bg)!important;color:var(--m-up)!important;border-color:var(--m-up-line)!important;}
.sent-neg,.bear-badge{background:var(--m-down-bg)!important;color:var(--m-down)!important;border-color:var(--m-down-line)!important;}
.sent-neu{background:var(--m-warn-bg)!important;color:var(--m-warn)!important;border-color:var(--m-warn-line)!important;}
.impact-badge,.platform-badge{background:var(--m-info-bg)!important;color:var(--m-info)!important;border-color:var(--m-info-line)!important;}
.signal-chip{background:#fff!important;color:var(--m-ink)!important;}
.dot-green{background:var(--m-up)!important;box-shadow:none!important;}
.dot-yellow{background:#d1a43a!important;box-shadow:none!important;}
.dot-red{background:var(--m-down)!important;box-shadow:none!important;}
.dot-blue{background:#9ca3af!important;box-shadow:none!important;}
.status-dot{border:none!important;border-radius:50%!important;width:8px!important;height:8px!important;}

/* 배너 — 채도 낮은 틴트 */
.alert-banner,.china-banner,.split-banner{border:1px solid var(--m-line)!important;border-radius:var(--radius-card)!important;box-shadow:none!important;}
.alert-banner{background:var(--m-down-bg)!important;border-color:var(--m-down-line)!important;}
.china-banner{background:var(--m-warn-bg)!important;border-color:var(--m-warn-line)!important;}
.split-banner{background:var(--m-warn-bg)!important;border-color:var(--m-warn-line)!important;}
.alert-icon,.china-banner-icon{background:#fff!important;border:1px solid var(--m-line)!important;border-radius:10px!important;}
.alert-title{color:var(--m-down)!important;}
.china-banner-text,.china-banner-sub,.split-banner-title,.split-banner-body,.split-banner-body strong{color:var(--m-warn)!important;opacity:1!important;}
.split-banner .news-link{color:var(--m-warn)!important;text-decoration:underline;}

/* 헤더 */
.app-header{background:var(--m-card)!important;border:1px solid var(--m-line)!important;border-radius:var(--radius-card)!important;
  box-shadow:0 1px 2px rgba(17,24,39,.04)!important;overflow:hidden!important;animation:none!important;}
.app-header::before{display:none!important;}
.app-header::after{display:none!important;}
.app-header h1{color:var(--m-ink)!important;-webkit-text-fill-color:var(--m-ink)!important;font-size:1.2rem!important;font-weight:700!important;}
.app-header p{color:var(--m-mute)!important;font-weight:400!important;}
.nb-ticker{display:none!important;}

/* 섹션 헤더 · 아이콘 배지 */
.section-title,.title-amber,.title-teal,.title-indigo,.title-violet,.title-cyan,.title-rose{
  color:var(--m-ink)!important;font-family:var(--font-display)!important;font-weight:600!important;font-size:1rem!important;}
.section-icon,.liquid-icon:not(.liquid-icon-outline){background:#f3f4f6!important;border:1px solid var(--m-line)!important;border-radius:10px!important;box-shadow:none!important;}
.liquid-icon-outline{background:#fff!important;border:1px solid var(--m-line)!important;border-radius:10px!important;box-shadow:none!important;}
.liquid-icon svg{stroke:var(--m-ink)!important;}

/* 버튼 — 옅은 회색 면 + 검정 글씨 */
.stButton button,.stFormSubmitButton button,[data-testid="stFormSubmitButton"] button,[data-testid="stDownloadButton"] button,
[data-testid^="stBaseButton-secondary"],[data-testid^="stBaseButton-primary"],[data-testid="stNumberInput"] button{
  background:#f3f4f6!important;background-color:#f3f4f6!important;background-image:none!important;
  color:#111827!important;-webkit-text-fill-color:#111827!important;
  border:1px solid #d1d5db!important;border-radius:10px!important;box-shadow:none!important;
  font-family:var(--font-body)!important;font-weight:600!important;font-size:.88rem!important;filter:none!important;
  transition:background .15s,border-color .15s!important;}
.stButton button *,.stFormSubmitButton button *,[data-testid="stFormSubmitButton"] button *,[data-testid="stDownloadButton"] button *,
[data-testid^="stBaseButton-secondary"] *,[data-testid^="stBaseButton-primary"] *,[data-testid="stNumberInput"] button *{
  color:#111827!important;-webkit-text-fill-color:#111827!important;fill:#111827!important;opacity:1!important;}
.stButton button:hover,.stFormSubmitButton button:hover,[data-testid="stFormSubmitButton"] button:hover,[data-testid="stDownloadButton"] button:hover,
[data-testid^="stBaseButton-secondary"]:hover,[data-testid^="stBaseButton-primary"]:hover,[data-testid="stNumberInput"] button:hover{
  background:#e5e7eb!important;background-color:#e5e7eb!important;border-color:#9ca3af!important;transform:none!important;box-shadow:none!important;}
.stButton button:disabled{opacity:.45!important;}
[class*="st-key-fav_ticker_"] button,[class*="st-key-fav_action_"] button{background:#fff!important;background-color:#fff!important;}
[class*="st-key-fav_ticker_"] button:hover,[class*="st-key-fav_action_"] button:hover:not(:disabled){background:#f3f4f6!important;background-color:#f3f4f6!important;}

/* 탭 — 밑줄형 */
.stTabs [data-baseweb="tab-list"]{background:transparent!important;border:none!important;border-bottom:1px solid var(--m-line)!important;
  border-radius:0!important;box-shadow:none!important;padding:0!important;gap:.25rem!important;}
.stTabs [data-baseweb="tab"]{border-radius:0!important;color:var(--m-mute)!important;font-family:var(--font-body)!important;
  font-weight:500!important;border:none!important;background:transparent!important;}
.stTabs [aria-selected="true"]{background:transparent!important;color:var(--m-ink)!important;font-weight:700!important;border:none!important;}
.stTabs [data-baseweb="tab-highlight"]{display:block!important;background:var(--m-accent)!important;height:2px!important;}
.stTabs [data-baseweb="tab-border"]{display:none!important;}

/* 세그먼트 컨트롤 — 흰 필, 선택 시 옅은 회색 + 진한 테두리 (글씨는 항상 검정) */
[data-testid="stSegmentedControl"],[data-testid="stButtonGroup"]{background:transparent!important;border:none!important;box-shadow:none!important;padding:0!important;gap:.4rem!important;flex-wrap:wrap!important;}
[data-testid="stSegmentedControl"] button,[data-testid="stButtonGroup"] button,
[data-testid^="stBaseButton-segmented"],[data-testid^="stBaseButton-pills"],button[kind^="segmented_control"],button[kind^="pills"]{
  background:#fff!important;background-color:#fff!important;background-image:none!important;
  color:#111827!important;-webkit-text-fill-color:#111827!important;
  border:1px solid #d1d5db!important;border-radius:var(--radius-pill)!important;box-shadow:none!important;opacity:1!important;
  font-family:var(--font-body)!important;font-weight:500!important;font-size:.88rem!important;}
[data-testid="stSegmentedControl"] button *,[data-testid="stButtonGroup"] button *,[data-testid^="stBaseButton-segmented"] *,
[data-testid^="stBaseButton-pills"] *,button[kind^="segmented_control"] *,button[kind^="pills"] *{
  color:#111827!important;-webkit-text-fill-color:#111827!important;fill:#111827!important;opacity:1!important;}
[data-testid="stSegmentedControl"] button:hover,[data-testid^="stBaseButton-segmented"]:hover,[data-testid^="stBaseButton-pills"]:hover{
  background:#f3f4f6!important;background-color:#f3f4f6!important;border-color:#9ca3af!important;}
[data-testid="stSegmentedControl"] button[aria-checked="true"],[data-testid="stSegmentedControl"] button[aria-pressed="true"],
[data-testid="stSegmentedControl"] button[aria-selected="true"],[data-testid$="Active"],button[kind$="Active"]{
  background:#e5e7eb!important;background-color:#e5e7eb!important;border-color:#111827!important;font-weight:700!important;}

/* 입력 · 표 · 알림 · 폼 — 모두 흰 바탕 + 검정 글씨 (폰 다크모드여도 동일) */
[data-baseweb="input"],[data-baseweb="base-input"],[data-baseweb="textarea"],[data-baseweb="select"]>div,
[data-testid="stTextInputRootElement"],[data-testid="stNumberInputContainer"]{
  background:#fff!important;background-color:#fff!important;border-color:#d1d5db!important;}
[data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"]>div,[data-testid="stTextInputRootElement"]{
  border:1px solid #d1d5db!important;border-radius:10px!important;box-shadow:none!important;}
[data-baseweb="base-input"]{border:none!important;}
[data-baseweb="input"]:focus-within,[data-baseweb="textarea"]:focus-within,[data-testid="stTextInputRootElement"]:focus-within{border-color:#111827!important;}
input,textarea,[data-baseweb="input"] input,[data-baseweb="select"] *,[data-testid="stSidebar"] .stTextInput input,[data-testid="stSidebar"] input{
  background:#fff!important;background-color:#fff!important;color:#111827!important;-webkit-text-fill-color:#111827!important;caret-color:#111827!important;}
input::placeholder,textarea::placeholder{color:#9ca3af!important;-webkit-text-fill-color:#9ca3af!important;}
[data-testid="stWidgetLabel"],[data-testid="stWidgetLabel"] *,label{color:#111827!important;}
.stTextArea textarea{border:1px solid #d1d5db!important;border-radius:10px!important;box-shadow:none!important;}
[data-testid="stForm"]{border:1px solid var(--m-line)!important;border-radius:var(--radius-card)!important;box-shadow:none!important;background:transparent!important;}
[role="slider"]{background:#111827!important;border:2px solid #fff!important;border-radius:50%!important;box-shadow:0 0 0 1px #111827!important;}
[data-testid="stSliderThumbValue"],[data-testid="stSliderTickBarMin"],[data-testid="stSliderTickBarMax"]{color:#111827!important;}
[data-testid="stExpander"] details{background:#fff!important;border:1px solid var(--m-line)!important;border-radius:var(--radius-card)!important;box-shadow:none!important;}
[data-testid="stExpander"] summary,[data-testid="stExpander"] summary *{color:#111827!important;}
[data-testid="stAlert"]{background:#fff!important;border:1px solid var(--m-line)!important;border-radius:10px!important;box-shadow:none!important;}
[data-testid="stAlert"] *{color:#111827!important;}
[data-testid="stDataFrame"]{border:1px solid var(--m-line)!important;border-radius:10px!important;box-shadow:none!important;overflow:hidden;}
/* 체크박스 — 미선택=흰 네모, 선택=옅은 회색 + 검정 체크 */
[data-testid="stCheckbox"] label>span:first-child,label[data-baseweb="checkbox"]>span:first-of-type{
  background:#fff!important;background-color:#fff!important;border:1.5px solid #6b7280!important;border-radius:4px!important;}
[data-testid="stCheckbox"] label:has(input:checked)>span:first-child,label[data-baseweb="checkbox"]:has(input:checked)>span:first-of-type{
  background:#e5e7eb!important;background-color:#e5e7eb!important;border-color:#111827!important;}
[data-testid="stCheckbox"] svg,label[data-baseweb="checkbox"] svg{color:#111827!important;fill:#111827!important;stroke:#111827!important;}
[data-testid="stCheckbox"] [data-testid="stTooltipIcon"] svg{color:#6b7280!important;fill:#6b7280!important;stroke:none!important;}
[data-testid="stTooltipIcon"] svg{color:#6b7280!important;fill:#6b7280!important;}
/* 드롭다운 · 멀티셀렉트 태그 · 파일 업로더 */
[data-baseweb="popover"],[data-baseweb="popover"] *,[data-baseweb="menu"],[data-baseweb="menu"] *,ul[role="listbox"],ul[role="listbox"] *{
  background-color:#fff!important;color:#111827!important;-webkit-text-fill-color:#111827!important;}
[data-baseweb="menu"] li:hover,ul[role="listbox"] li:hover{background-color:#f3f4f6!important;}
[data-baseweb="tag"]{background-color:#e5e7eb!important;border:1px solid #d1d5db!important;}
[data-baseweb="tag"] *{color:#111827!important;-webkit-text-fill-color:#111827!important;background-color:transparent!important;}
[data-testid="stFileUploaderDropzone"]{background:#fff!important;border:1px dashed #9ca3af!important;border-radius:10px!important;}
[data-testid="stFileUploaderDropzone"] *{color:#111827!important;}
[data-testid="stFileUploaderDropzone"] button{background:#f3f4f6!important;border:1px solid #d1d5db!important;}
.sentiment-bar-track{background:var(--m-line-2)!important;border:none!important;border-radius:var(--radius-pill)!important;height:8px!important;}
.sentiment-bar-fill{background:var(--m-up)!important;border-radius:var(--radius-pill)!important;border-right:none!important;}

/* 상단 툴바(Share·별·메뉴) — 흰 배경에서도 보이게 */
[data-testid="stHeader"]{background:#fafafa!important;}
[data-testid="stToolbar"],[data-testid="stToolbar"] *,[data-testid="stHeader"] button,[data-testid="stHeader"] button *,[data-testid="stSidebarCollapseButton"] *,[data-testid="stExpandSidebarButton"] *{
  color:#111827!important;fill:#111827!important;opacity:1!important;}

/* 사이드바 */
[data-testid="stSidebar"]{background:#ffffff!important;border-right:1px solid var(--m-line)!important;}
[data-testid="stSidebar"] :is(label,p,span,h1,h2,h3,li,small,a){color:#111827!important;}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] *{color:var(--m-mute)!important;}

@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important;}}
"""

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
        # 보조 텍스트는 불투명 솔리드 컬러로 통일 (배경과 명암만 다른 회색 사용 금지)
        text_muted   = "#8fc4e8"
        text_dimmed  = "#e0b374"
        text_status  = "#cbd5e1"
        metric_label = "#8fc4e8"
        sidebar_input_bg  = "rgba(255,255,255,0.05)"
        sidebar_input_bdr = "rgba(139,92,246,0.4)"
        sidebar_input_clr = "#e2e8f0"
        textarea_bg  = "rgba(255,255,255,0.04)"
        plotly_tmpl  = "plotly_dark"
        sector_name_clr  = "#f8fafc"
        sector_ticker_clr= "#8fc4e8"
        social_selftext_bdr = "rgba(255,255,255,0.1)"
        social_selftext_clr = "#e0b374"

        # 위젯 스타일: 무광 플랫 배경 + 순검정 카드. 글로시 메시/파티클은 다크 모드에서도 비활성화.
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
        text_muted   = "#1d5c85"
        text_dimmed  = "#8a5a1e"
        text_status  = "#374151"
        metric_label = "#1d5c85"
        sidebar_input_bg  = "rgba(255,255,255,0.9)"
        sidebar_input_bdr = "rgba(90,91,214,0.4)"
        sidebar_input_clr = "#1e1b4b"
        textarea_bg  = "rgba(255,255,255,0.9)"
        plotly_tmpl  = "plotly_white"
        sector_name_clr  = "#1e1b4b"
        sector_ticker_clr= "#1d5c85"
        social_selftext_bdr = "rgba(90,91,214,0.2)"
        social_selftext_clr = "#8a5a1e"

        mesh_bg_layers      = ""
        mesh_bg_size        = "100% 100%"
        mesh_bg_anim        = "none"
        mesh_keyframes_css  = ""
        particle_overlay_css = ""

    st.session_state["_plotly_template"] = plotly_tmpl

    mesh_bg_comma = "," if mesh_bg_layers else ""
    light_mode_overrides = "" if dark else LIGHT_MODE_OVERRIDE_CSS

    css = Template(CSS_TEMPLATE).substitute(
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

    # 상단 요약 카드 2열→12열 그리드 및 카드 높이 오버라이드
    narrow_metric_cards_css = """
    .metric-grid {
        grid-template-columns: repeat(2, 1fr) !important;
        gap: 0.5rem !important;
    }
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

    # 인라인 style 하드코딩 rgba 텍스트를 다크/라이트 모두 불투명 색으로 통일
    unified_contrast_css = f"""
    [style*="color:rgba(148,163,184"], [style*="color: rgba(148,163,184"] {{
        color: {text_muted} !important;
    }}
    [style*="color:rgba(255,255,255"], [style*="color: rgba(255,255,255"] {{
        color: {"#ffffff" if dark else "#1e1b4b"} !important;
    }}
    [style*="color:rgba(254,202,202"], [style*="color: rgba(254,202,202"] {{
        color: {"#fecaca" if dark else "#7f1d1d"} !important;
    }}
    """

    st.markdown(f"\n{css}\n<style>{narrow_metric_cards_css}{unified_contrast_css}</style>\n<style>{MINIMAL_CSS}</style>\n", unsafe_allow_html=True)

inject_css(False)   # 미니멀 라이트 팔레트 고정

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
        chips = "".join([f'<span class="signal-chip">{_safe_html(r["티커"])} {_safe_html(r["🔔신호"])}</span>' for r in alert_tickers])
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
# Part 8 / 엑셀 종목 일괄 분석 (파싱 · 종목별 스캔 · 결과 표시)
# ════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════
# 엑셀 종목 일괄 분석 — 섹터별 정리 엑셀을 올리면 전 종목을 한 번에 분석
# ════════════════════════════════════════════════════════════════
def _is_krw_ticker(ticker: str) -> bool:
    return ticker.upper().endswith((".KS", ".KQ"))

def parse_watchlist_excel(uploaded) -> tuple:
    """엑셀(.xlsx)에서 (섹터, 티커[, 종목명]) 목록을 읽습니다. 티커가 빈 줄은 건너뜁니다.
    반환: (items, skipped_names)  — items: [{"섹터":..,"티커":..,"종목명":..}, ...]"""
    xl = pd.ExcelFile(uploaded)
    sheet = "종목" if "종목" in xl.sheet_names else xl.sheet_names[0]
    # "NA"(Nano Labs 티커)가 결측치로 읽히지 않도록 기본 NA 변환을 끈다
    df = xl.parse(sheet, keep_default_na=False, na_values=[""])
    cols = {str(c).strip().lower(): c for c in df.columns}
    def pick(*names):
        for n in names:
            if n.lower() in cols:
                return cols[n.lower()]
        return None
    c_tic = pick("티커", "ticker", "symbol", "종목코드")
    c_sec = pick("섹터", "sector", "업종")
    c_nam = pick("종목명(한글)", "종목명", "name")
    if c_tic is None:
        raise ValueError("엑셀에 '티커' 열이 없습니다. (열 이름: 티커 / ticker / symbol)")
    items, skipped, seen = [], [], set()
    for _, row in df.iterrows():
        ticker = str(row[c_tic]).strip().upper() if pd.notna(row[c_tic]) else ""
        name   = str(row[c_nam]).strip() if c_nam is not None and pd.notna(row[c_nam]) else ""
        sector = str(row[c_sec]).strip() if c_sec is not None and pd.notna(row[c_sec]) else "미분류"
        if not ticker or ticker == "NAN":
            if name:
                skipped.append(name)
            continue
        if ticker in seen:
            continue
        seen.add(ticker)
        items.append({"섹터": sector, "티커": ticker, "종목명": name})
    return items, skipped

def _fetch_history_retry(ticker: str, tries: int = 3) -> pd.DataFrame:
    """엑셀 일괄 스캔용 조회. 요청 제한·일시적 네트워크 오류는 대기 후 재시도하고,
    빈 결과는 캐시를 거치지 않고 한 번 더 직접 조회한다(캐시된 빈 결과로 오판 방지)."""
    last_exc = None
    empty_retried = False
    for n in range(tries):
        try:
            raw = fetch_history(ticker) if n == 0 else yf.Ticker(ticker).history(period="1y")
            if raw is not None and not raw.empty:
                return raw
            last_exc = None
            if empty_retried:
                return pd.DataFrame()
            empty_retried = True
        except Exception as e:
            last_exc = e
            if not _classify_error(e).startswith(("요청 제한", "네트워크")):
                raise
        time.sleep(1.5 * (n + 1))
    if last_exc is not None:
        raise last_exc
    return pd.DataFrame()


def scan_ticker_for_excel(item: dict, usd_krw: float, with_events: bool = False) -> dict:
    """한 종목을 분석해 표 한 줄(dict)로 반환. 실패해도 예외 대신 상태 문구를 담아 반환."""
    ticker = item["티커"]
    row = {"섹터": item["섹터"], "티커": ticker, "종목명": item.get("종목명", ""), "상태": "오류"}
    try:
        raw = _fetch_history_retry(ticker)
        if raw is None or raw.empty or len(raw) < 2:
            row["상태"] = "데이터 없음(티커 확인)"
            return row
        vol_3d = float(raw["Volume"].tail(3).mean())
        vol_3m_w = raw["Volume"].tail(63) if len(raw) >= 20 else raw["Volume"]
        vol_3m = float(vol_3m_w.mean())
        surge = round(vol_3d / vol_3m, 2) if vol_3m > 0 else None

        h = calc_indicators(raw.dropna())
        t, y = h.iloc[-1], h.iloc[-2]
        close, prev = float(t["Close"]), float(y["Close"])
        pct = (close - prev) / prev * 100 if prev else 0.0
        vol_ma20 = t["VOL_MA20"] if pd.notna(t["VOL_MA20"]) and t["VOL_MA20"] > 0 else 1
        vol_r  = float(t["Volume"]) / float(vol_ma20) * 100
        vol_dd = (float(t["Volume"]) / float(y["Volume"]) * 100) if y["Volume"] else 0.0
        rsi = float(t["RSI"]) if pd.notna(t["RSI"]) else None
        fx = 1.0 if _is_krw_ticker(ticker) else usd_krw
        tv_eok = round(close * float(t["Volume"]) * fx / 100_000_000, 1)
        gap = (float(t["Open"]) - prev) / prev * 100 if prev else 0.0

        m20 = calc_ma20_breakout(h)   # 20일선이격(%) 열에도 쓰이므로 신호 표시 여부와 상관없이 계산

        signals = []
        if vol_r >= 200: signals.append("🔥거래량")
        if surge is not None and surge >= 5: signals.append("📊3일5배")
        # 스윙용 신호(MACD·과매도·120일선·20일선)는 SHOW_SWING_SIGNALS=True일 때만 표시
        if SHOW_SWING_SIGNALS:
            if pd.notna(t["MACD"]) and pd.notna(t["MACD_SIG"]) and pd.notna(y["MACD"]) and pd.notna(y["MACD_SIG"]) \
                    and t["MACD"] > t["MACD_SIG"] and y["MACD"] <= y["MACD_SIG"]:
                signals.append("⚡MACD")
            if rsi is not None and rsi <= 35: signals.append("📉과매도")
            if pd.notna(t["MA120"]) and pd.notna(y["MA120"]) and close > t["MA120"] and prev <= y["MA120"]:
                signals.append("🚀120일선")
            if m20["breakout"]:
                signals.append("🚀20일선" + ("+량" if m20["vol_confirm"] else ""))
        float_turn, catalyst_txt = None, None
        if with_events:        # 뉴스·공시·유통주식수 조회가 종목당 추가되어 기본은 꺼 둠
            signals.extend(detect_corporate_events(ticker)["signals"])
            float_turn = calc_float_turnover(ticker, t["Volume"])
            catalyst_txt = catalyst_summary_text(ticker)
        if gap >= 5: signals.append("⬆️갭업")

        # 급등 전 매집·돌파 임박 예측 점수 (이미 급등한 종목은 상한 30점)
        _pb = calc_prebreakout_score(h)
        score = _pb.get("score")
        pb_stage = _pb.get("stage", "—")
        row.update({
            "상태": "정상", "통화": "₩" if _is_krw_ticker(ticker) else "$",
            "현재가": round(close, 2), "등락률(%)": round(pct, 2), "돌파임박점수": score, "단계": pb_stage,
            "거래량(MA20대비%)": round(vol_r, 0), "3일/3개월 거래량배율": surge,
            "RSI": round(rsi, 1) if rsi is not None else None,
            "20일선이격(%)": round(m20["gap_pct"], 1) if m20["gap_pct"] is not None else None,
            "거래대금(억원)": tv_eok, "신호": " ".join(signals) if signals else "—",
            "플로트회전(%)": float_turn, "재료": catalyst_txt,
        })
    except Exception as _e:
        _log_err("excel_scan:" + ticker, _e)
        row["상태"] = "오류: " + _classify_error(_e)
    return row

def _excel_results_to_bytes(df_all: pd.DataFrame, df_sector: pd.DataFrame) -> bytes:
    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        df_all.to_excel(xw, sheet_name="전체결과", index=False)
        df_sector.to_excel(xw, sheet_name="섹터요약", index=False)
    return buf.getvalue()

def render_excel_scan_results():
    data = st.session_state.get("excel_scan")
    if not data:
        return
    rows = data["rows"]
    df = pd.DataFrame(rows)
    ok = df[df["상태"] == "정상"].copy()
    bad = df[df["상태"] != "정상"]
    sig = ok[ok["신호"] != "—"] if not ok.empty else ok

    st.markdown(f"""
    <div class="scan-header">
        <span class="scan-title">📥 엑셀 종목 일괄 분석 &nbsp;·&nbsp; {len(ok)}/{len(df)}개 종목 분석 완료</span>
        <span style="font-size:0.82rem;font-weight:700;">🔔 신호 {len(sig)}건 · 오류 {len(bad)}건</span>
    </div>
    """, unsafe_allow_html=True)

    if len(bad):
        _reasons = bad["상태"].value_counts()
        st.caption("⚠️ 분석 실패 사유: " + " · ".join(f"{k} {v}건" for k, v in _reasons.items()))

    if data.get("skipped"):
        st.warning("티커가 비어 있어 건너뛴 종목 " + str(len(data["skipped"])) + "개: " + ", ".join(data["skipped"]))

    if ok.empty:
        st.error("분석된 종목이 없습니다. 티커를 확인해 주세요.")
    else:
        g = ok.groupby("섹터")
        sector_df = pd.DataFrame({
            "종목수": g.size(),
            "평균 등락률(%)": g["등락률(%)"].mean().round(2),
            "평균 돌파임박점수": g["돌파임박점수"].mean().round(1),
            "신호 종목수": g.apply(lambda x: int((x["신호"] != "—").sum())),
            "최고점수 종목": g.apply(lambda x: x.loc[x["돌파임박점수"].idxmax(), "티커"]),
        }).reset_index().sort_values("평균 돌파임박점수", ascending=False)
        st.markdown("**섹터 요약** (평균 돌파임박점수 높은 순)")
        st.dataframe(sector_df, use_container_width=True, hide_index=True)

        if not sig.empty:
            chips = "".join(f'<span class="signal-chip">{_safe_html(r["티커"])} {_safe_html(r["신호"])}</span>' for _, r in sig.iterrows())
            st.markdown(f"""
            <div class="alert-banner"><div class="alert-icon">🔔</div>
            <div><div class="alert-title">신호 감지 종목</div><div class="alert-signals">{chips}</div></div></div>
            """, unsafe_allow_html=True)

        show_cols = ["티커", "종목명", "통화", "현재가", "등락률(%)", "돌파임박점수", "단계", "거래량(MA20대비%)",
                     "3일/3개월 거래량배율", "RSI", "20일선이격(%)", "거래대금(억원)", "플로트회전(%)", "재료", "신호"]
        # 뉴스·이벤트 조회를 끈 스캔에서는 플로트회전/재료 열이 비어 있으므로 값이 하나도 없는 열은 숨긴다
        show_cols = [c for c in show_cols if c in ok.columns and not ok[c].isna().all()]
        order = sector_df["섹터"].tolist()
        for sec in order:
            part = ok[ok["섹터"] == sec].sort_values("돌파임박점수", ascending=False)
            label = f"{sec} · {len(part)}종목 · 평균 {part['등락률(%)'].mean():+.2f}%"
            with st.expander(label, expanded=False):
                st.dataframe(
                    part[show_cols], use_container_width=True, hide_index=True,
                    column_config={
                        "현재가": st.column_config.NumberColumn(format="%.2f"),
                        "등락률(%)": st.column_config.NumberColumn(format="%+.2f%%"),
                        "20일선이격(%)": st.column_config.NumberColumn(format="%+.1f%%"),
                        "돌파임박점수": st.column_config.NumberColumn(format="%.1f", help="급등 전 매집·돌파 임박 예측 점수"),
                        "거래량(MA20대비%)": st.column_config.NumberColumn(format="%d%%"),
                        "3일/3개월 거래량배율": st.column_config.NumberColumn(format="%.1f배"),
                        "거래대금(억원)": st.column_config.NumberColumn(format="%.1f"),
                    },
                )

    if not bad.empty:
        with st.expander(f"분석 못 한 종목 {len(bad)}개 (티커 확인 필요)"):
            st.dataframe(bad[["섹터", "티커", "종목명", "상태"]], use_container_width=True, hide_index=True)

    if not ok.empty:
        st.download_button(
            "결과 엑셀로 내려받기", key="dl_excel_scan",
            data=_excel_results_to_bytes(df, sector_df),
            file_name="섹터별_분석결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    if st.button("✕ 엑셀 분석 결과 닫기", key="close_excel_scan"):
        st.session_state["excel_scan"] = None
        st.rerun()
    st.markdown("---")

render_excel_scan_results()
# ════════════════════════════════════════════════════════════════
# Part 9 / 사이드바 (설정 · 토글 · 엑셀 업로드 · 티커 입력 · 즐겨찾기 · 키 설정 · 매물대 파라미터)
# ════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════
# 사이드바 — 티커 입력 및 파라미터
# ════════════════════════════════════════════════════════════════
st.sidebar.header("🔍 주식 분석 설정")

# ── 섹터 히트맵 / 급등주 검색기 / 거래량 급증 스크리너 토글 (스크롤 없이 바로 보이도록 상단 배치) ──
tcol1, tcol2, tcol3 = st.sidebar.columns(3)
tcol4, _tcol5, _tcol6 = st.sidebar.columns(3)
with tcol1:
    st.checkbox(
        "섹터 히트맵", key="show_heatmap",
        help="11개 섹터 ETF의 당일/1주/1개월 성과를 히트맵으로 표시합니다"
    )
with tcol2:
    st.checkbox(
        "급등주 검색기", key="show_screener",
        help="Yahoo Finance 실시간 스크리너로 조건에 맞는 급등 종목을 찾습니다"
    )
with tcol3:
    st.checkbox(
        "거래량 급증", key="show_vol_surge",
        help="최근 3일 평균 거래량이 최근 3개월 평균 대비 N배 이상인 나스닥 종목을 찾습니다"
    )
st.sidebar.checkbox(
    "🚫 상장폐지 확정 종목 제외", key="excl_delisted",
    help="Form 25·15 공시, 상장폐지 확정 뉴스, 청산, OTC 이전 종목을 검색기·스캐너 순위에서 뺍니다 (뉴스·공시 키워드 기반)")
st.sidebar.checkbox(
    "🚫 피인수(합병 확정) 종목 제외", key="excl_acquired",
    help="'to be acquired / all-cash deal' 등 인수가 확정돼 가격이 고정된 종목을 순위에서 뺍니다 (변동성이 낮고 거래량이 몰려 '급등 전' 패턴처럼 보이는 오탐 방지)")
with tcol4:
    st.checkbox(
        "급등 전 매집", key="show_prebreak",
        help="프리마켓 갭 5~15% 종목 중 촉매·프리마켓 거래량·플로트·일봉 위치로 장 시작 후 이어갈 후보를 등급(A/B/C)으로 찾습니다 (증자·역분할·인수확정 제외)"
    )
st.sidebar.markdown("---")

with st.sidebar.expander("엑셀 종목 일괄 분석", expanded=False):
    st.caption("섹터·티커가 들어 있는 엑셀(.xlsx)을 올리면 전 종목을 한 번에 분석해 섹터별로 정리합니다. "
               "('종목' 시트의 섹터/티커 열을 사용, 티커가 빈 줄은 건너뜀)")
    _xl_file = st.file_uploader("엑셀 파일", type=["xlsx"], key="excel_watchlist_upload")
    _xl_events = st.checkbox("📰 합병·인수·파산 이벤트 포함 (느림)", value=False, key="excel_scan_events",
                             help="종목마다 뉴스·SEC 공시를 추가로 조회합니다. 종목이 많으면 시간이 오래 걸리고 요청 제한에 걸릴 수 있습니다.")
    if _xl_file is not None and st.button("엑셀 종목 전체 분석", key="run_excel_scan", use_container_width=True):
        try:
            _items, _skipped = parse_watchlist_excel(_xl_file)
        except Exception as _e:
            st.error(f"엑셀을 읽지 못했습니다: {_e}")
            _items, _skipped = [], []
        if _items:
            _items = _items[:400]
            _prog = st.progress(0, text="분석 중...")
            _usd = fetch_usd_to_krw()
            _rows, _done = [], 0
            with ThreadPoolExecutor(max_workers=8) as _ex:
                _futs = [_ex.submit(scan_ticker_for_excel, it, _usd, _xl_events) for it in _items]
                for _f in as_completed(_futs):
                    _rows.append(_f.result())
                    _done += 1
                    _prog.progress(_done / len(_items), text=f"분석 중... {_done}/{len(_items)}")
            _prog.empty()
            st.session_state["excel_scan"] = {"rows": _rows, "skipped": _skipped}
            st.rerun()

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
    fav_count = len(st.session_state.favorites)
    # 목록이 길어져도 사이드바 공간을 차지하지 않도록 접이식(기본 접힘)으로 표시
    with st.sidebar.expander("⭐ 즐겨찾기", expanded=False):
        st.caption(f"총 {fav_count}개 · 티커를 누르면 입력창에 채워집니다")
        for idx, fav in enumerate(st.session_state.favorites):
            fav_col, up_col, down_col, del_col = st.columns([3, 1, 1, 1])
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

    # ── 즐겨찾기 일괄 스캔 ───────────────────────────────────────
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
                    vol_ma20   = t['VOL_MA20'] if t['VOL_MA20'] > 0 else 1
                    vol_r      = (t['Volume'] / vol_ma20) * 100
                    vol_ratio  = (t['Volume'] / y['Volume'] * 100) if y['Volume'] else 0
                    rsi        = t['RSI']
                    macd_cross = t['MACD'] > t['MACD_SIG'] and y['MACD'] <= y['MACD_SIG']
                    gap_up_pct = (t['Open'] - y['Close']) / y['Close'] * 100
                    trading_value_eok = round((t['Close'] * t['Volume'] * usd_krw) / 100_000_000, 1)

                    float_turn = calc_float_turnover(fav_ticker, t['Volume'])   # 플로트 회전율(%)
                    signals = []
                    if vol_r  >= 200:  signals.append("🔥거래량")
                    # 스윙용 신호는 SHOW_SWING_SIGNALS=True일 때만 표시
                    if SHOW_SWING_SIGNALS:
                        if macd_cross:     signals.append("⚡MACD")
                        if rsi    <= 35:   signals.append("📉과매도")
                        if t['Close'] > t['MA120'] and y['Close'] <= y['MA120']:
                                           signals.append("🚀120일선")
                        _m20 = calc_ma20_breakout(fav_hist)
                        if _m20["breakout"]:
                            signals.append("🚀20일선" + ("+량" if _m20["vol_confirm"] else ""))
                    signals.extend(detect_corporate_events(fav_ticker)["signals"])
                    if gap_up_pct >= 5:
                                       signals.append("⬆️갭업")
                    alert = " ".join(signals) if signals else "—"

                    _pb = calc_prebreakout_score(fav_hist)      # 급등 전 매집·돌파 임박 예측 점수
                    score = _pb.get("score")
                    pb_stage = _pb.get("stage", "—")

                    return {
                        "티커":      fav_ticker,
                        "현재가":    f"${t['Close']:.2f}",
                        "등락(%)":   f"{pct:+.2f}%",
                        "돌파임박":  f"{score:.0f} ({pb_stage})" if score is not None else "—",
                        "거래량(MA비%)": f"{vol_r:.0f}%",
                        "RSI":       f"{rsi:.1f}",
                        "플로트회전": f"{float_turn:.0f}%" if float_turn is not None else "—",
                        "재료":      catalyst_summary_text(fav_ticker),
                        "🔔신호":    alert,
                        "_pct": pct, "_volr": vol_r, "_gap": gap_up_pct,
                    }
            except Exception as _e:
                _log_err("favorites_scan:" + fav_ticker, _e)
                return {"티커": fav_ticker, "현재가": f"오류({_classify_error(_e)})", "등락(%)": "-",
                        "돌파임박": "-", "거래량(MA비%)": "-", "RSI": "-", "🔔신호": "-"}
            return {"티커": fav_ticker, "현재가": "데이터 없음", "등락(%)": "-",
                    "돌파임박": "-",
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

        flags = []
        for r in scan_data:
            try:
                flags.append(is_surge_candidate(r.get("_pct", 0), r.get("_volr", 0), r.get("_gap", 0)))
            except Exception:
                flags.append(False)
        attach_beams(scan_data, "티커", "🔔신호", flags)
        for r in scan_data:
            for k in ("_pct", "_volr", "_gap"):
                r.pop(k, None)   # 표에 나오지 않게 제거

        st.session_state.scan_results = scan_data
        st.rerun()
else:
    st.sidebar.markdown("---")
    st.sidebar.caption("☆ 버튼으로 즐겨찾기를 추가하세요")

# ════════════════════════════════════════════════════════════════
# AI 차트 해석 — Gemini API 키 설정
# 키는 st.secrets 또는 세션 입력으로만 사용하며 서버 파일에 저장하지 않는다.
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
# 악성매물대(저항선) 분석 파라미터 — 사이드바에서 조절 가능
# ════════════════════════════════════════════════════════════════
st.sidebar.markdown("---")
with st.sidebar.expander("⚙️ 매물대 분석 설정", expanded=False):
    supply_lookback_days = st.slider(
        "분석 기간 (거래일)", min_value=60, max_value=504, value=120, step=6,
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
    # ════════════════════════════════════════════════════════════════
# Part 10 / 메인 화면 렌더링 함수 (요약 카드 · 기술적 분석 · 히트맵 · 검색기 · 뉴스)
# ════════════════════════════════════════════════════════════════

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
    rsi_status  = "과매수" if current_rsi >= 70 else ("과매도" if current_rsi <= 30 else "보통")
    score_label = None
    if score is not None:
        score_label = "임박" if score >= 75 else ("준비" if score >= 60 else ("관찰" if score >= 45 else "해당없음"))

    pct_color = "delta-up" if price_chg >= 0 else "delta-down"
    pct_arrow = "▲" if price_chg >= 0 else "▼"
    rsi_color = "delta-down" if current_rsi >= 70 else ("delta-up" if current_rsi <= 30 else "delta-neu")

    score_card_html = ""
    if score is not None:
        score_color = "delta-up" if score_label in ("임박", "준비") else ("delta-neu" if score_label == "관찰" else "delta-down")
        score_card_html = (
            f'<div class="metric-card mc-amber" style="grid-column: span 3;">'
            f'<div class="metric-label">돌파 임박 점수</div>'
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
        f'<div class="metric-value">{current_rsi:.1f}</div>'
        f'<div class="metric-delta {rsi_color}">{rsi_status}</div>'
        f'</div>'
        f'{score_card_html}'
    )
    return front_html, end_html


# ════════════════════════════════════════════════════════════════
# 렌더링 함수 — 기술적 분석
# ════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════
# 단타 보조 분석 — 시간보정 RVOL · 플로트 회전율 · 가까운 저항 · ATR 손절/손익비
# ════════════════════════════════════════════════════════════════
@st.cache_data(ttl=120, show_spinner=False)
def calc_time_adjusted_rvol(ticker: str) -> dict:
    """같은 시각까지의 평균 누적 거래량 대비 오늘 누적 거래량(시간보정 상대거래량, RVOL).

    왜 필요한가? 일봉 기준 "오늘 거래량 ÷ 20일 평균 일 거래량"은 장 초반에 항상 낮게 나옵니다.
    그래서 최근 며칠의 1분봉을 받아 "지금 시각(예: 10:15)까지의 누적 거래량"끼리 비교합니다.
    (yfinance 1분봉은 최근 약 5거래일만 제공되므로 평균은 '최근 4~5일 평균'입니다 — 30일 평균이 아님)
    반환: {"rvol": 배수, "cutoff": "HH:MM", "n_days": 비교한 일수} / 계산 불가 시 {}
    """
    try:
        raw = yf.Ticker(ticker).history(period="5d", interval="1m", prepost=False)
    except Exception as _e:
        _log_err("calc_time_adjusted_rvol:" + ticker, _e)
        return {}
    if raw is None or raw.empty:
        return {}
    raw.index = pd.to_datetime(raw.index)
    days = sorted(set(raw.index.date))
    if len(days) < 2:
        return {}
    today_df = raw[raw.index.date == days[-1]]
    cutoff = today_df.index.max().time()          # 오늘 데이터의 마지막 시각
    today_cum = float(today_df["Volume"].sum())
    prev_cums = []
    for d in days[:-1]:
        day_df = raw[raw.index.date == d]
        v = float(day_df[day_df.index.time <= cutoff]["Volume"].sum())   # 같은 시각까지만 합산
        if v > 0:
            prev_cums.append(v)
    if not prev_cums:
        return {}
    avg_cum = sum(prev_cums) / len(prev_cums)
    return {"rvol": today_cum / avg_cum, "cutoff": cutoff.strftime("%H:%M"), "n_days": len(prev_cums)}


def calc_atr(hist: pd.DataFrame, period: int = 14) -> float:
    """ATR(평균 진폭): 하루 평균 얼마나 움직이는지($). 손절폭을 잡는 기준으로 사용."""
    h, l, c = hist["High"], hist["Low"], hist["Close"]
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period, min_periods=5).mean().iloc[-1]
    return float(atr) if pd.notna(atr) else 0.0


def calc_near_resistances(ticker: str, price: float, today, yesterday) -> list:
    """현재가 위쪽의 가까운 저항 후보(전일 고가·당일 고가·프리마켓 고가·라운드 넘버)를 가까운 순으로 반환.
    반환: [(이름, 가격), ...]  — 1년치 매물대보다 단타에서 더 먼저 부딪히는 가격대입니다."""
    levels = [("전일 고가", float(yesterday["High"])), ("당일 고가", float(today["High"]))]
    try:
        intr = fetch_intraday_5min(ticker)
        if not intr.empty and "Session" in intr.columns:
            mins = intr.index.hour * 60 + intr.index.minute
            pre = intr[(intr["Session"] == "EXT") & (mins < 570)]    # 09:30(ET) 이전 = 프리마켓
            if not pre.empty:
                levels.append(("프리마켓 고가", float(pre["High"].max())))
    except Exception as _e:
        _log_err("calc_near_resistances", _e)
    import math
    levels.append((f"라운드 ${math.floor(price) + 1}", float(math.floor(price) + 1)))
    five = (math.floor(price / 5) + 1) * 5
    levels.append((f"라운드 ${five}", float(five)))
    # 현재가보다 0.1% 이상 위에 있는 것만, 가까운 순으로 정렬하고 같은 가격은 하나만 남긴다
    above = sorted([x for x in levels if x[1] > price * 1.001], key=lambda x: x[1])
    out, seen = [], set()
    for name, lv in above:
        key = round(lv, 2)
        if key not in seen:
            seen.add(key)
            out.append((name, lv))
    return out


def calc_premarket_summary(ticker: str, hist: pd.DataFrame) -> dict:
    """프리마켓(04:00~09:30 ET) 갭 %, 누적 거래량, 고가를 계산. 프리마켓 거래가 없으면 {}.

    전일 종가 기준을 잡을 때 주의: 장 시작 전에는 일봉의 마지막 행이 '어제'이고,
    장이 열린 뒤에는 마지막 행이 '오늘'이라서 하루 앞의 행을 전일 종가로 써야 합니다.
    그래서 5분봉의 날짜와 일봉 마지막 날짜를 비교해 전일 종가를 고릅니다."""
    try:
        intr = fetch_intraday_5min(ticker)
        if intr.empty or "Session" not in intr.columns or len(hist) < 2:
            return {}
        mins = intr.index.hour * 60 + intr.index.minute
        pre = intr[(intr["Session"] == "EXT") & (mins < 570)]
        if pre.empty:
            return {}
        intr_date = intr.index[-1].date()
        last_daily_date = pd.to_datetime(hist.index[-1]).date()
        prev_close = float(hist["Close"].iloc[-1] if last_daily_date < intr_date else hist["Close"].iloc[-2])
        if prev_close <= 0:
            return {}
        last_px = float(pre["Close"].iloc[-1])
        return {"gap": (last_px / prev_close - 1) * 100, "volume": int(pre["Volume"].sum()),
                "high": float(pre["High"].max()), "prev_close": prev_close}
    except Exception as _e:
        _log_err("calc_premarket_summary:" + ticker, _e)
        return {}


def render_daytrade_panel(ticker: str, hist, today, yesterday, info: dict):
    """단타용 보조 지표 카드: 시간보정 RVOL, 유통주식수/플로트 회전율, 공매도, 가까운 저항, ATR 손절·손익비."""
    ui_section_header(mono_icon_badge("target", color="var(--c-rose)"),
                      "단타 보조 분석", "icon-rose", "title-rose")
    price = float(today["Close"])
    rows = []

    # 0) 단타 셋업 등급 (재료×수급×진입위치×손익비×거래가능성, 게이트 적용)
    su = compute_setup_for_ticker(ticker)
    if su:
        gdot = {"A": "dot-green", "B": "dot-green", "C": "dot-yellow"}.get(su["grade"], "dot-red")
        cap_txt = f" · 상한 {su['cap']}점({_safe_html(su['cap_reason'])})" if su.get("cap") else ""
        rows.append((gdot, f"<strong>셋업 {su['grade']}등급 · {su['score']:.0f}점</strong> ({_safe_html(su['setup'])}){cap_txt} — {_safe_html(su['why'])}"))
        if su.get("warn"):
            rows.append(("dot-red", f"<strong>경고</strong> {_safe_html(su['warn'])}"))

    # 1) 시간보정 RVOL
    rv = calc_time_adjusted_rvol(ticker)
    if rv:
        dot = "dot-green" if rv["rvol"] >= 5 else ("dot-yellow" if rv["rvol"] >= 2 else "dot-blue")
        rows.append((dot, f"<strong>시간보정 RVOL {rv['rvol']:.1f}배</strong> — {rv['cutoff']}까지 누적 거래량을 "
                          f"최근 {rv['n_days']}일 같은 시각 평균과 비교 (5배 이상이면 강한 수급)"))
    else:
        rows.append(("dot-blue", "시간보정 RVOL — 1분봉 데이터를 가져오지 못했습니다"))

    # 1-2) 프리마켓 갭 · 거래량 (기준: 전일 종가 대비 프리마켓 마지막 가격)
    pm = calc_premarket_summary(ticker, hist)
    if pm:
        dot = "dot-green" if (pm["gap"] >= 5 and pm["volume"] >= 200_000) else ("dot-yellow" if pm["gap"] >= 0 else "dot-red")
        rows.append((dot, f"<strong>프리마켓 갭 {pm['gap']:+.1f}%</strong> (전일 종가 ${pm['prev_close']:.2f} 대비) · "
                          f"프리마켓 거래량 <strong>{pm['volume']:,}주</strong> · 프리마켓 고가 ${pm['high']:.2f}"
                          f"{' — 갭 +5% · 거래량 20만 주 이상 충족' if dot == 'dot-green' else ''}"))
    else:
        rows.append(("dot-blue", "프리마켓 거래 데이터 없음 (프리마켓 시간이 아니거나 거래 없음)"))

    # 2) 유통주식수 · 플로트 회전율 · 시총
    fl = info.get("floatShares") or 0
    if fl:
        turn = float(today["Volume"]) / fl * 100
        low_float = fl <= 20_000_000
        dot = "dot-green" if (low_float and turn >= 100) else ("dot-yellow" if low_float else "dot-blue")
        rows.append((dot, f"<strong>유통주식 {fl / 10_000:,.0f}만 주</strong>"
                          f"{' (2천만 이하 · 저유통)' if low_float else ''} · "
                          f"<strong>플로트 회전율 {turn:.0f}%</strong> (당일 거래량 ÷ 유통주식수)"))
    else:
        rows.append(("dot-blue", "유통주식수 정보 없음 — 플로트 회전율을 계산할 수 없습니다"))
    mc = info.get("marketCap") or 0
    if mc:
        rows.append(("dot-blue", f"시가총액 약 <strong>${mc / 1_000_000:,.0f}M</strong>"))

    # 3) 공매도 비율 · 호가 스프레드 (공매도 데이터는 갱신이 느려 참고용)
    spf = info.get("shortPercentOfFloat")
    if spf:
        rows.append(("dot-yellow" if spf >= 0.2 else "dot-blue",
                     f"공매도 비율 <strong>{spf * 100:.1f}%</strong> (유통주식 대비, 갱신 느림 · 참고용)"))
    bid, ask = info.get("bid") or 0, info.get("ask") or 0
    if bid and ask and ask >= bid:
        spread = (ask - bid) / ((ask + bid) / 2) * 100
        rows.append(("dot-yellow" if spread >= 1 else "dot-blue", f"호가 스프레드 <strong>{spread:.2f}%</strong> (넓을수록 체결 손실 큼)"))

    # 4) 재료(뉴스) 종류와 신선도 — 재료 없이 움직이는 종목은 끝나는 시점을 알 수 없어 위험
    cats = detect_catalysts(ticker)
    if cats:
        seen, shown = set(), []
        for c in cats:
            if c["key"] in seen:
                continue
            seen.add(c["key"])
            shown.append(c)
        for c in shown[:3]:
            title = _safe_html(c["title"])[:80]
            link = _safe_url(c["link"])
            if link:
                title = f'<a href="{link}" target="_blank" rel="noopener" style="color:inherit;text-decoration:underline;">{title}</a>'
            if not c["good"]:
                dot = "dot-red"
            else:
                dot = "dot-green" if c["hours"] <= 24 else ("dot-yellow" if c["hours"] <= 72 else "dot-blue")
            rows.append((dot, f"<strong>{c['label']}</strong> · {c['age']} — {title}"))
    else:
        rows.append(("dot-yellow", "최근 7일 안에 분류된 재료(FDA·계약·실적·오퍼링·애널리스트) 뉴스 없음 — "
                                   "재료 없는 급등은 지속성을 확신하기 어렵습니다"))
    try:
        offs = fetch_offering_history(ticker)
        if offs:
            d = pd.to_datetime(offs[0].get("date"), errors="coerce", utc=True)
            if pd.notna(d):
                days_ago = max((pd.Timestamp.now(tz="UTC") - d).days, 0)
                if days_ago <= 30:
                    rows.append(("dot-red" if days_ago <= 7 else "dot-yellow",
                                 f"<strong>오퍼링 관련 공시 {days_ago}일 전</strong> ({_safe_html(offs[0].get('type', ''))}) — 희석 위험, 원문 확인"))
    except Exception as _e:
        _log_err("render_daytrade_panel:offering", _e)

    # 5) 가까운 저항 + ATR 손절 / 손익비
    res = calc_near_resistances(ticker, price, today, yesterday)
    if res:
        res_txt = " → ".join(f"{n} <strong>${v:.2f}</strong> (+{(v / price - 1) * 100:.1f}%)" for n, v in res[:4])
        rows.append(("dot-blue", f"가까운 저항: {res_txt}"))
    atr = calc_atr(hist)
    if atr > 0:
        stop = max(price - atr, 0.0)
        msg = f"ATR(14) <strong>${atr:.2f}</strong> → ATR 1배 손절가 <strong>${stop:.2f}</strong> (-{atr / price * 100:.1f}%)"
        if res:
            rr = (res[0][1] - price) / atr
            msg += f" · 첫 저항({res[0][0]})까지 손익비 <strong>{rr:.1f} : 1</strong>"
        rows.append(("dot-green" if res and (res[0][1] - price) / atr >= 2 else "dot-yellow", msg))

    items = "".join(f'<div class="status-item"><div class="status-dot {d}"></div><div class="status-text">{t}</div></div>'
                    for d, t in rows)
    st.markdown(f'<div class="glass-card"><div class="status-row">{items}</div></div>', unsafe_allow_html=True)
    st.caption("ATR 1배 손절과 손익비는 가격 변동폭 기준의 단순 계산입니다. 실제 손절가는 본인 매매 계획에 맞게 정하세요.")


def render_technical_analysis(ticker_input, hist, today, yesterday, vol_ratio,
                               vol_ma20_ratio, trading_value_krw_eok, threshold_eok,
                               high_52w, low_52w, spike_df=None, offering_list=None,
                               nasdaq_compliance=None, top_cards_front="", top_cards_end=""):
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
                <div class="china-banner-sub">본사 소재지: {_safe_html(country)} — VIE 구조, 회계 투명성, 규제 리스크 등을 반드시 확인하세요</div>
            </div>
        </div>
        """

    if not top_cards_front:
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
    _ma20        = calc_ma20_breakout(hist)
    _events      = detect_corporate_events(ticker_input)

    # ── 🔔 급등 신호 배너 ────────────────────────────────────────
    alert_signals = []
    if vol_ma20_ratio >= 200:    alert_signals.append(f"🔥 거래량 MA20 대비 {vol_ma20_ratio:.0f}%")
    # 아래 4개는 스윙용(느린) 신호라 SHOW_SWING_SIGNALS=True일 때만 칩에 표시한다
    if SHOW_SWING_SIGNALS and macd_cross:
        alert_signals.append("⚡ MACD 골든크로스")
    if SHOW_SWING_SIGNALS and rsi_val <= 35:
        alert_signals.append("📉 RSI 과매도")
    if SHOW_SWING_SIGNALS and today['Close'] > today['MA120'] and yesterday['Close'] <= yesterday['MA120']:
        alert_signals.append("🚀 120일선 돌파")
    if SHOW_SWING_SIGNALS and _ma20["breakout"]:
        alert_signals.append("🚀 20일선 돌파" + (" (거래량 동반)" if _ma20["vol_confirm"] else ""))
    if pct_chg >= 5:             alert_signals.append(f"📈 당일 +{pct_chg:.1f}%")
    if gap_up_pct >= 5:          alert_signals.append(f"⬆️ 갭업 시초가 +{gap_up_pct:.1f}%")

    # ── 🧨 이벤트 빔 (병합/인수/파산) ──────────────────────────────
    try:
        beam_events = detect_event_beams(get_beam_news(ticker_input))
    except Exception as _e:
        _log_err("beam_events", _e)
        beam_events = []
    is_surging = (pct_chg >= 5) or (vol_ma20_ratio >= 200) or (gap_up_pct >= 5)
    for ev in beam_events:
        if is_surging:
            tag = "" if ev["strong"] else " (관련 가능성)"
            alert_signals.append(f"🧨 {ev['kind']} 가능성{tag} — 뉴스+급등 동반")

    alert_banner_html = ""
    if alert_signals:
        chips = "".join([f'<span class="signal-chip">{_safe_html(s)}</span>' for s in alert_signals])
        alert_banner_html = f"""
        <div class="alert-banner">
            <div class="alert-icon">🔔</div>
            <div>
                <div class="alert-title">급등 신호 감지!</div>
                <div class="alert-signals">{chips}</div>
            </div>
        </div>
        """

    alert_banner_html += build_event_banner_html(_events)

    if not top_cards_front and alert_banner_html:
        st.markdown(alert_banner_html, unsafe_allow_html=True)

    # ── 메트릭 카드 ───────────────────────────────────────────────
    gap_52w_high = ((high_52w - today['Close']) / high_52w) * 100
    gap_52w_low  = ((today['Close'] - low_52w) / low_52w) * 100

    # ── 시가총액 & 유통주식수 조회 ───────────────────────────────
    MC_LOW  = 4_000_000
    MC_HIGH = 500_000_000
    FLOAT_MAX = 20_000_000

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
        mc_star     = (market_cap_raw > 0) and (MC_LOW <= market_cap_raw <= MC_HIGH)
        shares_star = (shares_float_raw > 0) and (shares_float_raw <= FLOAT_MAX)
    except Exception:
        market_cap_str = "N/A"
        shares_str     = "N/A"
        mc_star        = False
        shares_star    = False

    mc_star_html     = ' <span style="color:#e0943a;font-size:1rem;vertical-align:middle;" title="소형주 최적 구간 ($4M~$500M)">⭐</span>' if mc_star else ""
    shares_star_html = ' <span style="color:#e0943a;font-size:1rem;vertical-align:middle;" title="저부동주 조건 (20M주 이하)">⭐</span>' if shares_star else ""

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
    </div>
    """, unsafe_allow_html=True)

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
        ui_section_header(mono_icon_badge("trend", color="var(--c-teal)"), "이동평균·보조지표 (스윙용 · 참고)", "icon-teal", "title-teal")

        if today['MA5'] > today['MA20'] > today['MA120']:
            ma_dot, ma_text = "dot-green", "<strong>완전 정배열</strong> — 강력한 상승 추세 유지 중"
        elif today['Close'] > today['MA120'] and yesterday['Close'] <= yesterday['MA120']:
            ma_dot, ma_text = "dot-green", "<strong>120일선 돌파!</strong> — 급등 초입 타점"
        else:
            ma_dot, ma_text = "dot-blue", f"이평선 밀집 — 에너지 응축 횡보 구간 &nbsp;|&nbsp; MA5 <strong>${today['MA5']:.1f}</strong> / MA20 <strong>${today['MA20']:.1f}</strong>"

        ma20_dot, ma20_txt = ma20_status(_ma20)

        if rsi_val >= 70:
            # 급등주는 일봉 RSI 70 이상이 정상(강한 모멘텀)이라 경고 대신 참고 문구만 표시
            rsi_dot, rsi_txt = "dot-blue", f"<strong>RSI {rsi_val:.1f}</strong> — 강세 모멘텀 구간 (급등주에서는 정상, 과열 판단은 5분봉 RSI로)"
        elif rsi_val <= 30:
            rsi_dot, rsi_txt = "dot-yellow", f"<strong>RSI {rsi_val:.1f} — 과매도</strong> (급등주에서는 매수 신호가 아님, 참고용)"
        else:
            rsi_dot, rsi_txt = "dot-blue",   f"RSI <strong>{rsi_val:.1f}</strong> — 중립 구간 (30~70)"

        bb_range = today['BB_UPPER'] - today['BB_LOWER']
        bb_pct   = (today['Close'] - today['BB_LOWER']) / bb_range * 100 if bb_range else 50
        if today['Close'] >= today['BB_UPPER']:
            bb_dot, bb_txt = "dot-yellow", f"<strong>볼린저 상단 터치 ({bb_pct:.0f}%)</strong> — 과열 구간"
        elif today['Close'] <= today['BB_LOWER']:
            bb_dot, bb_txt = "dot-green",  f"<strong>볼린저 하단 터치 ({bb_pct:.0f}%)</strong> — 반등 구간"
        else:
            bb_dot, bb_txt = "dot-blue",   f"밴드 내부 <strong>{bb_pct:.0f}%</strong> 위치 &nbsp;|&nbsp; 밴드폭 {today['BB_WIDTH']:.1f}%"

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
                <div class="status-item"><div class="status-dot {ma20_dot}"></div><div class="status-text">{ma20_txt}</div></div>
                <div class="status-item"><div class="status-dot {rsi_dot}"></div><div class="status-text">{rsi_txt}</div></div>
                <div class="status-item"><div class="status-dot {bb_dot}"></div><div class="status-text">{bb_txt}</div></div>
                <div class="status-item"><div class="status-dot {mc_dot}"></div><div class="status-text">{mc_txt}</div></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col_breakout:
        render_breakout_probability(breakout_calc)

    # ── 🚫 상장폐지 확정·청산·피인수 확정 경고 ──
    render_delist_banner(ticker_input)

    # ── 🔮 급등 전 매집 · 돌파 임박 (변동성 축소 · 거래량 선행 · 20일선 직전) ──
    render_prebreakout_panel(hist)

    # ── 🎯 단타 보조 분석 (시간보정 RVOL · 플로트 회전율 · 저항 · ATR 손절) ──
    render_daytrade_panel(ticker_input, hist, today, yesterday, info)

    # ── 📰 합병·인수·파산 이벤트 신호 ─────────────────────────────
    render_event_signals(_events)

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
                _ou = _safe_url(o.get("url"))
                link_html = f"<a class='news-link' href='{_ou}' target='_blank'>공시 원문 →</a>" if _ou else ""
                rows_html += (
                    f"<div class='status-item'><div class='status-dot dot-yellow'></div>"
                    f"<div class='status-text'>📅 {_safe_html(o['date'])} &nbsp;<strong>{_safe_html(o['type'])}</strong> — {_safe_html(o['title'])} {link_html}</div></div>"
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
        else:
            st.markdown("""
            <div class="glass-card">
                <div class="status-row">
                    <div class="status-item"><div class="status-dot dot-blue"></div>
                    <div class="status-text">S-1 / S-3 / 424B 계열 오퍼링 관련 공시 이력이 조회되지 않았습니다</div></div>
                </div>
            </div>
            """, unsafe_allow_html=True)


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
                <div class="sector-name">{_safe_html(s['sector'])}</div>
                <div class="sector-ticker">{_safe_html(s['ticker'])}</div>
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

        top = sorted_data[0]
        bot = sorted_data[-1]
        top_bg, top_c = _sector_color(top[key])
        bot_bg, bot_c = _sector_color(bot[key])
        summary_html = f"""
        <div style="display:flex;gap:0.6rem;margin-bottom:0.9rem;flex-wrap:wrap;">
            <div style="flex:1;min-width:120px;background:{top_bg};border:1px solid {top_c}44;border-radius:10px;padding:0.6rem 0.8rem;">
                <div style="font-size:0.65rem;color:rgba(255,255,255,0.5);font-weight:700;text-transform:uppercase;margin-bottom:0.2rem;">🏆 최강 섹터</div>
                <div style="font-size:0.9rem;font-weight:800;color:{top_c};">{_safe_html(top['sector'])} ({_safe_html(top['ticker'])})</div>
                <div style="font-size:0.8rem;color:{top_c};">▲ {top[key]:.2f}%</div>
            </div>
            <div style="flex:1;min-width:120px;background:{bot_bg};border:1px solid {bot_c}44;border-radius:10px;padding:0.6rem 0.8rem;">
                <div style="font-size:0.65rem;color:rgba(255,255,255,0.5);font-weight:700;text-transform:uppercase;margin-bottom:0.2rem;">📉 최약 섹터</div>
                <div style="font-size:0.9rem;font-weight:800;color:{bot_c};">{_safe_html(bot['sector'])} ({_safe_html(bot['ticker'])})</div>
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
# ════════════════════════════════════════════════════════════════
# 단타 셋업 점수 (A/B/C/D 등급) — 기존 "종합점수"를 대체하는 구조
#
# 기존 점수의 문제: 등락률·거래량처럼 "이미 일어난 일"을 더하는 방식이라 이미 다 오른 종목이 1등,
# 초기 진입 후보가 꼴찌가 됐고, 재료 없음·오퍼링 같은 약점이 합산에 묻혔습니다.
#
# 새 구조
#  1) 게이트(상한): 오퍼링·나스닥 경고·재료 없음·스프레드 과대·유통주식 불명이면 점수 상한을 건다 (감점이 아님)
#  2) 셋업 점수(곱셈형): 재료 × 수급 × 진입위치 × 손익비 × 거래 가능성 — 하나라도 약하면 전체가 낮아진다
#  3) 출력: 등급 + 이유 태그 + 경고 태그
# ⚠️ 가중치(0.30/0.25/0.25/0.10/0.10)와 구간은 경험칙입니다. 아래 '결과 기록'으로 실제 성과를 쌓아 보정하세요.
# ════════════════════════════════════════════════════════════════
import math as _math

SETUP_WEIGHTS = {"catalyst": 0.30, "participation": 0.25, "extension": 0.25, "rr": 0.10, "tradability": 0.10}
GRADE_CUTS = (("A", 75), ("B", 60), ("C", 45))     # 이 점수 이상이면 해당 등급, 미만이면 D


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _clean_ticker(r: dict) -> str:
    return str(r.get("ticker", "")).replace("⚠️ ", "").strip()


def _extension_factor(pct: float) -> float:
    """등락률(또는 프리마켓 갭)이 '초기 진입'에 얼마나 적합한지 구간으로 평가.
    높을수록 좋은 게 아니라 +10~40%가 최적, 80% 넘으면 이미 늦은 자리라고 본다."""
    if pct is None:
        return 0.5
    if pct < 3:
        return 0.25
    if pct < 5:
        return 0.5
    if pct < 10:
        return 0.8
    if pct <= 40:
        return 1.0
    if pct <= 80:
        return 1.0 - (pct - 40) / 80          # 40%→1.0, 80%→0.5
    if pct <= 150:
        return 0.5 - (pct - 80) / 70 * 0.3    # 80%→0.5, 150%→0.2
    return 0.15


def attach_intraday_context(rows: list, limit: int = 30, max_workers: int = 6) -> None:
    """상위 limit개 종목에 장중 맥락(VWAP·당일 고가·저항·ATR 손익비·시간보정 RVOL·프리마켓 거래량)을 병렬로 붙인다.
    결과는 r["ctx_*"] 키로 저장. 장중 데이터를 못 받으면 r["ctx_ok"]=False."""
    targets = rows[:limit]

    def _one(r):
        t = _clean_ticker(r)
        out = {"ctx_ok": False}
        try:
            intr = fetch_intraday_5min(t)
            if intr is None or intr.empty:
                return r, out
            has_session = "Session" in intr.columns
            has_reg = bool((intr["Session"] == "REG").any()) if has_session else True
            base = intr[intr["Session"] == "REG"] if (has_session and has_reg) else intr
            price = float(intr["Close"].iloc[-1])
            vol = base["Volume"].astype(float)
            tp = (base["High"] + base["Low"] + base["Close"]) / 3
            vwap = float((tp * vol).sum() / vol.sum()) if vol.sum() > 0 else None
            day_high = float(base["High"].max())
            off_high = (day_high - price) / day_high * 100 if day_high > 0 else None

            # 전일 종가/고가: 장 시작 전엔 일봉 마지막 행이 '어제', 장중엔 두 번째 행이 '어제'
            intr_date = intr.index[-1].date()
            last_dt = r.get("last_date")
            use_last = last_dt is not None and last_dt < intr_date
            prev_close = r.get("last_close") if use_last else r.get("prev2_close")
            prev_high = r.get("last_high") if use_last else r.get("prev2_high")
            live_pct = (price / prev_close - 1) * 100 if prev_close else None

            res = calc_near_resistances(t, price, {"High": day_high}, {"High": prev_high or day_high})
            atr = r.get("atr") or 0
            stop = (price - atr) if atr > 0 else None
            res1 = res[0] if res else None
            rr = ((res1[1] - price) / atr) if (res1 and atr > 0) else None

            rvol_t = None
            if has_reg:     # 장 시작 전에는 직전 거래일 전체와 비교하게 되어 의미가 없으므로 계산하지 않음
                _rv = calc_time_adjusted_rvol(t)
                rvol_t = _rv.get("rvol") if _rv else None

            pm_vol = None
            if has_session:
                mins = intr.index.hour * 60 + intr.index.minute
                pre = intr[(intr["Session"] == "EXT") & (mins < 570)]
                pm_vol = int(pre["Volume"].sum()) if not pre.empty else 0

            out.update({
                "ctx_ok": True, "ctx_has_reg": has_reg, "ctx_price": price, "ctx_vwap": vwap,
                "ctx_above_vwap": (price >= vwap) if vwap else None,
                "ctx_day_high": day_high, "ctx_off_high": off_high, "ctx_live_pct": live_pct,
                "ctx_res1_name": res1[0] if res1 else None, "ctx_res1": res1[1] if res1 else None,
                "ctx_stop": stop, "ctx_rr": rr, "ctx_rvol_t": rvol_t, "ctx_pm_vol": pm_vol,
            })
        except Exception as _e:
            _log_err("attach_intraday_context:" + t, _e)
        return r, out

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for r, out in ex.map(_one, targets):
            r.update(out)


def calc_trade_setup(r: dict) -> dict:
    """한 종목의 단타 셋업을 평가해 {grade, score, setup, why, warn, factors, ...}를 반환.
    필요한 값: attach_catalysts + attach_intraday_context 가 붙인 키들 (없으면 중립값으로 처리하고 경고)."""
    why, warn, caps = [], [], []     # caps: (상한점수, 이유)

    # ── ① 재료 ──────────────────────────────────────────────
    if r.get("catalyst_checked"):
        f_cat = r.get("catalyst_score") or 0.0
        if f_cat <= 0:
            f_cat = 0.3
            caps.append((55, "호재성 재료 없음"))
        else:
            why.append(f"재료 {r.get('catalyst', '')}")
        if r.get("catalyst_offering_news"):
            warn.append("오퍼링 뉴스(72시간 내)")
            caps.append((50, "오퍼링 뉴스"))
    else:
        f_cat = 0.5
        warn.append("재료 미조회")

    # ── ② 수급(참여도) ─────────────────────────────────────
    ctx_ok = bool(r.get("ctx_ok"))
    has_reg = r.get("ctx_has_reg", True) if ctx_ok else True
    fl = r.get("float_shares")
    if has_reg:
        rvol = r.get("ctx_rvol_t")
        rvol_src = "시간보정"
        if rvol is None:
            rvol = (r.get("vol_ma20_ratio") or 0) / 100.0      # 일봉 기준 대체값(장 초반엔 낮게 나옴)
            rvol_src = "일봉"
        rvol_s = _clamp01(_math.log(max(rvol, 1.0)) / _math.log(8))     # 1배→0, 8배→1
        turn = r.get("float_turnover")
        if turn is None:
            f_part, why_part = rvol_s * 0.9, f"RVOL {rvol:.1f}배({rvol_src})"
        else:
            f_part = 0.6 * rvol_s + 0.4 * _clamp01(turn / 60.0)
            why_part = f"RVOL {rvol:.1f}배({rvol_src}) · 회전 {turn:.0f}%"
    else:
        # 프리마켓: 프리마켓 거래량이 평소 하루 거래량·유통주식수 대비 얼마나 되는지
        pm_vol = r.get("ctx_pm_vol") or r.get("pm_volume") or 0
        avg20 = r.get("avg_vol20") or 0
        rel = (pm_vol / avg20) if avg20 else 0.0
        pm_turn = (pm_vol / fl * 100) if fl else None
        if pm_turn is None:
            f_part = 0.9 * _clamp01(rel / 0.5)
        else:
            f_part = 0.5 * _clamp01(rel / 0.5) + 0.5 * _clamp01(pm_turn / 20.0)
        why_part = f"프리거래량 평소의 {rel * 100:.0f}%" + (f" · 프리회전 {pm_turn:.0f}%" if pm_turn is not None else "")
    f_part = max(f_part, 0.05)
    why.append(why_part)
    if fl is None:
        warn.append("유통주식수 불명")
        caps.append((70, "유통주식수 불명"))

    # ── ③ 진입 위치(확장도) ────────────────────────────────
    pct = r.get("ctx_live_pct") if r.get("ctx_live_pct") is not None else r.get("pct_change")
    f_ext = _extension_factor(pct)
    why.append(f"{'갭' if not has_reg else '등락'} {pct:+.0f}%" if pct is not None else "등락률 불명")
    if pct is not None and pct > 80:
        warn.append(f"이미 {pct:.0f}% 상승(늦은 자리)")
    if ctx_ok:
        if r.get("ctx_above_vwap") is False:
            f_ext *= 0.65
            warn.append("VWAP 아래")
        off = r.get("ctx_off_high")
        if off is not None:
            if off > 20:
                f_ext *= 0.6
                warn.append(f"고점 대비 -{off:.0f}% (꺾임)")
            elif off > 8:
                f_ext *= 0.85
                why.append(f"고점 대비 -{off:.0f}% 눌림")
    else:
        f_ext *= 0.8
        warn.append("장중 데이터 없음")
    f_ext = max(f_ext, 0.05)

    # ── ④ 손익비(첫 저항까지 / ATR 1배 손절) ───────────────
    rr = r.get("ctx_rr")
    if rr is None:
        f_rr = 0.7
    elif rr >= 3:
        f_rr = 1.0
    elif rr >= 2:
        f_rr = 0.85
    elif rr >= 1:
        f_rr = 0.5
    else:
        f_rr = 0.25
        warn.append("저항이 가까움(손익비 1 미만)")
    if rr is not None:
        why.append(f"손익비 {rr:.1f}")

    # ── ⑤ 거래 가능성(스프레드·거래대금) ──────────────────
    sp = r.get("spread_pct")
    f_trd = 1.0 if (sp is None or sp <= 1) else (0.8 if sp <= 3 else 0.5)
    if sp is not None and sp > 3:
        warn.append(f"스프레드 {sp:.1f}%")
        caps.append((50, "스프레드 과대"))
    tv = r.get("trading_value_eok") or 0
    f_trd *= 0.6 + 0.4 * _clamp01(tv / 270.0)

    # ── 게이트: 오퍼링·나스닥 경고 ─────────────────────────
    off_days = r.get("offering_days")
    if off_days is not None:
        if off_days <= 7:
            caps.append((40, f"오퍼링 공시 {off_days}일 전"))
            warn.append(f"오퍼링 공시 {off_days}일 전")
        elif off_days <= 30:
            caps.append((60, f"오퍼링 공시 {off_days}일 전"))
            warn.append(f"오퍼링 공시 {off_days}일 전")
    nr = r.get("nasdaq_risk") or {}
    if nr.get("applicable"):
        if nr.get("phase") == "notice_issued_est":
            caps.append((40, "나스닥 $1 유예기간"))
            warn.append(f"나스닥 유예 D-{nr.get('days_left', '?')}")
        else:
            caps.append((60, "나스닥 $1 미달"))
            warn.append(f"나스닥 $1 미달 {nr.get('streak_days', 0)}일째")
    if r.get("is_china"):
        warn.append("중국/홍콩계")

    # ── 곱셈형 합성 (가중 기하평균) ───────────────────────
    w = SETUP_WEIGHTS
    raw = (f_cat ** w["catalyst"]) * (f_part ** w["participation"]) * (f_ext ** w["extension"]) \
        * (f_rr ** w["rr"]) * (f_trd ** w["tradability"])
    score = raw * 100
    cap_val = min([c[0] for c in caps], default=100)
    score = min(score, cap_val)
    grade = "D"
    for g, cut in GRADE_CUTS:
        if score >= cut:
            grade = g
            break

    # A등급은 '손익비 2 이상 + VWAP 위'를 충족해야 한다 (점수가 높아도 자리가 나쁘면 B로 낮춤)
    if grade == "A":
        rr_ok = (rr is None) or rr >= 2
        vwap_ok = r.get("ctx_above_vwap") is not False
        if not (rr_ok and vwap_ok):
            grade = "B"
            warn.append("A 조건 미충족(손익비 2 이상·VWAP 위 필요)")

    # ── 셋업 유형 ─────────────────────────────────────────
    if not has_reg:
        setup = "갭앤고(프리마켓)"
    elif ctx_ok and r.get("ctx_above_vwap") is False:
        setup = "관망(VWAP 아래)"
    elif ctx_ok and (r.get("ctx_off_high") or 0) > 8:
        setup = "눌림 후 재상승 대기"
    else:
        setup = "장중 모멘텀"

    return {
        "grade": grade, "score": round(score, 1), "raw_score": round(raw * 100, 1), "setup": setup,
        "why": " · ".join(why), "warn": " · ".join(warn), "cap": cap_val if caps else None,
        "cap_reason": min(caps, key=lambda c: c[0])[1] if caps else "",
        "factors": {"catalyst": round(f_cat, 2), "participation": round(f_part, 2),
                    "extension": round(f_ext, 2), "rr": round(f_rr, 2), "tradability": round(f_trd, 2)},
    }


def apply_setup_to_rows(rows: list) -> None:
    """각 행에 calc_trade_setup 결과를 r["grade"], r["setup_score"] 등으로 붙인다."""
    for r in rows:
        if "catalyst_checked" not in r and "ctx_ok" not in r:
            r.update({"grade": "—", "setup_score": None, "setup": "", "why": "", "warn": "", "factors": {}})
            continue
        su = calc_trade_setup(r)
        r.update({"grade": su["grade"], "setup_score": su["score"], "setup": su["setup"],
                  "why": su["why"], "warn": su["warn"], "factors": su["factors"],
                  "setup_raw": su["raw_score"], "setup_cap": su["cap"]})


@st.cache_data(ttl=60, show_spinner=False)
def compute_setup_for_ticker(ticker: str) -> dict:
    """종목 상세 화면용: 한 종목에 대해 검색기와 같은 방식으로 셋업 평가를 수행."""
    try:
        enr = enrich_screener_results((ticker,)).get(ticker) or {}
        if not enr or enr.get("error"):
            return {}
        row = {"ticker": ticker, "price": enr.get("last_close"), "pct_change": enr.get("last_pct"), **enr}
        attach_catalysts([row], limit=1)
        attach_intraday_context([row], limit=1)
        su = calc_trade_setup(row)
        su["row"] = {k: row.get(k) for k in ("ctx_price", "ctx_stop", "ctx_res1_name", "ctx_res1", "ctx_rr")}
        return su
    except Exception as _e:
        _log_err("compute_setup_for_ticker:" + ticker, _e)
        return {}


# ════════════════════════════════════════════════════════════════
# 결과 기록 — 검색 후보와 점수 구성요소를 CSV로 남기고, 장 마감 후 실제 성과를 채워 등급별로 비교
# 저장 위치: 환경변수 SCREEN_LOG_PATH (기본 screen_log.csv).
# ⚠️ Streamlit Cloud 등은 재시작 시 파일이 초기화되므로 아래 '📥 기록 CSV 다운로드'로 정기 백업하세요.
# ════════════════════════════════════════════════════════════════
SCREEN_LOG_PATH = os.environ.get("SCREEN_LOG_PATH", "screen_log.csv")
_SCREEN_LOG_LOCK = threading.Lock()
SCREEN_LOG_COLUMNS = [
    "run_id", "logged_at_utc", "scan_mode", "ticker", "price", "grade", "score", "setup", "why", "warn",
    "f_catalyst", "f_participation", "f_extension", "f_rr", "f_tradability",
    "pct", "rvol", "float_turnover", "catalyst", "offering_days", "rr", "stop", "res1_name", "res1",
    "vwap", "off_high_pct", "atr",
    "out_status", "out_mfe_pct", "out_mae_pct", "out_close_pct", "out_R",
]


def _read_screen_log() -> pd.DataFrame:
    try:
        if os.path.exists(SCREEN_LOG_PATH):
            df = pd.read_csv(SCREEN_LOG_PATH)
            for c in SCREEN_LOG_COLUMNS:
                if c not in df.columns:
                    df[c] = np.nan
            df = df[SCREEN_LOG_COLUMNS].copy()
            df["out_status"] = df["out_status"].astype(object)      # 'done' 같은 문자열을 넣을 수 있게
            return df
    except Exception as _e:
        _log_err("_read_screen_log", _e)
    return pd.DataFrame(columns=SCREEN_LOG_COLUMNS)


def _write_screen_log(df: pd.DataFrame) -> None:
    tmp = SCREEN_LOG_PATH + ".tmp"
    df.to_csv(tmp, index=False, encoding="utf-8")
    os.replace(tmp, SCREEN_LOG_PATH)          # 임시 파일로 쓴 뒤 교체 → 쓰는 도중 깨지는 것 방지


def log_screen_results(rows: list, scan_mode: str) -> int:
    """등급이 계산된 후보(상위 종목)를 기록 파일에 추가하고 기록한 건수를 반환. 실패해도 앱은 계속 동작."""
    try:
        now = pd.Timestamp.now(tz="UTC")
        run_id = now.strftime("%Y%m%d%H%M%S")
        new = []
        for r in rows:
            if r.get("setup_score") is None:
                continue
            f = r.get("factors") or {}
            price = r.get("ctx_price") or r.get("price")
            if not price:
                continue
            rvol = r.get("ctx_rvol_t") if r.get("ctx_rvol_t") is not None else (r.get("vol_ma20_ratio") or 0) / 100
            new.append({
                "run_id": run_id, "logged_at_utc": now.isoformat(), "scan_mode": scan_mode,
                "ticker": _clean_ticker(r), "price": float(price), "grade": r.get("grade"),
                "score": r.get("setup_score"), "setup": r.get("setup"), "why": r.get("why"), "warn": r.get("warn"),
                "f_catalyst": f.get("catalyst"), "f_participation": f.get("participation"),
                "f_extension": f.get("extension"), "f_rr": f.get("rr"), "f_tradability": f.get("tradability"),
                "pct": r.get("ctx_live_pct") if r.get("ctx_live_pct") is not None else r.get("pct_change"),
                "rvol": rvol, "float_turnover": r.get("float_turnover"), "catalyst": r.get("catalyst"),
                "offering_days": r.get("offering_days"), "rr": r.get("ctx_rr"), "stop": r.get("ctx_stop"),
                "res1_name": r.get("ctx_res1_name"), "res1": r.get("ctx_res1"), "vwap": r.get("ctx_vwap"),
                "off_high_pct": r.get("ctx_off_high"), "atr": r.get("atr"), "out_status": "",
            })
        if not new:
            return 0
        with _SCREEN_LOG_LOCK:
            df = pd.concat([_read_screen_log(), pd.DataFrame(new)], ignore_index=True)
            _write_screen_log(df[SCREEN_LOG_COLUMNS])
        return len(new)
    except Exception as _e:
        _log_err("log_screen_results", _e)
        return 0


def _compute_outcome(row) -> dict:
    """기록된 한 건의 '기록 시점 이후 같은 날' 성과를 5분봉으로 계산.
    - MFE/MAE: 기록가 대비 이후 최고가/최저가 변동(%)
    - R 결과: 손절 = 기록가 − ATR 1배(1R), 목표 = +2R. 먼저 닿는 쪽이 결과, 같은 봉에서 둘 다면 손절 우선(보수적).
      둘 다 안 닿으면 정규장 종가 기준 R."""
    t, price = str(row["ticker"]), float(row["price"])
    logged = pd.to_datetime(row["logged_at_utc"], utc=True).tz_convert("America/New_York")
    raw = yf.Ticker(t).history(period="5d", interval="5m", prepost=True)
    if raw is None or raw.empty:
        return {}
    raw.index = pd.to_datetime(raw.index)
    if raw.index.tz is None:
        raw.index = raw.index.tz_localize("UTC")
    idx = raw.index.tz_convert("America/New_York")
    mins = idx.hour * 60 + idx.minute
    same_day = np.array(idx.date) == logged.date()
    bars = raw[(idx >= logged) & same_day & (mins < 960)]       # 기록 이후 ~ 정규장 마감(16:00)
    if bars.empty:
        bars = raw[(idx >= logged) & same_day]
    if bars.empty:
        return {}
    mfe = (float(bars["High"].max()) / price - 1) * 100
    mae = (float(bars["Low"].min()) / price - 1) * 100
    close_pct = (float(bars["Close"].iloc[-1]) / price - 1) * 100
    out = {"out_status": "done", "out_mfe_pct": round(mfe, 2), "out_mae_pct": round(mae, 2),
           "out_close_pct": round(close_pct, 2), "out_R": np.nan}
    stop = row.get("stop")
    if pd.notna(stop) and float(stop) < price:
        risk = price - float(stop)
        target = price + 2 * risk
        r_val = (float(bars["Close"].iloc[-1]) - price) / risk
        for _, b in bars.iterrows():
            if float(b["Low"]) <= float(stop):
                r_val = -1.0
                break
            if float(b["High"]) >= target:
                r_val = 2.0
                break
        out["out_R"] = round(r_val, 2)
    return out


def update_screen_outcomes(max_rows: int = 80) -> tuple:
    """장 마감(16:10 ET) 이후가 된 미완료 기록의 결과를 채운다. 반환: (갱신 건수, 대기 건수)."""
    with _SCREEN_LOG_LOCK:
        df = _read_screen_log()
    if df.empty:
        return 0, 0
    now_et = pd.Timestamp.now(tz="America/New_York")
    todo = df[(df["out_status"].isna()) | (df["out_status"] == "")]
    updated = waiting = 0
    for i, row in todo.head(max_rows).iterrows():
        try:
            logged = pd.to_datetime(row["logged_at_utc"], utc=True).tz_convert("America/New_York")
            if now_et < logged.normalize() + pd.Timedelta(hours=16, minutes=10):
                waiting += 1
                continue
            res = _compute_outcome(row)
            if res:
                for k, v in res.items():
                    df.at[i, k] = v
                updated += 1
            elif (now_et - logged).days >= 4:
                df.at[i, "out_status"] = "no_data"      # 5분봉 보관 기간이 지나 더는 채울 수 없음
        except Exception as _e:
            _log_err("update_screen_outcomes", _e)
    with _SCREEN_LOG_LOCK:
        cur = _read_screen_log()
        # 다른 세션이 그 사이 추가한 기록은 유지하고, 우리가 채운 건만 덮어쓴다
        key = ["run_id", "ticker"]
        upd = df.dropna(subset=["out_status"]).query("out_status != ''")
        cur = cur.drop_duplicates(key, keep="last").set_index(key)
        upd = upd.drop_duplicates(key).set_index(key)
        cur.update(upd[["out_status", "out_mfe_pct", "out_mae_pct", "out_close_pct", "out_R"]])
        _write_screen_log(cur.reset_index()[SCREEN_LOG_COLUMNS])
    return updated, waiting


def _summarize_log(df: pd.DataFrame, by: str) -> pd.DataFrame:
    d = df[df["out_status"] == "done"].copy()
    for c in ("out_R", "out_mfe_pct", "out_mae_pct", "out_close_pct"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    if d.empty:
        return pd.DataFrame()
    g = d.groupby(by)
    out = pd.DataFrame({
        "건수": g["ticker"].count(),
        "승률(R>0,%)": g["out_R"].apply(lambda x: (x.dropna() > 0).mean() * 100 if x.notna().any() else np.nan),
        "평균R": g["out_R"].mean(),
        "평균MFE(%)": g["out_mfe_pct"].mean(),
        "평균MAE(%)": g["out_mae_pct"].mean(),
        "평균종가(%)": g["out_close_pct"].mean(),
    }).round(2)
    return out


def render_screen_log_panel():
    """검색 결과 기록과 등급별 실제 성과 비교 패널."""
    with st.expander("📊 점수 검증 (후보 기록 · 결과 추적)", expanded=False):
        df = _read_screen_log()
        done = int((df["out_status"] == "done").sum()) if not df.empty else 0
        st.caption(f"기록 {len(df)}건 · 결과 확정 {done}건. 검색을 실행할 때마다 등급이 계산된 후보가 자동 기록되고, "
                   "장 마감(16:10 ET) 후 '결과 업데이트'를 누르면 그날 성과가 채워집니다.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔄 결과 업데이트", key="update_outcomes", use_container_width=True):
                with st.spinner("5분봉으로 기록 이후 성과 계산 중..."):
                    u, w = update_screen_outcomes()
                st.success(f"{u}건 갱신 · 장 마감 전이라 대기 {w}건")
                df = _read_screen_log()
        with c2:
            if not df.empty:
                st.download_button("📥 기록 CSV 다운로드", df.to_csv(index=False).encode("utf-8-sig"),
                                   file_name="screen_log.csv", mime="text/csv", use_container_width=True)
        up = st.file_uploader("이전 기록 CSV 병합 (서버 재시작으로 기록이 사라졌을 때)", type=["csv"], key="log_upload")
        if up is not None and st.button("업로드한 기록 병합", key="merge_log"):
            try:
                add = pd.read_csv(up)
                for c in SCREEN_LOG_COLUMNS:
                    if c not in add.columns:
                        add[c] = np.nan
                with _SCREEN_LOG_LOCK:
                    merged = pd.concat([_read_screen_log(), add[SCREEN_LOG_COLUMNS]], ignore_index=True)
                    merged = merged.drop_duplicates(subset=["run_id", "ticker"], keep="last")
                    _write_screen_log(merged)
                st.success("병합 완료")
                df = _read_screen_log()
            except Exception as _e:
                st.error(f"병합 실패: {_e}")
        if done == 0:
            st.info("아직 결과가 확정된 기록이 없습니다. 검색 후 장 마감 뒤에 '결과 업데이트'를 눌러 주세요.")
            return
        order = {"A": 0, "B": 1, "C": 2, "D": 3}
        by_grade = _summarize_log(df, "grade")
        if not by_grade.empty:
            by_grade = by_grade.sort_index(key=lambda ix: [order.get(i, 9) for i in ix])
            st.markdown("**등급별 성과**")
            st.dataframe(by_grade, use_container_width=True)
        by_setup = _summarize_log(df, "setup")
        if not by_setup.empty:
            st.markdown("**셋업 유형별 성과**")
            st.dataframe(by_setup, use_container_width=True)
        st.caption("R 기준: 기록 시점 가격 − ATR 1배 = 손절(1R), +2R = 목표. 먼저 닿는 쪽이 결과(같은 봉이면 손절 우선), "
                   "둘 다 안 닿으면 정규장 종가 기준. A등급이 B·C·D보다 실제로 낫게 나오는지 확인하세요. "
                   "표본이 등급당 30건 미만이면 우연일 수 있어 참고만 하세요.")


def render_surge_screener():
    """급등주 검색기 + 점수 검증 패널 (화면 진입점)."""
    _render_surge_screener_main()
    render_screen_log_panel()


def _render_surge_screener_main():
    """
    조건(상승률/주가/거래량/거래대금/기술지표/리스크)에 맞는 급등주를 검색합니다.
    1차: Yahoo Finance 공식 스크리너로 후보 종목 수집
    2차: ThreadPoolExecutor로 RSI·거래량비율·거래대금·국가·나스닥 컴플라이언스 병렬 병합
    3차: 유저가 선택한 신호/리스크 필터 및 정렬 기준 적용
    """
    ui_section_header(mono_icon_badge("rocket", color="var(--c-rose)"), "급등주 검색기", "icon-rose", "title-rose")
    st.caption("Yahoo Finance 실시간(지연 가능) 시세 + RSI·거래대금·리스크 지표를 결합한 정밀 검색기입니다.")

    # ── 검색 모드: 정규장 등락률 / 프리마켓 갭 ───────────────────
    scan_mode = st.radio(
        "검색 기준", ["정규장 등락률", "프리마켓 갭 (장 시작 전)"],
        horizontal=True, key="screener_scan_mode",
        help="프리마켓 갭: 전일 종가 대비 프리마켓(04:00~09:30 ET) 현재가 상승률과 프리마켓 거래량으로 찾습니다. "
             "미국 장 시작 전(한국 시간 저녁 5~10시대)에 쓰세요.")
    is_pm_mode = scan_mode.startswith("프리마켓")

    # ── 1차 검색 조건 ────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        min_pct = st.slider(
            "최소 갭 상승률 (%)" if is_pm_mode else "최소 상승률 (%)",
            min_value=3, max_value=100, value=10, step=1,
            key="screener_min_pct"
        )
    with c2:
        price_range = st.slider(
            "주가 범위 ($)", min_value=0.1, max_value=200.0, value=(0.1, 20.0), step=0.1,
            key="screener_price_range"
        )
    with c3:
        if is_pm_mode:
            min_volume = st.number_input(
                "최소 프리마켓 거래량", min_value=0, value=200_000, step=50_000,
                key="screener_min_pm_vol"
            )
        else:
            min_volume = st.number_input(
                "최소 거래량", min_value=0, value=500_000, step=100_000,
                key="screener_min_vol"
            )

    # ── 소형 저유통주 필터 (0 = 제한 없음) ────────────────────────
    f1, f2, f3 = st.columns(3)
    with f1:
        max_float_m = st.number_input(
            "유통주식수 상한 (만 주, 0=제한없음)", min_value=0, value=2000, step=500,
            key="screener_max_float",
            help="2000 = 2천만 주 이하. 유통주식수 정보가 없는 종목은 이 필터가 켜져 있으면 제외됩니다.")
    with f2:
        max_cap_m = st.number_input(
            "시가총액 상한 ($백만, 0=제한없음)", min_value=0, value=0, step=100,
            key="screener_max_cap",
            help="예: 500 = 시총 $5억 이하. 시총 정보가 없는 종목은 필터가 켜져 있으면 제외됩니다.")
    with f3:
        min_rvol = st.number_input(
            "최소 상대거래량 (20일 평균 대비 %, 0=제한없음)", min_value=0, value=0, step=100,
            key="screener_min_rvol",
            help="500 = 5배. 장 초반에는 값이 낮게 나오므로 처음엔 0으로 두고 보세요.")

    # ── 정렬 기준 & 기술 시그널 필터 ─────────────────────────────
    d1, d2 = st.columns(2)
    with d1:
        sort_option = st.radio(
            "정렬 기준", ["셋업점수 순", "사전점수 순", "등락률 순", "거래대금 순", "거래량 순", "플로트 회전율 순"],
            horizontal=True, key="screener_sort"
        )
    with d2:
        signal_filter = st.selectbox(
            "기술 시그널 필터",
            ["전체", "상대거래량 500%+ (5배)", "거래량 200%+ 돌파", "플로트 회전율 100%+"],
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
    only_beam = st.checkbox("🧨 빔 신호 종목만", value=False, key="screener_only_beam")
    only_grade_b = st.checkbox("🅰 셋업 B등급 이상만", value=False, key="screener_only_grade_b",
                               help="상위 30개 종목만 등급을 계산합니다. 등급이 없는 종목은 제외됩니다.")
    only_catalyst = st.checkbox(
        "📰 재료(최근 48시간 호재성 뉴스) 있는 종목만", value=False, key="screener_only_catalyst",
        help="FDA·계약·실적·애널리스트 뉴스가 48시간 안에 있는 종목만 남깁니다. 상위 30개 종목만 뉴스를 조회하므로 그 아래 종목은 제외됩니다.")

    if st.button("🔍 검색 실행", key="run_screener", use_container_width=True):
        with st.spinner("Yahoo Finance에서 급등주 검색 및 상세 지표 병렬 수집 중..."):
            if is_pm_mode:
                # 프리마켓 갭 검색 (시총 상한 필터가 있으면 1단계 후보 수집에도 적용)
                base = fetch_premarket_gappers(min_pct, price_range[0], price_range[1],
                                               int(min_volume), int(max_cap_m))
            else:
                base = fetch_top_gainers(min_pct, price_range[0], price_range[1], int(min_volume))
            tickers = tuple(r["ticker"] for r in base if r.get("ticker"))
            enriched_map = enrich_screener_results(tickers) if tickers else {}

            merged = []
            for r in base:
                extra = enriched_map.get(r["ticker"], {})
                if extra.get("error"):
                    continue
                combined = {**r, **extra}
                combined["score"] = calc_screener_score(combined)
                merged.append(combined)
            # 1차 사전 순위(구 종합점수): 상위 30개에만 아래의 무거운 조회(뉴스·장중 데이터)를 수행한다
            merged.sort(key=lambda r: r.get("score", 0), reverse=True)
            # 상장폐지 확정·청산·피인수 확정·OTC 종목 제외 (상위 60개 조회) — 이후 상위 30개 평가가 정상 종목으로 채워진다
            merged, _excl = filter_delisted(merged, limit=60)
            st.session_state["screener_excluded"] = _excl
            attach_beams(merged, "ticker", "beam", [True] * len(merged), limit=30)
            attach_catalysts(merged, limit=30)          # 재료 종류·신선도·오퍼링 공시
            attach_intraday_context(merged, limit=30)   # VWAP·당일 고가·저항·손익비·시간보정 RVOL
            apply_setup_to_rows(merged)                 # 셋업 등급/점수/근거/경고 계산
            # 정렬: 등급 평가가 된 종목을 셋업 점수 순으로 먼저, 평가 안 된 종목은 사전 순위대로 뒤에
            merged.sort(key=lambda r: (r.get("setup_score") is not None, r.get("setup_score") or 0, r.get("score", 0)),
                        reverse=True)
            log_screen_results(merged, scan_mode)       # 후보·점수 구성요소 기록 (결과 추적용)
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
    if only_beam:
        filtered = [r for r in filtered if r.get("beam")]
    if only_catalyst:
        filtered = [r for r in filtered if r.get("catalyst_ok")]
    if only_grade_b:
        filtered = [r for r in filtered if r.get("grade") in ("A", "B")]
    # 소형 저유통주 필터 — 정보가 없는(None) 종목은 필터가 켜져 있으면 제외
    if max_float_m > 0:
        filtered = [r for r in filtered
                    if r.get("float_shares") and r["float_shares"] <= max_float_m * 10_000]
    if max_cap_m > 0:
        filtered = [r for r in filtered
                    if (r.get("market_cap") or r.get("market_cap_info"))
                    and (r.get("market_cap") or r.get("market_cap_info")) <= max_cap_m * 1_000_000]
    if min_rvol > 0:
        filtered = [r for r in filtered if r.get("vol_ma20_ratio", 0) >= min_rvol]
    if signal_filter == "상대거래량 500%+ (5배)":
        filtered = [r for r in filtered if r.get("vol_ma20_ratio", 0) >= 500]
    elif signal_filter == "거래량 200%+ 돌파":
        filtered = [r for r in filtered if r.get("vol_ma20_ratio", 0) >= 200]
    elif signal_filter == "플로트 회전율 100%+":
        filtered = [r for r in filtered if (r.get("float_turnover") or 0) >= 100]

    # ── 정렬 ─────────────────────────────────────────────────────
    sort_key_map = {
        "셋업점수 순": lambda r: (r.get("setup_score") is not None, r.get("setup_score") or 0),
        "사전점수 순": lambda r: r.get("score", 0) or 0,
        "등락률 순":   lambda r: r.get("pct_change", 0) or 0,
        "거래대금 순": lambda r: r.get("trading_value_eok", 0) or 0,
        "거래량 순":   lambda r: r.get("volume", 0) or 0,
        "플로트 회전율 순": lambda r: r.get("float_turnover") or 0,
    }
    filtered.sort(key=sort_key_map[sort_option], reverse=True)

    if not filtered:
        st.warning("조건에 맞는 종목이 없습니다. 필터를 완화해 보세요.")
        return

    st.markdown(f"**{len(filtered)}개 종목** (1차 후보 {len(results)}개 중 필터링 결과)")
    render_excluded_expander("screener_excluded")

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
            "등급":          r.get("grade", "—"),
            "셋업점수":      r.get("setup_score"),
            "셋업":          r.get("setup", ""),
            "근거":          r.get("why", ""),
            "경고":          r.get("warn", ""),
            "현재가":        r.get("price", 0),
            "등락률(%)":     r.get("pct_change", 0),     # 프리마켓 모드에서는 프리마켓 갭(%)
            "프리고가":      r.get("pm_high"),
            "사전점수":      r.get("score", 0),
            "거래량":        r.get("volume", 0),
            "거래대금(억)":  r.get("trading_value_eok", 0),
            "RSI":           r.get("rsi"),
            "유통주식(만)":   round(r["float_shares"] / 10_000) if r.get("float_shares") else None,
            "플로트회전(%)":  r.get("float_turnover"),
            "시총($M)":      round((r.get("market_cap") or r.get("market_cap_info") or 0) / 1_000_000) or None,
            "공매도(%)":     r.get("short_pct"),
            "거래량비율(%)":  r.get("vol_ratio", 0),
            "20일MA비율(%)": r.get("vol_ma20_ratio", 0),
            "상장리스크":     _risk_text(r),
            "빔신호":         r.get("beam", "") or "—",
            "재료":           r.get("catalyst") or "—",
            "오퍼링(일전)":   r.get("offering_days"),
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
            "프리고가":      st.column_config.NumberColumn(format="$%.2f"),
            "등락률(%)":     st.column_config.NumberColumn(format="%+.2f%%"),
            "셋업점수":      st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100,
                                                         help="재료×수급×진입위치×손익비×거래가능성 (게이트 적용 후). A≥75, B≥60, C≥45"),
            "사전점수":      st.column_config.NumberColumn(format="%.1f", help="1차 사전 순위용(구 종합점수). 매매 판단에는 셋업점수·등급을 보세요."),
            "거래량":        st.column_config.NumberColumn(format="%d"),
            "거래대금(억)":  st.column_config.NumberColumn(format="%.1f억"),
            "RSI":           st.column_config.NumberColumn(format="%.1f"),
            "유통주식(만)":   st.column_config.NumberColumn(format="%d"),
            "플로트회전(%)":  st.column_config.NumberColumn(format="%.0f%%"),
            "시총($M)":      st.column_config.NumberColumn(format="%d"),
            "공매도(%)":     st.column_config.NumberColumn(format="%.1f%%"),
            "오퍼링(일전)":   st.column_config.NumberColumn(format="%d일", help="가장 최근 오퍼링 관련 SEC 공시가 며칠 전인지 (7일 이내 -10점, 30일 이내 -5점)"),
            "거래량비율(%)":  st.column_config.NumberColumn(format="%.0f%%"),
            "20일MA비율(%)": st.column_config.NumberColumn(format="%.0f%%"),
        },
        key="screener_df",
    )

    if is_pm_mode:
        st.caption("프리마켓 모드: 등락률 = 전일 종가 대비 프리마켓 갭, 거래량 = 프리마켓 누적 거래량입니다. "
                   "거래대금·RSI·20일MA비율은 전일 일봉 기준이라 참고용입니다.")
    st.caption("⚠️ = 중국/홍콩 소재 기업 · ⭐ = 즐겨찾기 등록 종목 · 상장리스크는 나스닥 최소호가($1) 규정 기준 추정치입니다. "
               "행을 클릭하면 해당 종목의 정밀 분석 화면으로 이동합니다. 등급·셋업점수는 상위 30개 종목만 계산하며, "
               "가중치는 경험칙이라 아래 '점수 검증' 기록으로 실제 성과를 확인하며 보정하세요. 매매 신호가 아닌 참고 지표입니다.")

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
    csv_bytes = df_display.to_csv(index=False).encode("utf-8-sig")
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
# 🚫 상장폐지 확정 · 피인수(합병 확정) 종목 제외
#   상장폐지가 확정됐거나 인수가 확정돼 가격이 고정된 종목은 변동성이 줄고 거래량이 몰려서
#   '급등 전 매집' 패턴처럼 보이므로 순위에서 걸러낸다. (사이드바 체크박스로 켜고 끔)
#   판정 근거: ① 거래소가 OTC/핑크시트 ② 최근 6개월 SEC Form 25·15(상장폐지·등록말소)
#             ③ 최근 뉴스 제목의 확정 표현(delisting determination, will be delisted, 거래정지, 청산 등)
#   '결손 통지(deficiency notice)'·'규정 준수 기간 부여'처럼 아직 확정이 아닌 소식은 제외하지 않고 경고만 한다.
#   ⚠️ 키워드 기반이라 오탐이 있을 수 있어, 제외된 종목은 화면의 '🚫 제외된 종목'에서 사유·원문을 확인할 수 있다.
# ════════════════════════════════════════════════════════════════
DELIST_NEWS_DAYS = 120
DELIST_SEC_DAYS = 180
_DL_STRIP = _EV_STRIP     # 'Foo Acquisition Corp' 같은 SPAC 상호는 먼저 지운다
_DL_CONFIRM = [re.compile(p, re.I) for p in (
    r"\bwill be delisted\b", r"\bto be delisted\b", r"\bdelisting (?:determination|decision)\b",
    r"\b(?:determination|determined|decision|decided) to delist\b", r"\bstaff (?:delisting )?determination\b",
    r"\bsuspen(?:d|ds|ded|sion)\b[^.]{0,40}\btrading\b", r"\btrading suspension\b", r"\bform 25\b",
    r"\bvoluntar(?:y|ily)\b[^.]{0,30}\bdelist", r"\bdelist\w*\b[^.]{0,40}\b(?:effective|completed|completes|finalized)\b",
    r"\bremoved? from (?:the )?(?:nasdaq|nyse|nyse american|nyse arca)\b",
    r"\b(?:move|moves|moved|transfer|transfers|transferred)\b[^.]{0,30}\b(?:to|onto) (?:the )?otc",
    r"\bdelisted from\b", r"\bdelisting of (?:its |the )?(?:common|ordinary|shares|stock)\b")]
_DL_LIQ = [re.compile(p, re.I) for p in (
    r"\bchapter\s*7\b", r"\bplan of (?:complete )?(?:liquidation|dissolution)\b", r"\bvoluntary liquidation\b",
    r"\bliquidat(?:e|ing) the company\b", r"\bcease[sd]? (?:all )?operations\b",
    r"\bwind(?:ing)?[\s-]*down (?:the )?(?:company|operations|business)\b")]
_DL_ACQ = [re.compile(p, re.I) for p in (
    r"\b(?:to|will|agrees? to|agreed to) be (?:acquired|taken private|bought|purchased)\b",
    r"\bgo(?:es|ing)?[\s-]private\b", r"\btake[\s-]private\b",
    r"\b(?:\$\s?)?\d+(?:\.\d+)? per share in cash\b", r"\ball[\s-]cash (?:deal|transaction|offer)\b")]
_DL_KIND_LABEL = {"delisting": "상장폐지 확정", "liquidation": "파산·청산 진행", "acquired": "피인수(합병 확정)",
                  "otc": "OTC/핑크시트(상장폐지 후 거래 추정)"}


def classify_delisting_text(text):
    """뉴스 제목 한 줄 → 'delisting'(상장폐지 확정) / 'liquidation'(청산) / 'acquired'(피인수 확정) / None"""
    t = _DL_STRIP.sub(" ", str(text or ""))
    if any(p.search(t) for p in _DL_CONFIRM):
        return "delisting"
    if any(p.search(t) for p in _DL_LIQ):
        return "liquidation"
    if any(p.search(t) for p in _DL_ACQ):
        return "acquired"
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def detect_delisting(ticker: str) -> dict:
    """한 종목의 상장폐지·청산·피인수 확정 여부를 판정. 반환: {"kind", "label", "title", "date", "link", "source"} / 해당 없으면 {}
    우선순위: 상장폐지 > 청산 > 피인수 (더 심각한 쪽을 반환)."""
    now = pd.Timestamp.now(tz="UTC")
    found = []      # (심각도 순위, 결과 dict)
    rank = {"delisting": 0, "liquidation": 1, "acquired": 2}
    try:       # ① SEC 서식: Form 25(상장폐지)·Form 15(등록 말소)
        for f in fetch_sec_filings(ticker) or []:
            t = re.sub(r"[\s\-_/]", "", str(f.get("type") or "").upper())
            if not (t in {"25", "25NSE", "25NSEA"} or t.startswith(("1512", "1515", "15F"))):
                continue
            dt = pd.to_datetime(f.get("date"), utc=True, errors="coerce")
            if pd.isna(dt) or (now - dt) > pd.Timedelta(days=DELIST_SEC_DAYS):
                continue
            found.append((0, {"kind": "delisting", "title": f"SEC {f.get('type')} — {f.get('title') or ''}".strip(" —"),
                              "date": dt.strftime("%Y-%m-%d"), "link": f.get("url", ""), "source": "SEC 공시"}))
    except Exception as _e:
        _log_err("detect_delisting_sec:" + ticker, _e)
    try:       # ② 뉴스 제목
        for raw in fetch_yahoo_news(ticker) or []:
            p = parse_yahoo_news_item(raw)
            dt = _news_dt(raw)
            if dt is not None and (now - dt) > pd.Timedelta(days=DELIST_NEWS_DAYS):
                continue
            kind = classify_delisting_text(p.get("title", ""))
            if kind:
                found.append((rank[kind], {"kind": kind, "title": p.get("title", ""),
                                           "date": dt.strftime("%Y-%m-%d") if dt is not None else "",
                                           "link": p.get("link", ""), "source": "뉴스"}))
    except Exception as _e:
        _log_err("detect_delisting_news:" + ticker, _e)
    if not found:
        return {}
    found.sort(key=lambda x: (x[0], x[1].get("date") or ""), reverse=False)
    best = found[0][1]
    best["label"] = _DL_KIND_LABEL[best["kind"]]
    return best


def _delist_excluded(kind: str) -> bool:
    """사이드바 설정에 따라 이 종류를 제외할지 여부. 상장폐지·OTC·청산은 '상장폐지 제외', 피인수는 '피인수 제외' 설정을 따른다."""
    if kind in ("delisting", "liquidation", "otc"):
        return bool(st.session_state.get("excl_delisted", True))
    if kind == "acquired":
        return bool(st.session_state.get("excl_acquired", True))
    return False


def filter_delisted(rows: list, limit: int = 60, max_workers: int = 6) -> tuple:
    """순위 후보에서 상장폐지 확정(·청산·피인수 확정) 종목을 제거. 반환: (남은 행, 제외된 행 목록)
    상위 limit개만 뉴스·공시를 조회한다(속도). OTC/핑크시트 상장 종목은 조회 없이 바로 제외."""
    if not (st.session_state.get("excl_delisted", True) or st.session_state.get("excl_acquired", True)):
        return rows, []
    excluded, status = [], {}
    otc_re = re.compile(r"otc|pink|pnk|grey|gray", re.I)

    def _clean(r):
        return str(r.get("ticker", "")).replace("⚠️ ", "").strip()

    to_check = []
    for r in rows[:limit]:
        if otc_re.search(str(r.get("exchange") or "")):
            status[_clean(r)] = {"kind": "otc", "label": _DL_KIND_LABEL["otc"], "title": str(r.get("exchange")),
                                 "date": "", "link": "", "source": "거래소"}
        else:
            to_check.append(_clean(r))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for t, res in zip(to_check, ex.map(detect_delisting, to_check)):
            if res:
                status[t] = res
    kept = []
    for r in rows:
        st_ = status.get(_clean(r))
        if st_ and _delist_excluded(st_["kind"]):
            excluded.append({"티커": _clean(r), "종목명": (r.get("name") or "")[:24], "사유": st_["label"],
                             "출처": st_["source"], "일자": st_["date"], "근거": st_["title"][:120], "링크": st_.get("link", "")})
        else:
            kept.append(r)
    return kept, excluded


def render_excluded_expander(state_key: str):
    """제외된 종목을 사유·원문 링크와 함께 보여주는 접이식 표 (오탐 확인용)."""
    ex = st.session_state.get(state_key) or []
    if not ex:
        return
    with st.expander(f"🚫 제외된 종목 {len(ex)}개 (상장폐지 확정·피인수·청산 등)", expanded=False):
        st.dataframe(pd.DataFrame(ex), use_container_width=True, hide_index=True,
                     column_config={"링크": st.column_config.LinkColumn("링크", display_text="원문")})
        st.caption("키워드 기반 판정이라 오탐이 있을 수 있습니다. 잘못 제외된 종목이 있으면 사이드바 설정을 끄거나 원문을 확인하세요.")


def render_delist_banner(ticker: str):
    """종목 상세 화면 상단 경고 배너 (설정과 무관하게 항상 표시)."""
    res = detect_delisting(ticker)
    if res:
        link = _safe_url(res.get("link", ""))
        link_html = f' · <a href="{link}" target="_blank" rel="noopener">원문 →</a>' if link else ""
        st.markdown(
            f'<div class="split-banner"><div class="split-banner-title">🚫 {_safe_html(res["label"])} 감지 '
            f'({_safe_html(res["source"])} · {_safe_html(res["date"])})</div>'
            f'<div>{_safe_html(res["title"])}{link_html}</div>'
            f'<div style="font-size:0.8rem;opacity:0.7;margin-top:0.3rem;">키워드 기반 자동 판정이라 원문 확인이 필요합니다. '
            f'이 종목의 점수는 신뢰하지 마세요.</div></div>', unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# 급등 전 매집 · 돌파 임박 예측 점수 (calc_prebreakout_score)
#
# 기존 종합점수는 등락률·거래량처럼 '이미 터진 뒤'의 값을 더해서, 급등한 종목일수록 점수가 높았습니다.
# 이 점수는 반대로 "아직 안 올랐는데 터질 준비가 된 자리"를 찾습니다 (일봉 기준).
#
#   ① 변동성 축소 (30%) : 볼린저밴드 폭이 최근 6개월 중 얼마나 좁은지 + 최근 5일 일중 변동폭이 이전 20일보다 줄었는지
#   ② 거래량 선행·매집 (30%) : 가격은 조용한데 거래량이 먼저 늘었는가 (5일/이전 평균 배율, 상승일/하락일 거래량 비,
#                              OBV 20일 변화)
#   ③ 20일선 직전 (25%) : 20일선 바로 아래~위 2% 이내인지, 20일선이 꺾이지 않았는지, 20일 고점까지 거리가 가까운지
#   ④ 미과열 (15%)      : 최근 5일·당일 상승률이 작고 RSI가 과열(75↑)이 아닌지
#   → 가중 기하평균(곱셈형): 한 요소라도 약하면 전체가 낮아집니다.
#   게이트: 이미 급등(당일 +10% 또는 5일 +25% 이상)이면 상한 30점, 20일 평균 거래대금 $30만 미만이면 상한 40점
#   단계: 75↑ 임박 / 60↑ 준비 / 45↑ 관찰 / 미만 해당없음
# ⚠️ 구간·가중치는 경험칙입니다. '급등 전 스캐너' 하단의 기록으로 단계별 5일 내 +10% 적중률을 확인하며 보정하세요.
# ════════════════════════════════════════════════════════════════
PREBREAK_WEIGHTS = {"contraction": 0.30, "accumulation": 0.30, "ma20": 0.25, "notext": 0.15}
PREBREAK_CUTS = (("임박", 75), ("준비", 60), ("관찰", 45))


def calc_prebreakout_score(hist: pd.DataFrame) -> dict:
    """일봉(calc_indicators 적용 완료)으로 '급등 전 매집·돌파 임박' 점수를 계산.
    반환: {score, stage, why, warn, factors{...}, metrics{...}}  — 데이터가 부족하면 {}"""
    try:
        d = hist.dropna(subset=["Close", "High", "Low", "Volume"])
        if len(d) < 45:
            return {}
        c, h, l, v = d["Close"].astype(float), d["High"].astype(float), d["Low"].astype(float), d["Volume"].astype(float)
        price = float(c.iloc[-1])
        if price <= 0:
            return {}
        why, warn, caps = [], [], []

        # ── ① 변동성 축소 ─────────────────────────────────
        bbw = d["BB_WIDTH"].dropna().tail(126)                   # 최근 약 6개월 볼린저밴드 폭
        bb_rank = float((bbw <= bbw.iloc[-1]).mean()) if len(bbw) >= 30 else 0.5   # 0에 가까울수록 가장 좁음
        day_rng = (h - l) / c * 100                              # 일중 변동폭(%)
        rng5 = float(day_rng.tail(5).mean())
        rng_base = float(day_rng.iloc[-25:-5].mean())
        contraction = (rng5 / rng_base) if rng_base > 0 else 1.0   # 1 미만이면 최근 변동폭이 줄어든 것
        f_con = 0.6 * _clamp01(1 - bb_rank / 0.5) + 0.4 * _clamp01((1.0 - contraction) / 0.5)
        f_con = max(f_con, 0.05)
        why.append(f"BB폭 하위 {bb_rank * 100:.0f}%")
        if contraction < 0.85:
            why.append(f"변동폭 {contraction:.2f}배로 축소")

        # ── ② 거래량 선행 · 매집 ──────────────────────────
        v_base = float(v.iloc[-65:-5].mean())
        vr5 = (float(v.tail(5).mean()) / v_base) if v_base > 0 else 0.0
        a1 = _clamp01((vr5 - 0.8) / 1.0)                          # 0.8배→0, 1.8배→1
        last15 = d.tail(15)
        up_mask = last15["Close"].astype(float).diff() > 0
        dn_mask = last15["Close"].astype(float).diff() < 0
        up_vol = float(last15.loc[up_mask, "Volume"].sum())
        dn_vol = float(last15.loc[dn_mask, "Volume"].sum())
        ud = (up_vol / dn_vol) if dn_vol > 0 else (3.0 if up_vol > 0 else 1.0)
        a2 = _clamp01((ud - 0.9) / 1.1)                            # 0.9→0, 2.0→1
        obv = (np.sign(c.diff().fillna(0)) * v).cumsum()
        vol20 = float(v.tail(20).sum())
        obv_chg = float(obv.iloc[-1] - obv.iloc[-21]) / vol20 if vol20 > 0 and len(obv) > 21 else 0.0
        a3 = _clamp01(obv_chg / 0.3)
        f_acc = max(0.4 * a1 + 0.35 * a2 + 0.25 * a3, 0.05)
        why.append(f"5일 거래량 {vr5:.1f}배")
        if ud >= 1.3:
            why.append(f"상승일/하락일 거래량 {ud:.1f}배")
        if obv_chg > 0.1:
            why.append("OBV 상승")

        # ── ③ 20일선 직전 ─────────────────────────────────
        ma20 = float(d["MA20"].iloc[-1])
        dist = (price / ma20 - 1) * 100 if ma20 > 0 else 0.0       # +면 20일선 위
        if -4 <= dist <= 2:
            p1 = 1.0
        elif 2 < dist <= 6:
            p1 = 1 - (dist - 2) / 4 * 0.7
        elif dist > 6:
            p1 = 0.15
        else:
            p1 = max(0.1, 1 - (-4 - dist) / 8)
        ma20_prev = float(d["MA20"].iloc[-6])
        slope = (ma20 / ma20_prev - 1) * 100 if ma20_prev > 0 else 0.0
        p2 = 1.0 if slope >= -0.5 else 0.6
        hi20 = float(h.tail(20).max())
        to_hi = (hi20 / price - 1) * 100
        p3 = 1.0 if to_hi <= 5 else (1.0 - (to_hi - 5) / 7 * 0.5 if to_hi <= 12 else 0.3)
        f_ma = max(0.55 * p1 + 0.20 * p2 + 0.25 * p3, 0.05)
        why.append(f"20일선 대비 {dist:+.1f}%")
        why.append(f"20일 고점까지 {to_hi:.1f}%")
        if slope < -0.5:
            warn.append("20일선 하락 중")

        # ── ④ 미과열(아직 안 오른 상태) ────────────────────
        today_pct = (price / float(c.iloc[-2]) - 1) * 100
        r5 = (price / float(c.iloc[-6]) - 1) * 100
        if today_pct > 10 or r5 > 25:
            n_ext = 0.1
            caps.append((30, "이미 급등"))
            warn.append(f"이미 급등(당일 {today_pct:+.0f}% · 5일 {r5:+.0f}%)")
        elif r5 > 12 or today_pct > 6:
            n_ext = 0.4
            warn.append(f"단기 상승 진행(5일 {r5:+.0f}%)")
        elif r5 > 8:
            n_ext = 0.7
        elif r5 >= -8:
            n_ext = 1.0
        else:
            n_ext = 0.6
            warn.append(f"5일 {r5:+.0f}% 하락")
        rsi = float(d["RSI"].iloc[-1]) if pd.notna(d["RSI"].iloc[-1]) else 50.0
        rsi_f = 1.0 if 40 <= rsi <= 65 else (0.8 if rsi <= 75 and rsi > 65 else (0.5 if rsi > 75 else 0.7))
        if rsi > 75:
            warn.append(f"RSI {rsi:.0f} 과열")
        f_not = max(0.7 * n_ext + 0.3 * rsi_f, 0.05)

        # ── 게이트: 유동성 ────────────────────────────────
        adv = float((c * v).tail(20).mean())                       # 20일 평균 거래대금($)
        if adv < 300_000:
            caps.append((40, "거래대금 부족"))
            warn.append(f"20일 평균 거래대금 ${adv / 1000:,.0f}K")

        w = PREBREAK_WEIGHTS
        raw = (f_con ** w["contraction"]) * (f_acc ** w["accumulation"]) * (f_ma ** w["ma20"]) * (f_not ** w["notext"])
        score = raw * 100
        cap_val = min([x[0] for x in caps], default=100)
        score = min(score, cap_val)
        stage = "해당없음"
        for name, cut in PREBREAK_CUTS:
            if score >= cut:
                stage = name
                break
        return {
            "score": round(score, 1), "raw_score": round(raw * 100, 1), "stage": stage,
            "why": " · ".join(why), "warn": " · ".join(warn),
            "cap": cap_val if caps else None, "cap_reason": min(caps, key=lambda x: x[0])[1] if caps else "",
            "factors": {"contraction": round(f_con, 2), "accumulation": round(f_acc, 2),
                        "ma20": round(f_ma, 2), "notext": round(f_not, 2)},
            "metrics": {"price": price, "today_pct": today_pct, "r5": r5, "bb_rank": bb_rank * 100,
                        "contraction": contraction, "vr5": vr5, "ud": ud, "obv_chg": obv_chg,
                        "ma20_dist": dist, "to_hi20": to_hi, "rsi": rsi, "adv": adv},
        }
    except Exception as _e:
        _log_err("calc_prebreakout_score", _e)
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def prebreakout_enrich(tickers: tuple) -> dict:
    """후보 종목들의 일봉을 병렬로 받아 돌파 임박 점수를 계산. 반환: {티커: 결과 dict}"""
    def _one(t):
        try:
            hist = fetch_history(t)
            if hist is None or hist.empty or len(hist) < 45:
                return t, {}
            res = calc_prebreakout_score(calc_indicators(hist.dropna()))
            return t, res
        except Exception as _e:
            _log_err("prebreakout_enrich:" + t, _e)
            return t, {}
    out = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for t, res in ex.map(_one, tickers):
            out[t] = res
    return out


# ════════════════════════════════════════════════════════════════
# 급등 전 매집 스캐너 v0.3 — 프리마켓 '갭 이어가기(Gap & Go)' 후보 선별 (당일~익일 단타용)
#
# 설계 근거(실전 자료 종합, 검증된 백테스트 아님):
#   · 대부분의 갭은 꺾인다. 이어가는 갭은 '종목 고유 촉매 + 평소보다 높은 프리마켓 거래량 + 작은 플로트' 프로필을 가진다.
#   · 갭 5~15%가 이어갈 가능성이 높은 구간, 개장 후 프리마켓 고점 돌파 + VWAP 유지가 진입 확인.
#   · 호재와 증자(오퍼링)·역분할이 같이 나오면 오히려 하락 → 제외. 인수 확정(가격 고정)·상장폐지도 제외.
#
#   [제외 필터]  평균거래량 부족 · 플로트 초과 · 증자 뉴스/공시 직후 · 역분할 뉴스 · 상장폐지/피인수/OTC
#   [점수 100]  촉매 품질 30 + 프리마켓 거래량 25 + 갭 크기 15 + 플로트·회전율 15 + 일봉 위치 15 (가중합)
#   [등급]      A 75↑ / B 60↑ / C 45↑ / 미만 —
#   [등급 상한] 1달러 미만 · 증자 공시 14일 이내 · 갭 30% 초과 · 프리마켓 고점 대비 -10%↓ → 최대 B / 촉매 미확인 → 최대 C
#   [시장 보정] 소형주(IWM)가 20일선 아래 + 5일 하락이면 '약세' → 등급 한 단계 하향
# ⚠️ 가중치·구간은 초안입니다. 하단 '예측 검증' 기록(시가→고가 +5%/+10% 적중률)으로 등급별 성과를 보며 보정하세요.
# ════════════════════════════════════════════════════════════════
GAPGO_WEIGHTS = {"catalyst": 30, "pm_volume": 25, "gap": 15, "float": 15, "daily": 15}
GAPGO_GRADES = (("A", 75), ("B", 60), ("C", 45))
GAPGO_GRADE_ORDER = ["A", "B", "C", "—"]
GAPGO_MIN_AVG_VOL = 400_000          # 평균거래량 하한(주)
GAPGO_MAX_FLOAT = 20_000_000         # 플로트 상한(주)
GAPGO_OFFER_EXCLUDE_DAYS = 3         # 증자 관련 공시가 이 일수 이내면 제외
GAPGO_OFFER_CAP_DAYS = 14            # 이 일수 이내면 등급 상한 B
GAPGO_REVERSE_SPLIT_DAYS = 30


def _gg_clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def gapgo_gap_factor(gap_pct: float) -> float:
    """갭 크기 점수(0~1): 5~15%가 만점, 그 아래는 비례, 15~30%는 1.0→0.5로 감소, 30% 초과는 0.3 (과열·소진 위험)."""
    g = float(gap_pct)
    if g <= 0:
        return 0.0
    if g < 5:
        return g / 5.0
    if g <= 15:
        return 1.0
    if g <= 30:
        return 1.0 - (g - 15) / 15.0 * 0.5
    return 0.3


def gapgo_pmvol_factor(pm_volume: float, avg_volume) -> float:
    """프리마켓 거래량 ÷ 평균 일거래량이 5%면 0점, 50% 이상이면 만점. 평균거래량을 모르면 0.3."""
    if not avg_volume or float(avg_volume) <= 0:
        return 0.3
    ratio = float(pm_volume) / float(avg_volume)
    return _gg_clamp((ratio - 0.05) / (0.50 - 0.05))


def gapgo_float_factor(float_shares, pm_volume: float) -> float:
    """플로트 점수(0~1) = 0.7×크기 + 0.3×프리마켓 회전율. 1천만 주 이하 만점, 2천만 주에서 0.6. 플로트를 모르면 중립 0.5."""
    if not float_shares or float(float_shares) <= 0:
        return 0.5
    f = float(float_shares)
    base = 1.0 if f <= 10_000_000 else _gg_clamp(1.0 - (f - 10_000_000) / 10_000_000 * 0.4)
    rot = _gg_clamp((float(pm_volume) / f) / 0.25)        # 프리마켓에서 플로트의 25%가 돌면 만점
    return 0.7 * base + 0.3 * rot


def gapgo_daily_factor(daily_score, pm_price: float, hi20, day2: bool = False) -> float:
    """일봉 위치 점수(0~1) = 0.6×(돌파임박 점수/75) + 0.4×(프리마켓 가격이 20일 고점을 뚫었거나 가까운 정도).
    전일 급등(2일차 갭)은 '이미 급등' 감점을 적용하지 않고 중립 0.5로 둔다. 정보가 없으면 중립."""
    if day2 or daily_score is None:
        part1 = 0.5
    else:
        part1 = _gg_clamp(float(daily_score) / 75.0)
    if hi20 and pm_price and float(pm_price) > 0:
        if float(pm_price) >= float(hi20) * 0.99:
            part2 = 1.0
        else:
            part2 = _gg_clamp(1.0 - ((float(hi20) / float(pm_price) - 1) * 100) / 10.0)
    else:
        part2 = 0.5
    return 0.6 * part1 + 0.4 * part2


def gapgo_grade(score: float) -> str:
    for name, cut in GAPGO_GRADES:
        if score >= cut:
            return name
    return "—"


def _gg_demote(grade: str) -> str:
    i = GAPGO_GRADE_ORDER.index(grade) if grade in GAPGO_GRADE_ORDER else len(GAPGO_GRADE_ORDER) - 1
    return GAPGO_GRADE_ORDER[min(i + 1, len(GAPGO_GRADE_ORDER) - 1)]


def _gg_cap_grade(grade: str, cap: str) -> str:
    """등급이 cap보다 좋으면 cap으로 낮춘다 (A가 가장 좋음)."""
    gi = GAPGO_GRADE_ORDER.index(grade) if grade in GAPGO_GRADE_ORDER else 3
    ci = GAPGO_GRADE_ORDER.index(cap)
    return GAPGO_GRADE_ORDER[max(gi, ci)]


def gapgo_cheap_exclusion(avg_volume, float_shares, min_avg_vol: int = GAPGO_MIN_AVG_VOL,
                          max_float: int = GAPGO_MAX_FLOAT) -> str:
    """네트워크 없이 판단되는 제외 사유. 통과하면 빈 문자열. 값을 모르면(None) 제외하지 않는다."""
    if avg_volume is not None and float(avg_volume) < min_avg_vol:
        return f"평균거래량 부족({float(avg_volume) / 1000:,.0f}K주)"
    if float_shares is not None and float(float_shares) > max_float:
        return f"플로트 초과({float(float_shares) / 1e6:,.1f}M주)"
    return ""


def calc_gapgo_score(r: dict) -> dict:
    """갭 이어가기 점수. 입력 r 키(없으면 None 취급):
      pm_gap, pm_volume, pm_price, pm_high, avg_volume, float_shares, catalyst_score, offering_days,
      offering_news(bool), reverse_split(bool), daily_score, daily_cap_reason, hi20, regime
    반환: {excluded(사유 또는 ''), score, grade, parts{항목: 0~1}, why, warn}"""
    gap = float(r.get("pm_gap") or 0)
    pm_vol = float(r.get("pm_volume") or 0)
    pm_px = float(r.get("pm_price") or 0)
    avg_vol, fl = r.get("avg_volume"), r.get("float_shares")
    off_days = r.get("offering_days")
    why, warn = [], []

    # ── 제외 필터 ─────────────────────────────────────
    ex = gapgo_cheap_exclusion(avg_vol, fl, r.get("min_avg_vol", GAPGO_MIN_AVG_VOL), r.get("max_float", GAPGO_MAX_FLOAT))
    if not ex and r.get("offering_news"):
        ex = "증자·오퍼링 뉴스(72시간 이내)"
    if not ex and off_days is not None and off_days <= GAPGO_OFFER_EXCLUDE_DAYS:
        ex = f"증자 관련 공시 {off_days}일 전"
    if not ex and r.get("reverse_split"):
        ex = f"역분할 뉴스({GAPGO_REVERSE_SPLIT_DAYS}일 이내)"
    if ex:
        return {"excluded": ex, "score": 0.0, "grade": "—", "parts": {}, "why": "", "warn": ""}

    # ── 점수 ──────────────────────────────────────────
    cat_s = float(r.get("catalyst_score") or 0.0)
    day2 = (r.get("daily_cap_reason") == "이미 급등")
    parts = {
        "catalyst": _gg_clamp(cat_s),
        "pm_volume": gapgo_pmvol_factor(pm_vol, avg_vol),
        "gap": gapgo_gap_factor(gap),
        "float": gapgo_float_factor(fl, pm_vol),
        "daily": gapgo_daily_factor(r.get("daily_score"), pm_px, r.get("hi20"), day2),
    }
    score = sum(GAPGO_WEIGHTS[k] * parts[k] for k in GAPGO_WEIGHTS)
    grade = gapgo_grade(score)

    # ── 근거·경고, 등급 상한 ───────────────────────────
    why.append(f"갭 {gap:+.1f}%")
    if avg_vol:
        why.append(f"프리마켓 거래량 평균의 {pm_vol / float(avg_vol) * 100:.0f}%")
    if cat_s > 0:
        why.append("촉매 있음")
    else:
        warn.append("촉매 미확인(뉴스 지연 가능)")
        grade = _gg_cap_grade(grade, "C")
    if fl is None or not fl:
        warn.append("플로트 확인 필요")
    if day2:
        warn.append("전일 급등(2일차 갭)")
    if pm_px and pm_px < NASDAQ_MIN_BID:
        warn.append("1달러 미만: 나스닥 최저가 요건·역분할 위험")
        grade = _gg_cap_grade(grade, "B")
    if off_days is not None and off_days <= GAPGO_OFFER_CAP_DAYS:
        warn.append(f"증자 관련 공시 {off_days}일 전(희석 위험)")
        grade = _gg_cap_grade(grade, "B")
    pm_high = r.get("pm_high")
    if pm_high and pm_px and float(pm_high) > 0 and pm_px < float(pm_high) * 0.90:
        warn.append(f"프리마켓 고점 대비 {(pm_px / float(pm_high) - 1) * 100:.0f}% (꺾이는 중)")
        grade = _gg_cap_grade(grade, "B")
    if gap > 30:
        warn.append("갭 30% 초과(소진 위험)")
        grade = _gg_cap_grade(grade, "B")
    if r.get("regime") == "약세":
        warn.append("소형주 약세장: 등급 한 단계 하향")
        grade = _gg_demote(grade)
    return {"excluded": "", "score": round(score, 1), "grade": grade,
            "parts": {k: round(v, 2) for k, v in parts.items()},
            "why": " · ".join(why), "warn": " · ".join(warn)}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_market_regime() -> dict:
    """소형주(IWM)·대형주(SPY) 일봉으로 시장 환경 라벨: 강세/중립/약세. 실패하면 '알 수 없음'.
    약세 = IWM 종가가 20일선 아래 + 최근 5일 하락 / 강세 = 20일선 위 + 5일 상승."""
    try:
        out = {}
        for sym in ("IWM", "SPY"):
            c = yf.Ticker(sym).history(period="3mo")["Close"].dropna()
            if len(c) < 25:
                return {"label": "알 수 없음"}
            out[sym] = {"vs_ma20": (float(c.iloc[-1]) / float(c.tail(20).mean()) - 1) * 100,
                        "ret5": (float(c.iloc[-1]) / float(c.iloc[-6]) - 1) * 100}
        iw = out["IWM"]
        label = "약세" if (iw["vs_ma20"] < 0 and iw["ret5"] < 0) else ("강세" if (iw["vs_ma20"] > 0 and iw["ret5"] > 0) else "중립")
        return {"label": label, "iwm_vs_ma20": iw["vs_ma20"], "iwm_ret5": iw["ret5"], "spy_ret5": out["SPY"]["ret5"]}
    except Exception as _e:
        _log_err("fetch_market_regime", _e)
        return {"label": "알 수 없음"}


def _recent_reverse_split(ticker: str, days: int = GAPGO_REVERSE_SPLIT_DAYS) -> bool:
    """최근 days일 야후 뉴스 제목에 역분할(주식병합) 키워드가 있으면 True."""
    now = pd.Timestamp.now(tz="UTC")
    try:
        for raw in fetch_yahoo_news(ticker) or []:
            dt = _news_dt(raw)
            if dt is not None and (now - dt) > pd.Timedelta(days=days):
                continue
            title = parse_yahoo_news_item(raw).get("title", "")
            if any(p.search(title) for p in _REVERSE_SPLIT_PATTERNS):
                return True
    except Exception as _e:
        _log_err("_recent_reverse_split:" + ticker, _e)
    return False


def _et_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="America/New_York")


def _premarket_status_text() -> str:
    """지금이 미국 프리마켓(04:00~09:30 ET, 평일)인지 알려주는 안내 문구. 프리마켓이면 빈 문자열."""
    t = _et_now()
    mins = t.hour * 60 + t.minute
    if t.weekday() < 5 and 240 <= mins < 570:
        return ""
    return (f"지금은 프리마켓 시간이 아닙니다(미국 동부 {t.strftime('%a %H:%M')}). "
            "가장 최근 프리마켓 데이터 기준이거나 결과가 비어 있을 수 있습니다. "
            "프리마켓은 한국시간 11월~3월 18:00~23:30, 3월~11월 17:00~22:30입니다.")


def run_gapgo_scan(min_gap: float, max_gap: float, price_lo: float, price_hi: float, min_pm_vol: int,
                   max_cap_m: int, min_avg_vol: int, max_float: int) -> dict:
    """프리마켓 갭 후보 수집 → 평균거래량·플로트 확인 → 상장폐지/피인수 제외 → 촉매·증자·역분할 → 일봉 위치 → 점수.
    반환: {rows(점수순), excluded(사유 목록), delist_excluded, regime, n_base}"""
    regime = fetch_market_regime()
    base = fetch_premarket_gappers(min_gap, price_lo, price_hi, int(min_pm_vol), int(max_cap_m))
    base = [dict(r) for r in base if r.get("pm_gap", 0) <= max_gap]
    result = {"rows": [], "excluded": [], "delist_excluded": [], "regime": regime, "n_base": len(base)}
    if not base:
        return result

    # ① 평균거래량·플로트 (yfinance info, 1시간 캐시) → 싼 제외 필터
    def _info(r):
        info = fetch_ticker_info(r["ticker"]) or {}
        avg = info.get("averageVolume") or info.get("averageDailyVolume3Month") or info.get("averageVolume10days")
        return r, (float(avg) if avg else None), (float(info["floatShares"]) if info.get("floatShares") else None)

    kept = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for r, avg, fl in ex.map(_info, base):
            r["avg_volume"], r["float_shares"] = avg, fl
            why_ex = gapgo_cheap_exclusion(avg, fl, min_avg_vol, max_float)
            if why_ex:
                result["excluded"].append({"티커": r["ticker"], "종목명": (r.get("name") or "")[:24], "사유": why_ex})
            else:
                kept.append(r)

    # ② 상장폐지·청산·피인수 확정·OTC 제외 (기존 함수, 사이드바 설정 따름)
    kept, delist_ex = filter_delisted(kept, limit=60)
    result["delist_excluded"] = delist_ex
    kept = kept[:60]
    if not kept:
        return result

    # ③ 촉매·증자 공시(기존 함수) + 일봉 위치(돌파임박 점수) + 역분할 뉴스
    attach_catalysts(kept, limit=len(kept))
    daily = prebreakout_enrich(tuple(r["ticker"] for r in kept))
    with ThreadPoolExecutor(max_workers=8) as ex:
        splits = list(ex.map(lambda r: _recent_reverse_split(r["ticker"]), kept))

    rows = []
    for r, rs in zip(kept, splits):
        d = daily.get(r["ticker"]) or {}
        m = d.get("metrics") or {}
        hi20 = (m["price"] * (1 + m["to_hi20"] / 100)) if m.get("price") and m.get("to_hi20") is not None else None
        inp = {**r, "daily_score": d.get("score"), "daily_cap_reason": d.get("cap_reason"), "hi20": hi20,
               "offering_news": r.get("catalyst_offering_news"), "reverse_split": rs, "regime": regime.get("label"),
               "min_avg_vol": min_avg_vol, "max_float": max_float}
        res = calc_gapgo_score(inp)
        if res["excluded"]:
            result["excluded"].append({"티커": r["ticker"], "종목명": (r.get("name") or "")[:24], "사유": res["excluded"]})
            continue
        if r["price"] < NASDAQ_MIN_BID:       # 1달러 미만: 나스닥 결핍통지 추정치를 경고에 덧붙인다
            try:
                comp = calc_nasdaq_compliance(fetch_history(r["ticker"]), r["price"])
                if comp.get("applicable"):
                    txt = (f"결핍통지 추정 후 {comp['days_left']}일 남음" if comp.get("phase") == "notice_issued_est"
                           else f"1달러 미만 {comp['streak_days']}일째(30일이면 결핍통지)")
                    res["warn"] = (res["warn"] + " · " if res["warn"] else "") + txt
            except Exception as _e:
                _log_err("run_gapgo_scan:compliance:" + r["ticker"], _e)
        rows.append({**r, "gg_score": res["score"], "gg_grade": res["grade"], "gg_parts": res["parts"],
                     "gg_why": res["why"], "gg_warn": res["warn"], "gg_daily": d.get("score"),
                     "gg_hi20": hi20, "gg_regime": regime.get("label")})
    rows.sort(key=lambda x: x["gg_score"], reverse=True)
    result["rows"] = rows
    return result


# ── 예측 결과 기록: 당일(시가→고가·종가)과 익일(고가) 결과를 추적 ────────────────────
GAPGO_LOG_PATH = os.environ.get("GAPGO_LOG_PATH", "gapgo_log.csv")
_GAPGO_LOCK = threading.Lock()
GAPGO_LOG_COLUMNS = [
    "run_id", "logged_at_utc", "ticker", "pm_price", "gap_pct", "pm_volume", "score", "grade", "why", "warn", "regime",
    "f_catalyst", "f_pm_volume", "f_gap", "f_float", "f_daily",
    "out_status", "out_open", "out_open_to_high", "out_open_to_close", "out_hit5", "out_hit10", "out_green",
    "out_next_high_vs_close",
]
_GAPGO_OUT_COLS = ["out_status", "out_open", "out_open_to_high", "out_open_to_close", "out_hit5", "out_hit10",
                   "out_green", "out_next_high_vs_close"]


def _read_gapgo_log() -> pd.DataFrame:
    try:
        if os.path.exists(GAPGO_LOG_PATH):
            df = pd.read_csv(GAPGO_LOG_PATH)
            for c in GAPGO_LOG_COLUMNS:
                if c not in df.columns:
                    df[c] = np.nan
            df = df[GAPGO_LOG_COLUMNS].copy()
            df["out_status"] = df["out_status"].astype(object)
            return df
    except Exception as _e:
        _log_err("_read_gapgo_log", _e)
    return pd.DataFrame(columns=GAPGO_LOG_COLUMNS)


def _write_gapgo_log(df: pd.DataFrame) -> None:
    tmp = GAPGO_LOG_PATH + ".tmp"
    df.to_csv(tmp, index=False, encoding="utf-8")
    os.replace(tmp, GAPGO_LOG_PATH)


def log_gapgo_results(rows: list, top_n: int = 30) -> int:
    """점수 상위 top_n 후보를 기록 (같은 날 같은 종목은 중복 기록하지 않음)."""
    try:
        now = pd.Timestamp.now(tz="UTC")
        today_key = now.strftime("%Y-%m-%d")
        with _GAPGO_LOCK:
            cur = _read_gapgo_log()
            done_keys = set(zip(cur["logged_at_utc"].astype(str).str[:10], cur["ticker"]))
            new = []
            for r in rows[:top_n]:
                if (today_key, r["ticker"]) in done_keys:
                    continue
                p = r.get("gg_parts") or {}
                new.append({
                    "run_id": now.strftime("%Y%m%d%H%M%S"), "logged_at_utc": now.isoformat(), "ticker": r["ticker"],
                    "pm_price": r.get("price"), "gap_pct": round(float(r.get("pm_gap") or 0), 2),
                    "pm_volume": r.get("pm_volume"), "score": r.get("gg_score"), "grade": r.get("gg_grade"),
                    "why": r.get("gg_why"), "warn": r.get("gg_warn"), "regime": r.get("gg_regime"),
                    "f_catalyst": p.get("catalyst"), "f_pm_volume": p.get("pm_volume"), "f_gap": p.get("gap"),
                    "f_float": p.get("float"), "f_daily": p.get("daily"), "out_status": "",
                })
            if new:
                _write_gapgo_log(pd.concat([cur, pd.DataFrame(new)], ignore_index=True)[GAPGO_LOG_COLUMNS])
            return len(new)
    except Exception as _e:
        _log_err("log_gapgo_results", _e)
        return 0


def update_gapgo_outcomes(max_rows: int = 80) -> tuple:
    """기록한 날(미국 거래일 D)의 일봉으로 결과를 채운다. 반환: (갱신 건수, 대기 건수)
    - 시가→고가(%)·시가→종가(%)·양봉 여부, 시가→고가가 +5%/+10%에 닿았는지(적중)
    - 익일: D+1 일봉이 생기면 'D 종가 대비 D+1 고가(%)'를 추가로 채운다.
    D일이 아직 끝나지 않았으면(미국 동부 16:05 이전) 대기."""
    with _GAPGO_LOCK:
        df = _read_gapgo_log()
    if df.empty:
        return 0, 0
    need = df[(df["out_status"].isna()) | (df["out_status"] == "") |
              ((df["out_status"] == "done") & (pd.to_numeric(df["out_next_high_vs_close"], errors="coerce").isna()))]
    now_et = _et_now()
    updated = waiting = 0
    for i, row in need.head(max_rows).iterrows():
        try:
            logged = pd.to_datetime(row["logged_at_utc"], utc=True).tz_convert("America/New_York")
            d0 = logged.date() if (logged.hour * 60 + logged.minute) < 16 * 60 else (logged + pd.Timedelta(days=1)).date()
            raw = yf.Ticker(str(row["ticker"])).history(period="1mo")
            if raw is None or raw.empty:
                continue
            idx = pd.to_datetime(raw.index)
            dates = np.array(idx.tz_localize(None).date if idx.tz is None else idx.tz_convert("America/New_York").date)
            day_rows = raw[dates >= d0]
            if day_rows.empty:
                waiting += 1
                continue
            bar_date = np.array(dates[dates >= d0])[0]
            if bar_date == now_et.date() and (now_et.hour * 60 + now_et.minute) < 16 * 60 + 5:
                waiting += 1
                continue
            b = day_rows.iloc[0]
            o, h, l, c = float(b["Open"]), float(b["High"]), float(b["Low"]), float(b["Close"])
            if o <= 0:
                continue
            if df.at[i, "out_status"] != "done":
                oh, oc = (h / o - 1) * 100, (c / o - 1) * 100
                df.at[i, "out_status"], df.at[i, "out_open"] = "done", round(o, 4)
                df.at[i, "out_open_to_high"], df.at[i, "out_open_to_close"] = round(oh, 2), round(oc, 2)
                df.at[i, "out_hit5"], df.at[i, "out_hit10"] = float(oh >= 5), float(oh >= 10)
                df.at[i, "out_green"] = float(c > o)
                updated += 1
            if len(day_rows) >= 2:
                nb = day_rows.iloc[1]
                df.at[i, "out_next_high_vs_close"] = round((float(nb["High"]) / c - 1) * 100, 2)
        except Exception as _e:
            _log_err("update_gapgo_outcomes", _e)
    with _GAPGO_LOCK:
        cur = _read_gapgo_log()
        key = ["run_id", "ticker"]
        upd = df[df["out_status"] == "done"].drop_duplicates(key).set_index(key)
        cur = cur.drop_duplicates(key, keep="last").set_index(key)
        cur.update(upd[_GAPGO_OUT_COLS])
        _write_gapgo_log(cur.reset_index()[GAPGO_LOG_COLUMNS])
    return updated, waiting


def _summarize_gapgo(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["out_status"] == "done"].copy()
    if d.empty:
        return pd.DataFrame()
    for c in ("out_open_to_high", "out_open_to_close", "out_hit5", "out_hit10", "out_green", "out_next_high_vs_close"):
        d[c] = pd.to_numeric(d[c], errors="coerce")

    def _agg(g):
        return pd.Series({"건수": len(g), "시가→고가 +5% 적중(%)": g["out_hit5"].mean() * 100,
                          "시가→고가 +10% 적중(%)": g["out_hit10"].mean() * 100,
                          "평균 시가→고가(%)": g["out_open_to_high"].mean(),
                          "평균 시가→종가(%)": g["out_open_to_close"].mean(),
                          "종가 양봉 비율(%)": g["out_green"].mean() * 100,
                          "평균 익일고가(종가대비 %)": g["out_next_high_vs_close"].mean()})
    out = d.groupby("grade").apply(_agg)
    out.loc["전체(기준선)"] = _agg(d)
    order = {"A": 0, "B": 1, "C": 2, "—": 3, "전체(기준선)": 4}
    return out.sort_index(key=lambda ix: [order.get(i, 9) for i in ix]).round(1)


def render_gapgo_log_panel():
    with st.expander("📊 예측 검증 (점수 기록 · 당일/익일 결과 추적)", expanded=False):
        df = _read_gapgo_log()
        done = int((df["out_status"] == "done").sum()) if not df.empty else 0
        st.caption(f"기록 {len(df)}건 · 결과 확정 {done}건. 스캔할 때마다 상위 후보가 자동 기록되고, 그날 미국 장이 끝나면 "
                   "'결과 업데이트'로 시가→고가·종가가, 다음 거래일이 지나면 익일 고가가 채워집니다.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔄 결과 업데이트", key="update_gapgo", use_container_width=True):
                with st.spinner("당일/익일 결과 계산 중..."):
                    u, w = update_gapgo_outcomes()
                st.success(f"{u}건 갱신 · 장 미종료/데이터 대기 {w}건")
                df = _read_gapgo_log()
        with c2:
            if not df.empty:
                st.download_button("📥 기록 CSV 다운로드", df.to_csv(index=False).encode("utf-8-sig"),
                                   file_name="gapgo_log.csv", mime="text/csv", use_container_width=True)
        up = st.file_uploader("이전 기록 CSV 병합", type=["csv"], key="gapgo_upload")
        if up is not None and st.button("업로드한 기록 병합", key="merge_gapgo"):
            try:
                add = pd.read_csv(up)
                for c in GAPGO_LOG_COLUMNS:
                    if c not in add.columns:
                        add[c] = np.nan
                with _GAPGO_LOCK:
                    merged = pd.concat([_read_gapgo_log(), add[GAPGO_LOG_COLUMNS]], ignore_index=True)
                    _write_gapgo_log(merged.drop_duplicates(subset=["run_id", "ticker"], keep="last"))
                st.success("병합 완료")
                df = _read_gapgo_log()
            except Exception as _e:
                st.error(f"병합 실패: {_e}")
        summ = _summarize_gapgo(df) if done else pd.DataFrame()
        if summ.empty:
            st.info("아직 결과가 확정된 기록이 없습니다. 스캔한 날 미국 장이 끝난 뒤 '결과 업데이트'를 눌러 주세요.")
            return
        st.dataframe(summ, use_container_width=True)
        st.caption("A·B 등급의 적중률이 '전체(기준선)'보다 뚜렷하게 높아야 점수가 의미 있는 것입니다. "
                   "표본이 등급당 30건 미만이면 우연일 수 있으니 참고만 하세요.")


def render_prebreakout_screener():
    """'급등 전 매집' 스캐너 — 프리마켓 갭 5~15% 종목 중 장 시작 후 이어갈 가능성이 높은 후보를 점수·등급으로 보여준다."""
    ui_section_header(mono_icon_badge("target", color="var(--c-violet)"), "급등 전 매집 스캐너 (갭 이어가기)", "icon-violet", "title-violet")
    st.caption("프리마켓 갭 종목을 촉매 30 + 프리마켓 거래량 25 + 갭 크기 15 + 플로트 15 + 일봉 위치 15점으로 평가합니다. "
               "증자·역분할·인수확정·상장폐지 종목은 먼저 제외합니다. 대부분의 갭은 꺾이므로 점수는 후보 선별용이고, "
               "진입은 개장 후 프리마켓 고점 돌파 + VWAP 유지를 확인한 뒤에 판단하세요.")
    _pm_note = _premarket_status_text()
    if _pm_note:
        st.info(_pm_note)

    c1, c2 = st.columns(2)
    with c1:
        gg_gap = st.slider("프리마켓 갭 범위 (%)", 0.0, 100.0, (5.0, 15.0), 0.5, key="gg_gap",
                           help="자료상 이어갈 가능성이 높은 구간은 5~15%입니다. 넓히면 후보가 늘지만 점수에서 큰 갭은 감점됩니다.")
    with c2:
        gg_price = st.slider("주가 범위 ($)", 0.1, 100.0, (0.1, 20.0), 0.1, key="gg_price",
                             help="1달러 미만 종목은 경고가 붙고 등급이 최대 B로 제한됩니다.")
    c3, c4, c5, c6 = st.columns(4)
    with c3:
        gg_min_pm = st.number_input("최소 프리마켓 거래량(주)", min_value=10_000, value=300_000, step=50_000, key="gg_pmvol")
    with c4:
        gg_min_avg = st.number_input("최소 평균거래량(주)", min_value=50_000, value=GAPGO_MIN_AVG_VOL, step=50_000, key="gg_avgvol")
    with c5:
        gg_max_float = st.number_input("플로트 상한(백만 주)", min_value=1, value=GAPGO_MAX_FLOAT // 1_000_000, step=5, key="gg_float")
    with c6:
        gg_max_cap = st.number_input("시총 상한($백만, 0=제한없음)", min_value=0, value=1000, step=100, key="gg_cap")
    gg_min_score = st.slider("최소 점수", 0, 90, 45, 5, key="gg_min_score", help="45 = C등급 이상. 높일수록 후보가 줄어듭니다.")

    if st.button("🔮 스캔 실행", key="run_prebreak", use_container_width=True):
        with st.spinner("프리마켓 갭 수집 → 제외 필터 → 촉매·증자·일봉 점수 계산 중... (1~2분 걸릴 수 있습니다)"):
            out = run_gapgo_scan(gg_gap[0], gg_gap[1], gg_price[0], gg_price[1], int(gg_min_pm), int(gg_max_cap),
                                 int(gg_min_avg), int(gg_max_float) * 1_000_000)
            st.session_state["gg_results"] = out["rows"]
            st.session_state["gg_excluded"] = out["excluded"]
            st.session_state["gg_excluded_delist"] = out["delist_excluded"]
            st.session_state["gg_regime"] = out["regime"]
            st.session_state["gg_nbase"] = out["n_base"]
            st.session_state["gg_logged"] = log_gapgo_results([x for x in out["rows"] if x["gg_score"] >= 45])

    results = st.session_state.get("gg_results")
    if results is None:
        st.info("조건을 설정하고 '🔮 스캔 실행'을 눌러 주세요.")
        render_gapgo_log_panel()
        return
    reg = st.session_state.get("gg_regime") or {}
    if reg.get("label") in ("강세", "중립", "약세"):
        st.caption(f"시장 환경: **{reg['label']}** (IWM 20일선 대비 {reg['iwm_vs_ma20']:+.1f}% · 5일 {reg['iwm_ret5']:+.1f}% · SPY 5일 {reg['spy_ret5']:+.1f}%)"
                   + (" — 약세라 모든 등급을 한 단계 낮췄습니다." if reg["label"] == "약세" else ""))
    else:
        st.caption("시장 환경을 확인하지 못해 등급 보정 없이 표시합니다.")
    filtered = [r for r in results if r["gg_score"] >= gg_min_score]
    st.markdown(f"**{len(filtered)}개 종목** (갭 후보 {st.session_state.get('gg_nbase', 0)}개 → 점수 계산 {len(results)}개 중 {gg_min_score}점 이상)"
                + (f" · 이번 스캔에서 {st.session_state.get('gg_logged', 0)}건 기록" if st.session_state.get("gg_logged") else ""))
    render_excluded_expander("gg_excluded_delist")
    _ex = st.session_state.get("gg_excluded") or []
    if _ex:
        with st.expander(f"🚫 제외된 종목 {len(_ex)}개 (거래량·플로트·증자·역분할)", expanded=False):
            st.dataframe(pd.DataFrame(_ex), use_container_width=True, hide_index=True)
            st.caption("뉴스·공시 키워드 기반이라 오탐이 있을 수 있습니다. 증자 공시는 야후가 제공하는 SEC 서식 목록 기준이며 8-K 5.03(정관 변경) 같은 항목은 감지하지 못합니다.")
    if not filtered:
        st.warning("조건에 맞는 종목이 없습니다. 하루 0~5개가 정상 범위입니다. 갭·거래량 조건을 완화하거나 프리마켓 시간에 다시 실행해 보세요.")
        render_gapgo_log_panel()
        return

    table = []
    for r in filtered:
        avg, fl = r.get("avg_volume"), r.get("float_shares")
        pm_high = r.get("pm_high")
        table.append({
            "⭐": "★" if r["ticker"] in st.session_state.favorites else "",
            "티커": r["ticker"], "종목명": (r.get("name") or "")[:24],
            "등급": r["gg_grade"], "점수": r["gg_score"],
            "프리마켓가": r["price"], "갭(%)": r["pm_gap"], "PM거래량": r["pm_volume"],
            "평균대비(%)": (r["pm_volume"] / avg * 100) if avg else None,
            "플로트(M)": (fl / 1e6) if fl else None,
            "플로트회전(%)": (r["pm_volume"] / fl * 100) if fl else None,
            "PM고점대비(%)": ((r["price"] / pm_high - 1) * 100) if pm_high else None,
            "20일고점돌파": "O" if (r.get("gg_hi20") and r["price"] >= r["gg_hi20"] * 0.99) else "",
            "촉매": r.get("catalyst", "—"), "근거": r["gg_why"], "경고": r["gg_warn"],
        })
    event = st.dataframe(
        pd.DataFrame(table), use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row", key="gg_df",
        column_config={
            "점수": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100,
                                                  help="촉매30+PM거래량25+갭15+플로트15+일봉위치15. A≥75, B≥60, C≥45"),
            "프리마켓가": st.column_config.NumberColumn(format="$%.2f"),
            "갭(%)": st.column_config.NumberColumn(format="%+.1f%%"),
            "PM거래량": st.column_config.NumberColumn(format="%d"),
            "평균대비(%)": st.column_config.NumberColumn(format="%.0f%%", help="프리마켓 거래량 ÷ 평균 일거래량"),
            "플로트(M)": st.column_config.NumberColumn(format="%.1f"),
            "플로트회전(%)": st.column_config.NumberColumn(format="%.1f%%", help="프리마켓 거래량 ÷ 유통주식수"),
            "PM고점대비(%)": st.column_config.NumberColumn(format="%+.1f%%", help="프리마켓 현재가가 프리마켓 고점에서 얼마나 내려왔나"),
        })
    st.caption("행을 클릭하면 정밀 분석 화면으로 이동합니다. 가중치는 초안이므로 아래 '예측 검증'으로 등급별 적중률을 확인하며 보정하세요. "
               "진입 확인: 개장 후 프리마켓 고점 돌파 + VWAP 유지 / 프리마켓 고점 재이탈은 실패 신호입니다.")
    sel = []
    if event is not None:
        try:
            sel = event.selection["rows"]
        except Exception:
            sel = []
    if sel:
        picked = filtered[sel[0]]["ticker"]
        st.session_state["selected_ticker"] = picked
        st.session_state["active_ticker"] = picked
        st.session_state["has_searched"] = True
        st.rerun()
    render_gapgo_log_panel()


def render_prebreakout_panel(hist: pd.DataFrame):
    """종목 상세 화면: 돌파 임박 점수의 구성요소를 보여주는 카드."""
    res = calc_prebreakout_score(hist)
    if not res:
        return
    ui_section_header(mono_icon_badge("target", color="var(--c-violet)"), "급등 전 매집 · 돌파 임박", "icon-violet", "title-violet")
    m, f = res["metrics"], res["factors"]
    sdot = {"임박": "dot-green", "준비": "dot-green", "관찰": "dot-yellow"}.get(res["stage"], "dot-blue")
    cap_txt = f" · 상한 {res['cap']}점({_safe_html(res['cap_reason'])})" if res.get("cap") else ""
    rows = [
        (sdot, f"<strong>{res['stage']} · {res['score']:.0f}점</strong>{cap_txt} — {_safe_html(res['why'])}"),
        ("dot-blue", f"변동성 축소 {f['contraction']:.2f} · 거래량 선행 {f['accumulation']:.2f} · "
                     f"20일선 직전 {f['ma20']:.2f} · 미과열 {f['notext']:.2f} (각 0~1, 곱셈형이라 낮은 항목이 점수를 끌어내림)"),
    ]
    if res["warn"]:
        rows.append(("dot-red", f"<strong>경고</strong> {_safe_html(res['warn'])}"))
    items = "".join(f'<div class="status-item"><div class="status-dot {d}"></div><div class="status-text">{t}</div></div>' for d, t in rows)
    st.markdown(f'<div class="glass-card"><div class="status-row">{items}</div></div>', unsafe_allow_html=True)



def render_volume_surge_screener():
    """
    "최근 3일 평균 거래량이 최근 3개월 평균 거래량 대비 N배 이상"인
    나스닥 종목을 찾는 스크리너.

    1차: Yahoo 공식 스크리너로 나스닥(NMS/NGM/NCM) 상장 + 당일 거래량 상위
         후보군을 넉넉히(기본 250개) 조회 — Yahoo 스크리너에는 "N개월 평균
         대비 배율" 필드가 없어 거래량 자체로 넓게 후보를 추린다.
    2차: 후보별 1년치 일봉을 병렬로 내려받아(enrich_screener_results 재사용)
         실제 "최근 3일 평균 / 최근 63거래일(약 3개월) 평균" 비율을 계산.
    3차: 비율 ≥ 배수 조건으로 필터링 후 비율 내림차순 정렬.
    """
    ui_section_header(mono_icon_badge("trend", color="var(--c-cyan)"), "거래량 급증 스크리너", "icon-cyan", "title-cyan")
    st.caption("최근 3일 평균 거래량이 최근 3개월(약 63거래일) 평균 거래량 대비 N배 이상인 나스닥 종목을 찾습니다.")

    v1, v2, v3 = st.columns(3)
    with v1:
        surge_multiple = st.number_input(
            "최소 배율 (3일 평균 ÷ 3개월 평균)", min_value=1.0, max_value=50.0,
            value=5.0, step=0.5, key="vol_surge_multiple"
        )
    with v2:
        vs_price_range = st.slider(
            "주가 범위 ($)", min_value=0.1, max_value=200.0, value=(0.1, 50.0), step=0.1,
            key="vol_surge_price_range"
        )
    with v3:
        vs_min_day_volume = st.number_input(
            "1차 후보 최소 당일 거래량", min_value=0, value=200_000, step=100_000,
            key="vol_surge_min_vol",
            help="너무 낮으면 1차 후보가 너무 많아져 정밀 계산이 오래 걸릴 수 있습니다."
        )

    if st.button("🔍 검색 실행", key="run_vol_surge_screener", use_container_width=True):
        with st.spinner("나스닥 후보 종목 조회 및 3일/3개월 거래량 비율 계산 중... (후보가 많을수록 오래 걸릴 수 있습니다)"):
            base = fetch_volume_surge_candidates(
                vs_price_range[0], vs_price_range[1], int(vs_min_day_volume)
            )
            tickers = tuple(r["ticker"] for r in base if r.get("ticker"))
            enriched_map = enrich_screener_results(tickers) if tickers else {}

            merged = []
            for r in base:
                extra = enriched_map.get(r["ticker"], {})
                if extra.get("error"):
                    continue
                merged.append({**r, **extra})
            _hits = [r for r in merged if r.get("vol_surge_ratio", 0) >= surge_multiple]
            _hits.sort(key=lambda r: r.get("vol_surge_ratio", 0), reverse=True)
            # 상장폐지 확정·청산·피인수 확정·OTC 종목 제외 (배율 상위 60개 조회)
            _hits, _excl = filter_delisted(_hits, limit=60)
            _ex_set = {e["티커"] for e in _excl}
            merged = [r for r in merged if str(r.get("ticker", "")).replace("⚠️ ", "").strip() not in _ex_set]
            st.session_state["vol_surge_excluded"] = _excl
            attach_beams(_hits, "ticker", "beam", [True] * len(_hits), limit=30)
            st.session_state["vol_surge_results"] = merged

    results = st.session_state.get("vol_surge_results", [])
    if not results:
        st.info("조건을 설정하고 '🔍 검색 실행' 버튼을 눌러주세요.")
        return

    filtered = [r for r in results if r.get("vol_surge_ratio", 0) >= surge_multiple]
    filtered.sort(key=lambda r: r.get("vol_surge_ratio", 0), reverse=True)

    st.markdown(f"**{len(filtered)}개 종목** (1차 후보 {len(results)}개 중 {surge_multiple}배 이상 필터링 결과)")
    render_excluded_expander("vol_surge_excluded")

    if not filtered:
        st.warning("조건에 맞는 종목이 없습니다. 배율을 낮추거나 1차 후보 최소 거래량을 낮춰 보세요.")
        return

    rows = []
    for r in filtered:
        is_fav = r["ticker"] in st.session_state.favorites
        rows.append({
            "⭐":              "★" if is_fav else "",
            "티커":            ("⚠️ " if r.get("is_china") else "") + r["ticker"],
            "종목명":          (r.get("name") or "")[:26],
            "현재가":          r.get("price", 0),
            "등락률(%)":       r.get("pct_change", 0),
            "배율(3일/3개월)": r.get("vol_surge_ratio", 0),
            "3일 평균 거래량":  r.get("vol_3d", 0),
            "3개월 평균 거래량": r.get("vol_3m", 0),
            "당일 거래량":      r.get("volume", 0),
            "빔신호":          r.get("beam", "") or "—",
        })

    df_display = pd.DataFrame(rows)

    event = st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "현재가":           st.column_config.NumberColumn(format="$%.2f"),
            "등락률(%)":        st.column_config.NumberColumn(format="%+.2f%%"),
            "배율(3일/3개월)":   st.column_config.NumberColumn(format="%.1f배"),
            "3일 평균 거래량":   st.column_config.NumberColumn(format="%d"),
            "3개월 평균 거래량": st.column_config.NumberColumn(format="%d"),
            "당일 거래량":       st.column_config.NumberColumn(format="%d"),
        },
        key="vol_surge_df",
    )

    st.caption("⚠️ = 중국/홍콩 소재 기업 · ⭐ = 즐겨찾기 등록 종목 · 3개월 평균은 최근 약 63거래일 기준입니다. "
               "행을 클릭하면 해당 종목의 정밀 분석 화면으로 이동합니다.")

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
        ratio_html = f" &nbsp;·&nbsp; 비율(추정): <strong>{_safe_html(s['ratio'])}</strong>" if s["ratio"] else ""
        if s["effective_date"]:
            date_html = f"시행(effective) 예정일: <strong>{_safe_html(s['effective_date'])}</strong>"
        else:
            date_html = "시행일이 뉴스 원문에 명시되지 않음 — 원문 링크에서 정확한 일정을 확인하세요"
        pub_html = f" (게재일: {_safe_html(s['date'])})" if s["date"] else ""
        _su = _safe_url(s["link"])
        link_html = f"<br><a class='news-link' href='{_su}' target='_blank'>관련 뉴스 원문 보기 →</a>" if _su else ""
        st.markdown(f"""
        <div class="split-banner">
            <div class="split-banner-title">⚠️ 주식병합(리버스 스플릿) 관련 뉴스 감지{pub_html}</div>
            <div class="split-banner-body">{date_html}{ratio_html}<br>{_safe_html(s['title'])}{link_html}</div>
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

        raw_news_list = fetch_yahoo_news(ticker_input)[:3]
        parsed_list   = [parse_yahoo_news_item(r) for r in raw_news_list]
        titles_en     = [n["title"] for n in parsed_list]

        _translations = translate_texts_batch(titles_en, st.session_state.get("gemini_api_key", ""))
        translated    = [_translations.get(t, t) for t in titles_en]

        split_source = [
            {"date": "", "title": t_ko, "title_en": n["title"], "link": n["link"]}
            for n, t_ko in zip(parsed_list, translated)
        ]
        _render_reverse_split_banner(detect_reverse_split_news(split_source))

        for news_item, title_ko in zip(parsed_list, translated):
            st.markdown(f"""
            <div class="news-card">
                <div class="news-meta">📰 {_safe_html(news_item['publisher'])}</div>
                <div class="news-title">{_safe_html(title_ko)}</div>
                <a class="news-link" href="{_safe_url(news_item['link'])}" target="_blank">기사 원문 보기 →</a>
            </div>
            """, unsafe_allow_html=True)
    else:
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
                <div class="news-meta">📅 {_safe_html(n['date'])} &nbsp;{sent_html}{impact_html}</div>
                <div class="news-title">{_safe_html(n['title'])}</div>
                <div class="news-orig">{_safe_html(n['title_en'])}</div>
                <a class="news-link" href="{_safe_url(n['link'])}" target="_blank">스톡타이탄 원문 보기 →</a>
            </div>
            """, unsafe_allow_html=True)
            # ════════════════════════════════════════════════════════════════
# Part 11 / 메인 실행부 (토글 화면 · 티커 검색 · 탭 전환)
# ════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════
# 섹터 히트맵 · 검색기 (토글)
# ════════════════════════════════════════════════════════════════
if st.session_state.get("show_heatmap", False):
    render_sector_heatmap()
    st.markdown("---")

if st.session_state.get("show_screener", False):
    render_surge_screener()
    st.markdown("---")

if st.session_state.get("show_vol_surge", False):
    render_volume_surge_screener()
    st.markdown("---")

if st.session_state.get("show_prebreak", False):
    render_prebreakout_screener()
    st.markdown("---")

# ════════════════════════════════════════════════════════════════
# 메인 대시보드 로직
# ════════════════════════════════════════════════════════════════
if search_button:
    # 버튼 클릭 순간에만 True이므로 session_state에 검색 상태를 저장해
    # 차트 기간 라디오 등 다른 위젯 상호작용 후에도 결과가 유지되게 한다.
    st.session_state["active_ticker"] = ticker_input
    st.session_state["has_searched"]  = True

if st.session_state.get("has_searched"):
    active_ticker = st.session_state.get("active_ticker", ticker_input)

    with st.spinner("야후 파이낸스 및 스톡타이탄에서 실시간 데이터를 분석 중입니다..."):
        # 서로 의존관계 없는 네트워크 호출을 동시에 실행
        with ThreadPoolExecutor(max_workers=5) as _prefetch_ex:
            _fut_hist     = _prefetch_ex.submit(fetch_history, active_ticker)
            _fut_spike    = _prefetch_ex.submit(fetch_spike_history, active_ticker)
            _fut_offering = _prefetch_ex.submit(fetch_offering_history, active_ticker)
            _fut_info     = _prefetch_ex.submit(fetch_ticker_info, active_ticker)
            _fut_fx       = _prefetch_ex.submit(fetch_usd_to_krw)

            hist          = _fut_hist.result()
            spike_df      = _fut_spike.result()
            offering_list = _fut_offering.result()
            _fut_info.result()   # 캐시 예열 목적
            usd_krw       = _fut_fx.result()

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
            vol_ma20       = today['VOL_MA20'] if today['VOL_MA20'] > 0 else 1
            vol_ma20_ratio = (today['Volume'] / vol_ma20) * 100

            # 거래대금 (실시간 환율 적용)
            trading_value_usd     = today['Close'] * today['Volume']
            trading_value_krw_eok = (trading_value_usd * usd_krw) / 100_000_000

            # 52주 최고/최저
            high_52w = hist['High'].max()
            low_52w  = hist['Low'].min()

            # 나스닥 $1 컴플라이언스 추정
            nasdaq_compliance = calc_nasdaq_compliance(hist, today['Close'])

            # 급등주 검색기·즐겨찾기 스캔과 동일 기준의 종합점수 산출
            pct_change_now = ((today['Close'] - yesterday['Close']) / yesterday['Close']) * 100
            current_rsi_val = today['RSI']
            current_rsi = round(float(current_rsi_val), 1) if pd.notna(current_rsi_val) else None
            # 상단 카드 점수 = 급등 전 매집·돌파 임박 예측 점수 (당일 단타 셋업 등급은 '단타 보조 분석' 카드에 별도 표시)
            _pbres = calc_prebreakout_score(hist)
            ticker_score = _pbres.get("score") if _pbres else None
            if detect_delisting(active_ticker):      # 상장폐지·청산·피인수 확정 종목은 점수가 무의미하므로 카드에서 숨긴다
                ticker_score = None

            top_cards_front, top_cards_end = build_top_summary_cards_html(
                today, yesterday, hist, vol_ma20_ratio, score=ticker_score
            )
            render_technical_analysis(
                active_ticker, hist, today, yesterday,
                vol_ratio, vol_ma20_ratio,
                trading_value_krw_eok, TRADING_THRESHOLD,
                high_52w, low_52w,
                spike_df, offering_list, nasdaq_compliance,
                top_cards_front=top_cards_front, top_cards_end=top_cards_end,
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
