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
}

def mono_icon_badge(icon_key: str, color: str = "#111827", size: int = 32,
                     glyph_size: int = 16, outline: bool = False) -> str:
    """단색 원형 배지 아이콘 HTML(SVG)을 반환.

    outline=False → 속이 찬 원(색상=color) + 흰색 아이콘 (참고 이미지 위쪽 2줄 스타일)
    outline=True  → 테두리만 있는 원(색상=color) + 동일 색 아이콘 (참고 이미지 아래쪽 2줄 스타일)
    """
    path = _ICON_SVG.get(icon_key, "")
    if outline:
        return (
            f'<div style="width:{size}px;height:{size}px;border-radius:50%;'
            f'border:1.6px solid {color};display:flex;align-items:center;'
            f'justify-content:center;flex-shrink:0;">'
            f'<svg width="{glyph_size}" height="{glyph_size}" viewBox="0 0 24 24" '
            f'fill="none" stroke="{color}" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round">{path}</svg></div>'
        )
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:50%;'
        f'background:{color};display:flex;align-items:center;'
        f'justify-content:center;flex-shrink:0;">'
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
    "dark_mode":        False,          # 다크/라이트 모드 토글 (기본값: 라이트 모드)
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
            vol_ma20  = today['VOL_MA20'] if today['VOL_MA20'] > 0 else 1
            vol_ma20_ratio = (today['Volume'] / vol_ma20) * 100

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

@st.cache_data(ttl=3600, show_spinner=False)
def translate_text(text: str) -> str:
    """GoogleTranslator 호출 결과 캐싱 — 동일 문장 재번역 방지"""
    if not text:
        return text
    try:
        return GoogleTranslator(source='en', target='ko').translate(text)
    except Exception:
        return text

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
def calc_supply_zones(hist: pd.DataFrame, current_price: float,
                       n_bins: int = 40, lookback_days: int = 252,
                       heavy_mult: float = 1.3, max_zones: int = 4) -> dict:
    """
    최근 lookback_days(기본 1년) 동안의 일별 High~Low 구간에 그날의 거래량을
    균등 분산시켜 '거래량 프로파일(Volume Profile)'을 만든 뒤, 현재가보다 위쪽에서
    평균 대비 거래량이 몰려있는 가격대(=매물대, 이전 매수자들의 평단가 밀집구간)를
    현재가에 가까운 순으로 추출한다.
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
    """현재가 위쪽 악성매물대(저항 구간) — 4개 항목만 표시"""
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

    strength_dot = {"매우 강함": "dot-red", "강함": "dot-yellow", "보통": "dot-blue"}

    rows_html = ""
    for z in zones:
        dot = strength_dot.get(z["strength"], "dot-blue")
        rows_html += f"""
        <div class="status-item">
            <div class="status-dot {dot}"></div>
            <div class="status-text">
                ${z['low']:.2f} ~ ${z['high']:.2f} &nbsp;|&nbsp;
                {z['volume']:,.0f}주 &nbsp;|&nbsp;
                {z['strength']} &nbsp;|&nbsp;
                +{z['gap_pct']:.1f}%
            </div>
        </div>
        """

    st.markdown(f"""
    <div class="glass-card">
        <div class="status-row" style="flex-direction:column;align-items:stretch;gap:0.5rem;">
            {rows_html}
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

        # 1단계: 기사 목록 파싱
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

            title_ko = translate_text(title)
            raw_list.append({"date": date_str, "title": title_ko, "title_en": title, "link": link})
            if len(raw_list) >= 5:
                break

        # 2단계: 상세 페이지 병렬 요청
        detail_results = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_link = {
                executor.submit(_fetch_detail, item["link"], _random_headers()): item["link"]
                for item in raw_list
            }
            for future in as_completed(future_to_link):
                link = future_to_link[future]
                detail_results[link] = future.result()

        # 3단계: 결합
        news_list = []
        for item in raw_list:
            sentiment, impact = detail_results.get(item["link"], ("Unknown", "Normal"))
            news_list.append({**item, "sentiment": sentiment, "impact": impact})

        return news_list
    except Exception:
        return []

# ════════════════════════════════════════════════════════════════
# 소셜 미디어 — StockTwits & Reddit
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
                    "user": username, "body": body, "sentiment": sentiment,
                    "likes": likes, "date": created, "link": link,
                })
            if messages:
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

    messages  = []
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
        pub       = parsed["publisher"]
        link      = parsed["link"]
        title_ko  = translate_text(title)
        messages.append({
            "user": pub, "body": title_ko, "body_en": title,
            "sentiment": sentiment, "likes": 0,
            "date": "", "link": link,
        })
        if len(messages) >= 8:
            break

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
        src_color = "#38bdf8"
        src_badge_cls = "platform-badge"
    else:
        src_icon_key = "news"
        src_label = "Yahoo Finance 뉴스 감성 분석"
        src_color = "#a78bfa"
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
                source_html = f'<span class="{src_badge_cls}" style="background:rgba(167,139,250,0.12);color:#a78bfa;border-color:rgba(167,139,250,0.25);">Yahoo Finance</span>{badge}<span>📰 {user_name}</span>'

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
# CSS — 다크/라이트 모드 동적 주입
# ════════════════════════════════════════════════════════════════
def inject_css(dark: bool = True):
    if dark:
        bg_main      = "linear-gradient(135deg, #05080f 0%, #0a1220 45%, #0d1b2e 100%)"
        bg_sidebar   = "linear-gradient(180deg, #070d18 0%, #0d1b2e 100%)"
        glass_bg     = "rgba(255,255,255,0.04)"
        glass_border = "rgba(255,255,255,0.09)"
        metric_bg    = "rgba(255,255,255,0.045)"
        metric_bdr   = "rgba(255,255,255,0.1)"
        tab_bg       = "rgba(255,255,255,0.04)"
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
        text_muted   = "rgba(148,163,184,0.7)"
        text_dimmed  = "rgba(148,163,184,0.55)"
        text_status  = "#cbd5e1"
        metric_label = "rgba(148,163,184,0.7)"
        sidebar_input_bg  = "rgba(255,255,255,0.05)"
        sidebar_input_bdr = "rgba(139,92,246,0.4)"
        sidebar_input_clr = "#e2e8f0"
        textarea_bg  = "rgba(255,255,255,0.04)"
        plotly_tmpl  = "plotly_dark"
        sector_name_clr  = "rgba(255,255,255,0.7)"
        sector_ticker_clr= "rgba(255,255,255,0.4)"
        social_selftext_bdr = "rgba(255,255,255,0.1)"
        social_selftext_clr = "rgba(203,213,225,0.75)"

        # ── 다이나믹 다크모드 배경: 메시 그라디언트 + 파티클(트윙클) 오버레이 ──
        mesh_bg_layers = (
            "radial-gradient(circle at 12% 18%, rgba(56,189,248,0.18), transparent 38%),"
            "radial-gradient(circle at 88% 12%, rgba(167,139,250,0.16), transparent 40%),"
            "radial-gradient(circle at 78% 82%, rgba(52,211,153,0.12), transparent 42%),"
            "radial-gradient(circle at 18% 86%, rgba(244,63,94,0.10), transparent 38%),"
            "radial-gradient(circle at 50% 50%, rgba(245,158,11,0.06), transparent 55%)"
        )
        mesh_bg_size  = "180% 180%, 160% 160%, 200% 200%, 170% 170%, 220% 220%, 100% 100%"
        mesh_bg_anim  = "meshFloat 26s ease-in-out infinite"
        mesh_keyframes_css = """
        @keyframes meshFloat {
            0%   { background-position: 10% 20%, 90% 10%, 80% 85%, 15% 90%, 50% 50%, 0 0; }
            50%  { background-position: 30% 35%, 65% 25%, 70% 65%, 30% 75%, 55% 45%, 0 0; }
            100% { background-position: 10% 20%, 90% 10%, 80% 85%, 15% 90%, 50% 50%, 0 0; }
        }
        @keyframes particleTwinkle {
            0%   { opacity: 0.35; }
            50%  { opacity: 0.85; }
            100% { opacity: 0.35; }
        }
        """
        particle_overlay_css = """
        [data-testid="stAppViewContainer"] { position: relative; }
        [data-testid="stAppViewContainer"] > .main { position: relative; z-index: 1; }
        [data-testid="stAppViewContainer"]::before {
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            z-index: 0;
            background-image:
                radial-gradient(circle at 8%  22%, rgba(255,255,255,0.9) 0, rgba(255,255,255,0.9) 1px, transparent 1.5px),
                radial-gradient(circle at 23% 68%, rgba(255,255,255,0.7) 0, rgba(255,255,255,0.7) 1px, transparent 1.5px),
                radial-gradient(circle at 41% 12%, rgba(56,189,248,0.8)  0, rgba(56,189,248,0.8)  1px, transparent 1.5px),
                radial-gradient(circle at 62% 78%, rgba(255,255,255,0.6) 0, rgba(255,255,255,0.6) 1px, transparent 1.5px),
                radial-gradient(circle at 77% 34%, rgba(167,139,250,0.8) 0, rgba(167,139,250,0.8) 1px, transparent 1.5px),
                radial-gradient(circle at 89% 58%, rgba(255,255,255,0.7) 0, rgba(255,255,255,0.7) 1px, transparent 1.5px),
                radial-gradient(circle at 95% 15%, rgba(52,211,153,0.8)  0, rgba(52,211,153,0.8)  1px, transparent 1.5px),
                radial-gradient(circle at 34% 90%, rgba(255,255,255,0.6) 0, rgba(255,255,255,0.6) 1px, transparent 1.5px);
            background-repeat: no-repeat;
            animation: particleTwinkle 5s ease-in-out infinite alternate;
        }
        """
    else:
        bg_main      = "linear-gradient(135deg, #f0f4ff 0%, #e8eeff 40%, #f0f7ff 100%)"
        bg_sidebar   = "linear-gradient(180deg, #eef2ff 0%, #e8f0fe 100%)"
        glass_bg     = "rgba(255,255,255,0.72)"
        glass_border = "rgba(99,102,241,0.15)"
        metric_bg    = "rgba(255,255,255,0.8)"
        metric_bdr   = "rgba(99,102,241,0.15)"
        tab_bg       = "rgba(255,255,255,0.7)"
        tab_bdr      = "rgba(99,102,241,0.15)"
        status_bg    = "rgba(255,255,255,0.7)"
        status_bdr   = "rgba(99,102,241,0.12)"
        news_bg      = "rgba(255,255,255,0.72)"
        news_bdr     = "rgba(99,102,241,0.15)"
        social_bg    = "rgba(255,255,255,0.72)"
        social_bdr   = "rgba(99,102,241,0.15)"
        sent_wrap_bg = "rgba(255,255,255,0.8)"
        sent_wrap_bdr= "rgba(99,102,241,0.12)"
        sent_track   = "rgba(99,102,241,0.1)"
        hr_color     = "rgba(99,102,241,0.12)"
        text_primary = "#1e1b4b"
        text_sec     = "#312e81"
        text_muted   = "#6b7280"
        text_dimmed  = "#9ca3af"
        text_status  = "#374151"
        metric_label = "#6b7280"
        sidebar_input_bg  = "rgba(255,255,255,0.9)"
        sidebar_input_bdr = "rgba(99,102,241,0.4)"
        sidebar_input_clr = "#1e1b4b"
        textarea_bg  = "rgba(255,255,255,0.9)"
        plotly_tmpl  = "plotly_white"
        sector_name_clr  = "#374151"
        sector_ticker_clr= "#6b7280"
        social_selftext_bdr = "rgba(99,102,241,0.2)"
        social_selftext_clr = "#4b5563"

        # 라이트 모드는 정적 배경 유지 (다이나믹 메시/파티클은 다크모드 전용)
        mesh_bg_layers      = ""
        mesh_bg_size        = "100% 100%"
        mesh_bg_anim        = "none"
        mesh_keyframes_css  = ""
        particle_overlay_css = ""

    st.session_state["_plotly_template"] = plotly_tmpl

    st.markdown(f"""
<style>
    /* ── 폰트 임포트 ──────────────────────────────────────────────── *
     * 디스플레이 & 본문: Manrope (모던/미니멀)                         *
     * 데이터: JetBrains Mono (가격/티커/지표 — 자릿수 정렬되는 단말기 느낌) */
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap');

    :root {{
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
    }}

    /* ── 전역 배경 & 폰트 ─────────────────────────────────────────── */
    html, body, [data-testid="stAppViewContainer"] {{
        background-image: {mesh_bg_layers}{"," if mesh_bg_layers else ""} {bg_main} !important;
        background-size: {mesh_bg_size} !important;
        background-attachment: fixed !important;
        animation: {mesh_bg_anim};
        font-family: var(--font-body);
    }}
    {mesh_keyframes_css}
    {particle_overlay_css}
    h1, h2, h3, .app-header h1, .section-title, .glass-card-title,
    .scan-title, .alert-title {{ font-family: var(--font-display); }}
    .metric-value, .metric-delta, .sector-pct, .sector-sub, .sector-ticker,
    [data-testid="stDataFrame"] * {{
        font-family: var(--font-mono) !important;
        font-variant-numeric: tabular-nums;
    }}
    [data-testid="stAppViewContainer"] > .main {{ background: transparent !important; }}
    .block-container {{ padding: 1.2rem 1.5rem 2rem 1.5rem !important; max-width: 900px; }}

    /* ── 사이드바 ──────────────────────────────────────────────────── */
    [data-testid="stSidebar"] {{
        background: {bg_sidebar} !important;
        border-right: 1px solid rgba(139, 92, 246, 0.2);
    }}
    [data-testid="stSidebar"] .stTextInput input {{
        background: {sidebar_input_bg} !important;
        border: 1px solid {sidebar_input_bdr} !important;
        border-radius: 10px !important;
        color: {sidebar_input_clr} !important;
        font-family: var(--font-mono) !important;
        font-size: 1rem !important;
        letter-spacing: 0.5px !important;
        padding: 0.6rem 0.8rem !important;
    }}

    /* ── 헤더 배너 ─────────────────────────────────────────────────── */
    .app-header {{
        background: linear-gradient(135deg, rgba(245,185,66,0.18) 0%, rgba(251,113,133,0.16) 45%, rgba(99,102,241,0.2) 100%);
        border: 1px solid rgba(245,185,66,0.3);
        border-radius: 22px;
        padding: 1.4rem 1.8rem;
        margin-bottom: 1.4rem;
        backdrop-filter: blur(12px);
        box-shadow: 0 8px 32px rgba(99,102,241,0.15), inset 0 1px 0 rgba(255,255,255,0.08);
    }}
    .app-header h1 {{
        margin: 0 0 0.2rem 0;
        font-size: 1.15rem;
        font-weight: 800;
        background: linear-gradient(90deg, #f5b942, #fb7185, #818cf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        letter-spacing: -0.3px;
    }}
    .app-header p {{
        margin: 0;
        color: {text_muted};
        font-size: 0.72rem;
    }}

    /* ── 글래스 카드 공통 ──────────────────────────────────────────── */
    .glass-card {{
        background: {glass_bg};
        border: 1px solid {glass_border};
        border-radius: 20px;
        padding: 1.15rem 1.25rem;
        margin-bottom: 1rem;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }}
    .glass-card-title {{
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 1.2px;
        text-transform: uppercase;
        color: {text_muted};
        margin-bottom: 0.6rem;
    }}

    /* ── 메트릭 카드 ──────────────────────────────────────────────── */
    .metric-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-bottom: 1rem; }}
    .metric-card {{
        background: {metric_bg};
        border: 1px solid {metric_bdr};
        border-radius: 18px;
        padding: 1rem 1.1rem;
        backdrop-filter: blur(8px);
        box-shadow: 0 2px 12px rgba(0,0,0,0.2);
        transition: transform 0.15s;
    }}
    .metric-card:hover {{ transform: translateY(-2px); }}
    .metric-card {{ border-left: 3px solid transparent; }}
    .mc-amber  {{ border-left-color: var(--c-amber-a65)  !important; }}
    .mc-violet {{ border-left-color: var(--c-violet-a65) !important; }}
    .mc-rose   {{ border-left-color: var(--c-rose-a65)   !important; }}
    .mc-cyan   {{ border-left-color: var(--c-cyan-a65)   !important; }}
    .mc-indigo {{ border-left-color: var(--c-indigo-a65) !important; }}
    .mc-teal   {{ border-left-color: var(--c-teal-a65)   !important; }}
    .metric-label {{ font-size: 0.7rem; color: {metric_label}; font-weight: 600; letter-spacing: 0.8px; text-transform: uppercase; margin-bottom: 0.35rem; }}
    .metric-value {{ font-size: 1.45rem; font-weight: 800; color: {text_primary}; line-height: 1; }}
    .metric-delta {{ font-size: 0.78rem; font-weight: 600; margin-top: 0.3rem; }}
    .delta-up   {{ color: #34d399; }}
    .delta-down {{ color: #f87171; }}
    .delta-neu  {{ color: #94a3b8; }}

    /* ── 상단 st.metric 스코어보드 글씨 크기 축소 ─────────────────────── */
    [data-testid="stMetric"] {{ gap: 0.15rem; }}
    [data-testid="stMetricLabel"] {{ font-size: 0.72rem !important; }}
    [data-testid="stMetricValue"] {{ font-size: 1.3rem !important; line-height: 1.15 !important; }}
    [data-testid="stMetricDelta"] {{ font-size: 0.72rem !important; }}
    [data-testid="stMetricValue"] > div {{
        overflow: visible !important;
        white-space: nowrap !important;
        text-overflow: clip !important;
    }}

    /* ── 신호 알림 배너 ────────────────────────────────────────────── */
    .alert-banner {{
        background: linear-gradient(135deg, var(--c-red-a18), var(--c-yellow-a12));
        border: 1px solid var(--c-red-a45);
        border-radius: 14px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
        display: flex;
        align-items: flex-start;
        gap: 0.7rem;
        box-shadow: 0 0 20px var(--c-red-a12);
    }}
    .alert-icon {{ font-size: 1.4rem; line-height: 1; }}
    .alert-title {{ font-size: 0.72rem; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; color: #fca5a5; margin-bottom: 0.3rem; }}
    .alert-signals {{ display: flex; flex-wrap: wrap; gap: 0.4rem; }}
    .signal-chip {{
        background: var(--c-red-a20);
        border: 1px solid var(--c-red-a35);
        border-radius: 20px;
        padding: 0.2rem 0.7rem;
        font-size: 0.75rem;
        font-weight: 600;
        color: #fca5a5;
    }}
    .china-banner {{
        background: linear-gradient(135deg, rgba(220,38,38,0.28), rgba(220,38,38,0.12));
        border: 1.5px solid rgba(248,113,113,0.75);
        border-radius: 14px;
        padding: 0.85rem 1.2rem;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 0.7rem;
        box-shadow: 0 0 22px rgba(220,38,38,0.25);
    }}
    .china-banner-icon {{ font-size: 1.3rem; line-height: 1; }}
    .china-banner-text {{ font-size: 0.85rem; font-weight: 700; color: #fecaca; letter-spacing: 0.3px; }}
    .china-banner-sub {{ font-size: 0.72rem; font-weight: 500; color: rgba(254,202,202,0.75); margin-top: 0.15rem; }}
    .split-banner {{
        background: linear-gradient(135deg, rgba(245,158,11,0.22), rgba(245,158,11,0.08));
        border: 1.5px solid rgba(251,191,36,0.6);
        border-radius: 14px;
        padding: 0.85rem 1.2rem;
        margin-bottom: 0.8rem;
    }}
    .split-banner-title {{ font-size: 0.85rem; font-weight: 700; color: #fbbf24; letter-spacing: 0.3px; margin-bottom: 0.3rem; }}
    .split-banner-body  {{ font-size: 0.8rem; color: {text_status}; line-height: 1.5; }}
    .split-banner-body strong {{ color: {text_primary}; }}

    /* ── 섹션 헤더 ─────────────────────────────────────────────────── */
    .section-header {{
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin: 1.3rem 0 0.7rem 0;
    }}
    .section-icon {{
        width: 32px; height: 32px;
        background: linear-gradient(135deg, var(--c-violet-std), var(--c-indigo-a20));
        border: 1px solid var(--c-violet-bdr);
        border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 0.9rem;
        flex-shrink: 0;
    }}
    /* 섹션별 시그니처 컬러 — 의미별로 구분 */
    .icon-amber  {{ background: linear-gradient(135deg, var(--c-amber-a32),  var(--c-amber-a12));  border-color: var(--c-amber-a45)  !important; }}
    .icon-teal   {{ background: linear-gradient(135deg, var(--c-teal-a32),   var(--c-teal-a12));   border-color: var(--c-teal-a45)   !important; }}
    .icon-indigo {{ background: linear-gradient(135deg, var(--c-indigo-a32), var(--c-indigo-a12)); border-color: var(--c-indigo-a45) !important; }}
    .icon-violet {{ background: linear-gradient(135deg, var(--c-violet-a32), var(--c-violet-a12)); border-color: var(--c-violet-a45) !important; }}
    .icon-cyan   {{ background: linear-gradient(135deg, var(--c-cyan-a32),   var(--c-cyan-a12));   border-color: var(--c-cyan-a45)   !important; }}
    .icon-rose   {{ background: linear-gradient(135deg, var(--c-rose-a32),   var(--c-rose-a12));   border-color: var(--c-rose-a45)   !important; }}
    .title-amber  {{ color: var(--c-amber)  !important; }}
    .title-teal   {{ color: var(--c-teal)   !important; }}
    .title-indigo {{ color: var(--c-indigo) !important; }}
    .title-violet {{ color: var(--c-violet) !important; }}
    .title-cyan   {{ color: var(--c-cyan)   !important; }}
    .title-rose   {{ color: var(--c-rose)   !important; }}
    .section-title {{ font-size: 0.9rem; font-weight: 700; color: {text_sec}; }}

    /* ── 감성 배지 ─────────────────────────────────────────────────── */
    .sentiment-badge {{
        display: inline-flex; align-items: center; gap: 0.3rem;
        padding: 0.15rem 0.55rem;
        border-radius: 20px;
        font-size: 0.68rem;
        font-weight: 700;
    }}
    .sent-pos {{ background: var(--c-green-a15); color: var(--c-green); border: 1px solid var(--c-green-a30); }}
    .sent-neg {{ background: var(--c-red-a15);   color: var(--c-red);   border: 1px solid var(--c-red-a30);   }}
    .sent-neu {{ background: var(--c-yellow-a15); color: #fbbf24;       border: 1px solid var(--c-yellow-a30); }}
    .impact-badge {{
        background: var(--c-blue-a15); color: var(--c-blue);
        border: 1px solid var(--c-blue-a30);
        padding: 0.15rem 0.55rem; border-radius: 20px;
        font-size: 0.68rem; font-weight: 700;
    }}
    .status-row {{ display: flex; flex-direction: column; gap: 0.55rem; }}
    .status-item {{
        display: flex;
        align-items: center;
        gap: 0.7rem;
        background: {status_bg};
        border: 1px solid {status_bdr};
        border-radius: 10px;
        padding: 0.65rem 0.9rem;
    }}
    .status-dot {{ width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }}
    .dot-green  {{ background: #34d399; box-shadow: 0 0 6px rgba(52,211,153,0.6); }}
    .dot-yellow {{ background: #fbbf24; box-shadow: 0 0 6px rgba(251,191,36,0.6); }}
    .dot-red    {{ background: #f87171; box-shadow: 0 0 6px rgba(248,113,113,0.6); }}
    .dot-blue   {{ background: #60a5fa; box-shadow: 0 0 6px rgba(96,165,250,0.5); }}
    .status-text {{ font-size: 0.82rem; color: {text_status}; flex: 1; line-height: 1.4; }}
    .status-text strong {{ color: {text_primary}; }}

    /* ── 뉴스 카드 ─────────────────────────────────────────────────── */
    .news-card {{
        background: {news_bg};
        border: 1px solid {news_bdr};
        border-radius: 14px;
        padding: 1rem 1.1rem;
        margin-bottom: 0.8rem;
        backdrop-filter: blur(8px);
        transition: border-color 0.2s;
    }}
    .news-card:hover {{ border-color: var(--c-violet-bdr); }}
    .pos-card {{ border-left: 3px solid var(--c-green);  background: var(--c-green-a06); }}
    .neg-card {{ border-left: 3px solid var(--c-red);    background: var(--c-red-a06);   }}
    .neu-card {{ border-left: 3px solid #fbbf24;         background: var(--c-yellow-a06); }}
    .news-meta {{ font-size: 0.7rem; color: {text_muted}; margin-bottom: 0.4rem; display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }}
    .news-title {{ font-size: 0.9rem; font-weight: 600; color: {text_primary}; line-height: 1.45; margin-bottom: 0.35rem; }}
    .news-orig  {{ font-size: 0.72rem; color: {text_dimmed}; margin-bottom: 0.5rem; font-style: italic; }}
    .news-link  {{ font-size: 0.78rem; color: #818cf8; text-decoration: none; font-weight: 500; }}
    .news-link:hover {{ color: #a78bfa; }}

    /* ── 소셜 미디어 카드 ─────────────────────────────────────────── */
    .social-card {{
        background: {social_bg};
        border: 1px solid {social_bdr};
        border-radius: 14px;
        padding: 0.95rem 1.1rem;
        margin-bottom: 0.7rem;
        backdrop-filter: blur(8px);
        transition: border-color 0.2s;
    }}
    .social-card:hover {{ border-color: var(--c-cyan-a45); }}
    .social-bull {{ border-left: 3px solid var(--c-green); background: var(--c-green-a05); }}
    .social-bear {{ border-left: 3px solid var(--c-red);   background: var(--c-red-a05);   }}
    .social-meta {{
        display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;
        font-size: 0.7rem; color: {text_muted}; margin-bottom: 0.4rem;
    }}
    .social-body {{ font-size: 0.88rem; color: {text_sec}; line-height: 1.5; margin-bottom: 0.4rem; }}
    .social-stats {{ display: flex; gap: 0.9rem; font-size: 0.72rem; color: {text_dimmed}; }}
    .social-selftext {{
        font-size: 0.82rem; color: {social_selftext_clr};
        line-height: 1.55; margin: 0.3rem 0 0.4rem 0;
        border-left: 2px solid {social_selftext_bdr};
        padding-left: 0.7rem;
    }}
    .bull-badge {{
        background: var(--c-green-a15); color: var(--c-green);
        border: 1px solid var(--c-green-a30);
        padding: 0.12rem 0.5rem; border-radius: 20px; font-size: 0.68rem; font-weight: 700;
    }}
    .bear-badge {{
        background: var(--c-red-a15); color: var(--c-red);
        border: 1px solid var(--c-red-a30);
        padding: 0.12rem 0.5rem; border-radius: 20px; font-size: 0.68rem; font-weight: 700;
    }}
    .platform-badge {{
        background: var(--c-cyan-a12); color: var(--c-cyan);
        border: 1px solid var(--c-cyan-a25);
        padding: 0.12rem 0.5rem; border-radius: 20px; font-size: 0.68rem; font-weight: 700;
    }}
    .reddit-badge {{
        background: var(--c-orange-a12); color: var(--c-orange);
        border: 1px solid var(--c-orange-a25);
        padding: 0.12rem 0.5rem; border-radius: 20px; font-size: 0.68rem; font-weight: 700;
    }}
    .sentiment-bar-wrap {{
        background: {sent_wrap_bg}; border-radius: 10px;
        padding: 0.85rem 1rem; margin-bottom: 0.8rem;
        border: 1px solid {sent_wrap_bdr};
    }}
    .sentiment-bar-track {{
        background: {sent_track}; border-radius: 99px;
        height: 8px; overflow: hidden; margin: 0.4rem 0;
    }}
    .sentiment-bar-fill {{
        height: 100%; border-radius: 99px;
        background: linear-gradient(90deg, #34d399, #fbbf24);
        transition: width 0.6s ease;
    }}

    /* ── 스캔 결과 테이블 ──────────────────────────────────────────── */
    .scan-header {{
        background: linear-gradient(135deg, rgba(245,185,66,0.2), rgba(251,113,133,0.12));
        border: 1px solid rgba(245,185,66,0.35);
        border-radius: 14px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
        display: flex; align-items: center; justify-content: space-between;
    }}
    .scan-title {{ font-size: 0.95rem; font-weight: 700; color: #f5b942; }}

    /* ── 메모 영역 ─────────────────────────────────────────────────── */
    .stTextArea textarea {{
        background: {textarea_bg} !important;
        border: 1px solid rgba(139,92,246,0.3) !important;
        border-radius: 12px !important;
        color: {text_primary} !important;
        font-size: 0.88rem !important;
        resize: vertical;
    }}
    .stTextArea textarea:focus {{
        border-color: rgba(139,92,246,0.6) !important;
        box-shadow: 0 0 0 2px rgba(139,92,246,0.15) !important;
    }}

    /* ── 버튼 (Blobs 목업 스타일: 단색 필 형태 CTA) ───────────────────── */
    .stButton button {{
        background: var(--c-accent) !important;
        border: 1px solid var(--c-accent) !important;
        border-radius: 999px !important;
        color: var(--c-accent-ink) !important;
        font-weight: 700 !important;
        font-size: 0.88rem !important;
        transition: all 0.2s !important;
        min-height: 2.5rem !important;
        box-shadow: 0 2px 10px rgba(245,169,115,0.25) !important;
    }}
    .stButton button:hover {{
        background: var(--c-accent-hov) !important;
        border-color: var(--c-accent-hov) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 16px rgba(245,169,115,0.4) !important;
    }}

    /* ── 탭 (Blobs 목업 스타일: 필터 칩) ──────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {{
        background: {tab_bg} !important;
        border-radius: 999px !important;
        padding: 0.3rem !important;
        gap: 0.3rem !important;
        border: 1px solid {tab_bdr} !important;
    }}
    .stTabs [data-baseweb="tab"] {{
        border-radius: 999px !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        color: {text_muted} !important;
        padding: 0.55rem 1.1rem !important;
    }}
    .stTabs [aria-selected="true"] {{
        background: var(--c-accent) !important;
        color: var(--c-accent-ink) !important;
        border: 1px solid var(--c-accent) !important;
        font-weight: 700 !important;
    }}

    /* ── 세그먼트 컨트롤 (뉴스/소셜/기술분석 전환 — 탭과 동일한 필터 칩 스타일) ── */
    [data-testid="stSegmentedControl"] {{
        background: {tab_bg} !important;
        border-radius: 999px !important;
        padding: 0.3rem !important;
        gap: 0.3rem !important;
        border: 1px solid {tab_bdr} !important;
    }}
    [data-testid="stSegmentedControl"] label,
    [data-testid="stSegmentedControl"] button,
    [data-testid="stSegmentedControl"] div[role="radiogroup"] label,
    [data-testid="stSegmentedControl"] div[data-baseweb="button-group"] > * {{
        border-radius: 999px !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        color: {text_sec} !important;
        background: transparent !important;
        background-color: transparent !important;
        opacity: 1 !important;
    }}
    [data-testid="stSegmentedControl"] label *,
    [data-testid="stSegmentedControl"] button *,
    [data-testid="stSegmentedControl"] label p,
    [data-testid="stSegmentedControl"] button p,
    [data-testid="stSegmentedControl"] [data-testid="stMarkdownContainer"],
    [data-testid="stSegmentedControl"] [data-testid="stMarkdownContainer"] * {{
        color: {text_sec} !important;
        fill: {text_sec} !important;
        opacity: 1 !important;
    }}
    [data-testid="stSegmentedControl"] [aria-checked="true"],
    [data-testid="stSegmentedControl"] [aria-selected="true"] {{
        background: var(--c-accent) !important;
        background-color: var(--c-accent) !important;
        color: var(--c-accent-ink) !important;
        border: 1px solid var(--c-accent) !important;
        font-weight: 700 !important;
    }}
    [data-testid="stSegmentedControl"] [aria-checked="true"] *,
    [data-testid="stSegmentedControl"] [aria-selected="true"] *,
    [data-testid="stSegmentedControl"] [aria-checked="true"] p,
    [data-testid="stSegmentedControl"] [aria-selected="true"] p {{
        color: var(--c-accent-ink) !important;
        fill: var(--c-accent-ink) !important;
    }}

    /* ── 즐겨찾기 리스트: 티커 칩 (은은한 카드, 좌측 정렬) ───────────── */
    [class*="st-key-fav_ticker_"] button {{
        background: {glass_bg} !important;
        border: 1px solid {glass_border} !important;
        color: {text_primary} !important;
        font-weight: 700 !important;
        font-size: 0.85rem !important;
        border-radius: 10px !important;
        box-shadow: none !important;
        justify-content: flex-start !important;
        padding-left: 0.9rem !important;
        min-height: 2.3rem !important;
        transition: all 0.15s !important;
    }}
    [class*="st-key-fav_ticker_"] button:hover {{
        border-color: var(--c-accent) !important;
        color: var(--c-accent) !important;
        background: {glass_bg} !important;
        transform: none !important;
        box-shadow: none !important;
    }}

    /* ── 즐겨찾기 액션 아이콘(▲▼✕): 고스트 스타일로 시각적 무게 축소 ── */
    [class*="st-key-fav_action_"] button {{
        background: transparent !important;
        border: 1px solid {glass_border} !important;
        color: {text_muted} !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
        min-height: 2.3rem !important;
        box-shadow: none !important;
        padding: 0 !important;
    }}
    [class*="st-key-fav_action_"] button:hover:not(:disabled) {{
        border-color: var(--c-accent) !important;
        color: var(--c-accent) !important;
        background: {glass_bg} !important;
        transform: none !important;
        box-shadow: none !important;
    }}
    [class*="st-key-fav_action_"] button:disabled {{
        opacity: 0.3 !important;
    }}

    /* ── 폼 제출 버튼 (사이드바 '실시간 정밀 검증 시작' 등, .stButton과 별도 클래스) ── */
    .stFormSubmitButton button,
    [data-testid="stFormSubmitButton"] button {{
        background: var(--c-accent) !important;
        border: 1px solid var(--c-accent) !important;
        border-radius: 999px !important;
        color: var(--c-accent-ink) !important;
        font-weight: 700 !important;
        font-size: 0.88rem !important;
        transition: all 0.2s !important;
        min-height: 2.5rem !important;
        box-shadow: 0 2px 10px rgba(245,169,115,0.25) !important;
    }}
    .stFormSubmitButton button *,
    [data-testid="stFormSubmitButton"] button * {{
        color: var(--c-accent-ink) !important;
    }}
    .stFormSubmitButton button:hover,
    [data-testid="stFormSubmitButton"] button:hover {{
        background: var(--c-accent-hov) !important;
        border-color: var(--c-accent-hov) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 16px rgba(245,169,115,0.4) !important;
    }}

    /* ── 섹터 히트맵 ───────────────────────────────────────────────── */
    .sector-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
        gap: 0.6rem;
        margin-bottom: 1rem;
    }}
    .sector-cell {{
        border-radius: 12px;
        padding: 0.85rem 0.9rem;
        text-align: center;
        backdrop-filter: blur(8px);
        border: 1px solid rgba(255,255,255,0.1);
        transition: transform 0.15s;
        cursor: default;
    }}
    .sector-cell:hover {{ transform: translateY(-2px); }}
    .sector-name {{ font-size: 0.68rem; font-weight: 700; letter-spacing: 0.6px; text-transform: uppercase; color: {sector_name_clr}; margin-bottom: 0.3rem; }}
    .sector-ticker {{ font-size: 0.62rem; color: {sector_ticker_clr}; margin-bottom: 0.4rem; }}
    .sector-pct {{ font-size: 1.25rem; font-weight: 800; line-height: 1; }}
    .sector-sub {{ font-size: 0.68rem; margin-top: 0.25rem; opacity: 0.7; }}
    .sector-legend {{ display: flex; gap: 1.2rem; align-items: center; flex-wrap: wrap; margin-bottom: 0.9rem; }}
    .legend-item {{ display: flex; align-items: center; gap: 0.35rem; font-size: 0.72rem; color: {text_muted}; }}
    .legend-dot {{ width: 10px; height: 10px; border-radius: 3px; }}

    /* ── 구분선 ────────────────────────────────────────────────────── */
    hr {{ border-color: {hr_color} !important; margin: 1rem 0 !important; }}

    /* ── 모바일 ────────────────────────────────────────────────────── */
    @media (max-width: 640px) {{
        .block-container {{ padding: 0.8rem 0.9rem 2rem !important; }}
        .app-header {{ padding: 1rem 1.1rem; border-radius: 14px; }}
        .app-header h1 {{ font-size: 1rem; }}
        .app-header p {{ font-size: 0.68rem; }}
        .metric-value {{ font-size: 1.25rem; }}
        [data-testid="stMetricValue"] {{ font-size: 1.05rem !important; }}
        [data-testid="stMetricLabel"] {{ font-size: 0.65rem !important; }}
        [data-testid="stMetricDelta"] {{ font-size: 0.65rem !important; }}
        .stButton button {{ min-height: 2.8rem !important; font-size: 0.95rem !important; }}
    }}

    /* ── 라이트 모드: 저대비 텍스트 색상 전면 보정 ──────────────────── *
     * (버그 수정: 기존 코드는 이 블록이 바깥 f-string 안에 중첩된      *
     * "일반 문자열"인데도 중괄호를 {{ }} 로 이중 이스케이프해서       *
     * 실제로는 깨진 CSS( {{ ... }} )가 출력되어 라이트 모드 보정이    *
     * 하나도 적용되지 않고 있었음. 홑 중괄호로 수정 + 저대비 색상     *
     * 전반(회색 노트, 파스텔 강조색 등)에 대한 보정을 추가함.         */
    {"" if dark else """
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
    .alert-title  { color: #b91c1c !important; }
    .signal-chip  { color: #b91c1c !important; }
    .china-banner-text { color: #991b1b !important; }
    .china-banner-sub  { color: #7f1d1d !important; }
    .sent-neu   { color: #92600a !important; }
    .split-banner-title { color: #92600a !important; }
    .news-link  { color: #4338ca !important; }
    .news-link:hover { color: #6d28d9 !important; }
    .scan-title { color: #92600a !important; }
    .status-text { color: #334155 !important; }
    .metric-label, .news-meta, .social-meta, .social-stats,
    .sector-ticker, .legend-item, .news-orig { color: #64748b !important; }

    /* 인라인 style="color:..." 로 하드코딩된 파스텔 색상 보정
       (dark 테마 배경 기준으로 만들어진 값이라 밝은 배경에서 저대비) */
    [style*="color:rgba(148,163,184"], [style*="color: rgba(148,163,184"] { color: #475569 !important; }
    [style*="color:rgba(255,255,255"], [style*="color: rgba(255,255,255"] { color: #334155 !important; }
    [style*="color:rgba(254,202,202"], [style*="color: rgba(254,202,202"] { color: #7f1d1d !important; }
    [style*="color:#34d399"],  [style*="color: #34d399"]  { color: #047857 !important; }
    [style*="color:#6ee7b7"],  [style*="color: #6ee7b7"]  { color: #059669 !important; }
    [style*="color:#a7f3d0"],  [style*="color: #a7f3d0"]  { color: #0d9488 !important; }
    [style*="color:#f87171"],  [style*="color: #f87171"]  { color: #dc2626 !important; }
    [style*="color:#ef4444"],  [style*="color: #ef4444"]  { color: #b91c1c !important; }
    [style*="color:#fca5a5"],  [style*="color: #fca5a5"]  { color: #b91c1c !important; }
    [style*="color:#fecaca"],  [style*="color: #fecaca"]  { color: #991b1b !important; }
    [style*="color:#fbbf24"],  [style*="color: #fbbf24"]  { color: #92600a !important; }
    [style*="color:#f5b942"],  [style*="color: #f5b942"]  { color: #92600a !important; }
    [style*="color:#a78bfa"],  [style*="color: #a78bfa"]  { color: #6d28d9 !important; }
    [style*="color:#818cf8"],  [style*="color: #818cf8"]  { color: #4338ca !important; }
    [style*="color:#60a5fa"],  [style*="color: #60a5fa"]  { color: #1d4ed8 !important; }
    [style*="color:#94a3b8"],  [style*="color: #94a3b8"]  { color: #475569 !important; }
    [style*="color:#ff6a00"],  [style*="color: #ff6a00"]  { color: #c2410c !important; }
    """}
</style>
""", unsafe_allow_html=True)

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
                    vol_ma20   = t['VOL_MA20'] if t['VOL_MA20'] > 0 else 1
                    vol_r      = (t['Volume'] / vol_ma20) * 100
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

# ── 화면 레이아웃 모드 선택 ─────────────────────────────────────
st.sidebar.markdown("---")
desktop_mode = st.sidebar.checkbox(
    "💻 PC 와이드 모드 (좌우 2분할)",
    value=False,
    help="체크 해제 시 폰에 최적화된 탭(Tab) 방식으로 표시됩니다."
)

# ════════════════════════════════════════════════════════════════
# 렌더링 함수 — 상단 주요 지표 요약
# ════════════════════════════════════════════════════════════════
def render_top_summary_metrics(today_data, yesterday_data, df_calculated, score=None):
    """상단 주요 지표 요약 — st.columns 기반 메트릭 스코어보드.
    score가 주어지면 급등주 검색기·즐겨찾기 스캔과 동일 기준의 종합점수를 함께 표시합니다.
    """
    if score is not None:
        m1, m2, m3, m4, m5 = st.columns(5)
    else:
        m1, m2, m3, m4 = st.columns(4)

    # 가격 및 등락률
    price_chg = ((today_data['Close'] - yesterday_data['Close']) / yesterday_data['Close']) * 100
    m1.metric(
        label="현재가 (종가)",
        value=f"${today_data['Close']:.2f}",
        delta=f"{price_chg:+.2f}%"
    )

    # RSI 상태
    current_rsi = df_calculated['RSI'].iloc[-1]
    rsi_status = "과매수" if current_rsi >= 70 else ("과매도" if current_rsi <= 30 else "보통")
    m2.metric(
        label="RSI (14)",
        value=f"{current_rsi:.1f}",
        delta=rsi_status,
        delta_color="normal" if rsi_status == "보통" else "inverse"
    )

    # 당일 거래량
    m3.metric(
        label="당일 거래량",
        value=f"{int(today_data['Volume']):,}주"
    )

    # 전고점 대비 낙폭
    current_dd = df_calculated['Drawdown'].iloc[-1]
    m4.metric(
        label="전고점 대비 낙폭",
        value=f"{current_dd:.1f}%",
        delta="MDD 관리 필요" if current_dd < -20 else None
    )

    if score is not None:
        score_label = "강세" if score >= 70 else ("보통" if score >= 40 else "약세")
        m5.metric(
            label="종합점수",
            value=f"{score:.1f}점",
            delta=score_label,
            delta_color="normal" if score_label != "약세" else "inverse",
            help="등락률·거래량·거래대금·RSI를 종합한 참고 지표 (급등주 검색기·즐겨찾기 스캔과 동일 기준)"
        )

    st.divider()

# ════════════════════════════════════════════════════════════════
# 렌더링 함수 — 기술적 분석
# ════════════════════════════════════════════════════════════════
def render_technical_analysis(ticker_input, hist, today, yesterday, vol_ratio,
                               vol_ma20_ratio, trading_value_krw_eok, threshold_eok,
                               high_52w, low_52w, spike_df=None, offering_list=None,
                               nasdaq_compliance=None):
    """기술적 조건 & 수급 점검 + 차트 (탭1 또는 좌측 컬럼)"""

    # ── 종목 정보 조회 (국적 판별 등에 사용) ─────────────────────
    info = fetch_ticker_info(ticker_input)
    country = str(info.get("country") or "").strip()
    is_china = country in {"China", "Hong Kong"}

    if is_china:
        st.markdown(f"""
        <div class="china-banner">
            <div class="china-banner-icon">🇨🇳⚠️</div>
            <div>
                <div class="china-banner-text">중국 기업 (China-based Company)</div>
                <div class="china-banner-sub">본사 소재지: {country} — VIE 구조, 회계 투명성, 규제 리스크 등을 반드시 확인하세요</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

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

    if alert_signals:
        chips = "".join([f'<span class="signal-chip">{s}</span>' for s in alert_signals])
        st.markdown(f"""
        <div class="alert-banner">
            <div class="alert-icon">🔔</div>
            <div>
                <div class="alert-title">급등 신호 감지!</div>
                <div class="alert-signals">{chips}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ── 메트릭 카드 2x2 ─────────────────────────────────────────
    pct_color = "delta-up" if pct_chg >= 0 else "delta-down"
    pct_arrow = "▲" if pct_chg >= 0 else "▼"

    # #7 52주 최저가 추가
    gap_52w_high = ((high_52w - today['Close']) / high_52w) * 100
    gap_52w_low  = ((today['Close'] - low_52w) / low_52w) * 100

    rsi_label = "과매수 ⚠️" if rsi_val >= 70 else ("과매도 💡" if rsi_val <= 30 else "중립 ✓")
    rsi_color = "delta-down" if rsi_val >= 70 else ("delta-up" if rsi_val <= 30 else "delta-neu")

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

    mc_star_html     = ' <span style="color:#f5b942;font-size:1rem;vertical-align:middle;" title="소형주 최적 구간 ($4M~$500M)">⭐</span>' if mc_star else ""
    shares_star_html = ' <span style="color:#f5b942;font-size:1rem;vertical-align:middle;" title="저부동주 조건 (20M주 이하)">⭐</span>' if shares_star else ""

    st.markdown(f"""
    <div class="metric-grid">
        <div class="metric-card mc-amber">
            <div class="metric-label">현재가</div>
            <div class="metric-value">${today['Close']:.2f}</div>
            <div class="metric-delta {pct_color}">{pct_arrow} {abs(pct_chg):.2f}%</div>
        </div>
        <div class="metric-card mc-violet">
            <div class="metric-label">RSI (14)</div>
            <div class="metric-value">{rsi_val:.1f}</div>
            <div class="metric-delta {rsi_color}">{rsi_label}</div>
        </div>
        <div class="metric-card mc-rose">
            <div class="metric-label">52주 최고가</div>
            <div class="metric-value">${high_52w:.2f}</div>
            <div class="metric-delta delta-neu">↓ {gap_52w_high:.1f}% 하단</div>
        </div>
        <div class="metric-card mc-cyan">
            <div class="metric-label">52주 최저가</div>
            <div class="metric-value">${low_52w:.2f}</div>
            <div class="metric-delta delta-up">↑ {gap_52w_low:.1f}% 상단</div>
        </div>
    </div>
    <div class="metric-grid" style="margin-top:-0.25rem;">
        <div class="metric-card mc-indigo">
            <div class="metric-label">시가총액</div>
            <div class="metric-value" style="font-size:1.2rem;">{market_cap_str}{mc_star_html}</div>
            <div class="metric-delta {"delta-up" if mc_star else "delta-neu"}">{"$4M~$500M 최적 구간 ✓" if mc_star else "Market Cap"}</div>
        </div>
        <div class="metric-card mc-teal">
            <div class="metric-label">거래량 (MA20 대비)</div>
            <div class="metric-value">{vol_ma20_ratio:.0f}%</div>
            <div class="metric-delta {"delta-up" if vol_ma20_ratio >= 200 else "delta-neu"}">
                {"🔥 폭증" if vol_ma20_ratio >= 200 else ("보통" if vol_ma20_ratio >= 80 else "저조")}
            </div>
        </div>
    </div>
    <div class="metric-grid" style="margin-top:-0.25rem;">
        <div class="metric-card mc-rose" style="grid-column: span 2;">
            <div class="metric-label">유통주식수 (Float Shares)</div>
            <div class="metric-value" style="font-size:1.2rem;">{shares_str}{shares_star_html}</div>
            <div class="metric-delta {"delta-up" if shares_star else "delta-neu"}">{"20M주 이하 저부동주 ✓" if shares_star else "Float Shares"}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

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

    # ── 🧱 악성매물대 분석 ───────────────────────────────────────
    supply_data = calc_supply_zones(hist, float(today['Close']))
    render_supply_zones(float(today['Close']), supply_data)

    # ── 🚀 100%+ 급등 이력 ───────────────────────────────────────
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

    # ── 📜 오퍼링(유상증자) 이력 ─────────────────────────────────
    ui_section_header(mono_icon_badge("doc", color="var(--c-amber)"), "오퍼링(유상증자) 관련 공시 이력", "icon-amber", "title-amber")
    if offering_list:
        rows_html = ""
        for o in offering_list[:15]:
            link_html = f"<a class='news-link' href='{o['url']}' target='_blank'>공시 원문 →</a>" if o.get("url") else ""
            rows_html += (
                f"<div class='status-item'><div class='status-dot dot-yellow'></div>"
                f"<div class='status-text'>📅 {o['date']} &nbsp;<strong>{o['type']}</strong> — {o['title']} {link_html}</div></div>"
            )
        more_note = (f"<div style='font-size:0.7rem;color:rgba(148,163,184,0.55);margin-top:0.35rem;'>"
                      f"총 {len(offering_list)}건 중 최근 15건 표시</div>" if len(offering_list) > 15 else "")
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

    # ── 수급 체크 ────────────────────────────────────────────────
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

    # ── 이동평균선 배열 ──────────────────────────────────────────
    ui_section_header(mono_icon_badge("trend", color="var(--c-teal)"), "이동평균선 배열", "icon-teal", "title-teal")

    if today['MA5'] > today['MA20'] > today['MA120']:
        ma_dot, ma_text = "dot-green", "<strong>완전 정배열</strong> — 강력한 상승 추세 유지 중"
    elif today['Close'] > today['MA120'] and yesterday['Close'] <= yesterday['MA120']:
        ma_dot, ma_text = "dot-green", "<strong>120일선 돌파!</strong> — 급등 초입 타점"
    else:
        ma_dot, ma_text = "dot-blue", f"이평선 밀집 — 에너지 응축 횡보 구간 &nbsp;|&nbsp; MA5 <strong>${today['MA5']:.1f}</strong> / MA20 <strong>${today['MA20']:.1f}</strong>"

    # ── RSI ──────────────────────────────────────────────────────
    if rsi_val >= 70:
        rsi_dot, rsi_txt = "dot-yellow", f"<strong>RSI {rsi_val:.1f} — 과매수</strong> 단기 조정 가능성 주의"
    elif rsi_val <= 30:
        rsi_dot, rsi_txt = "dot-green",  f"<strong>RSI {rsi_val:.1f} — 과매도</strong> 반등 매수 타점"
    else:
        rsi_dot, rsi_txt = "dot-blue",   f"RSI <strong>{rsi_val:.1f}</strong> — 중립 구간 (30~70)"

    # ── 볼린저밴드 ───────────────────────────────────────────────
    bb_range = today['BB_UPPER'] - today['BB_LOWER']
    bb_pct   = (today['Close'] - today['BB_LOWER']) / bb_range * 100 if bb_range else 50
    if today['Close'] >= today['BB_UPPER']:
        bb_dot, bb_txt = "dot-yellow", f"<strong>볼린저 상단 터치 ({bb_pct:.0f}%)</strong> — 과열 구간"
    elif today['Close'] <= today['BB_LOWER']:
        bb_dot, bb_txt = "dot-green",  f"<strong>볼린저 하단 터치 ({bb_pct:.0f}%)</strong> — 반등 구간"
    else:
        bb_dot, bb_txt = "dot-blue",   f"밴드 내부 <strong>{bb_pct:.0f}%</strong> 위치 &nbsp;|&nbsp; 밴드폭 {today['BB_WIDTH']:.1f}%"

    # ── MACD ─────────────────────────────────────────────────────
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

    news_data = get_stock_titan_data(ticker_input)

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
        raw_news_list = fetch_yahoo_news(ticker_input)[:5]
        parsed_list   = [parse_yahoo_news_item(r) for r in raw_news_list]
        titles_en     = [n["title"] for n in parsed_list]

        def _translate(t): return translate_text(t)
        with ThreadPoolExecutor(max_workers=5) as ex:
            translated = list(ex.map(_translate, titles_en))

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
        with ThreadPoolExecutor(max_workers=5) as _prefetch_ex:
            _fut_hist     = _prefetch_ex.submit(fetch_history, active_ticker)
            _fut_spike    = _prefetch_ex.submit(fetch_spike_history, active_ticker)
            _fut_offering = _prefetch_ex.submit(fetch_offering_history, active_ticker)
            _fut_info     = _prefetch_ex.submit(fetch_ticker_info, active_ticker)
            _fut_fx       = _prefetch_ex.submit(fetch_usd_to_krw)

            hist          = _fut_hist.result()
            spike_df      = _fut_spike.result()
            offering_list = _fut_offering.result()
            _fut_info.result()   # 캐시 예열 목적 — 결과는 render_technical_analysis에서 재조회
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
            vol_ma20_ratio = (today['Volume'] / vol_ma20) * 100   # #8

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

            render_top_summary_metrics(today, yesterday, hist, score=ticker_score)

            if desktop_mode:
                col1, col2 = st.columns([4, 5])
                with col1:
                    render_technical_analysis(
                        active_ticker, hist, today, yesterday,
                        vol_ratio, vol_ma20_ratio,
                        trading_value_krw_eok, TRADING_THRESHOLD,
                        high_52w, low_52w,
                        spike_df, offering_list, nasdaq_compliance
                    )
                with col2:
                    # #성능 st.tabs는 선택 안 된 탭도 매번 내부 코드를 전부 실행해
                    # 안 보는 탭의 뉴스/소셜 API까지 계속 호출되는 문제가 있었음.
                    # segmented_control은 선택된 값만 알려주므로, 선택된 섹션만 조건부로
                    # 렌더링(=API 호출)하도록 바꿔 불필요한 네트워크 호출을 없앰.
                    desktop_view = st.segmented_control(
                        "정보 보기",
                        ["📰 뉴스 & 호재", "💬 소셜 미디어"],
                        default="📰 뉴스 & 호재",
                        required=True,
                        key="desktop_info_view",
                        label_visibility="collapsed",
                    )
                    if desktop_view == "📰 뉴스 & 호재":
                        render_news_section(active_ticker)
                    else:
                        render_social_section(active_ticker)
            else:
                mobile_view = st.segmented_control(
                    "보기 선택",
                    ["📊 기술 분석", "📰 뉴스 & 호재", "💬 소셜 미디어"],
                    default="📊 기술 분석",
                    required=True,
                    key="mobile_info_view",
                    label_visibility="collapsed",
                )
                if mobile_view == "📊 기술 분석":
                    render_technical_analysis(
                        active_ticker, hist, today, yesterday,
                        vol_ratio, vol_ma20_ratio,
                        trading_value_krw_eok, TRADING_THRESHOLD,
                        high_52w, low_52w,
                        spike_df, offering_list, nasdaq_compliance
                    )
                elif mobile_view == "📰 뉴스 & 호재":
                    render_news_section(active_ticker)
                else:
                    render_social_section(active_ticker)