import json
import os
import random
import re
import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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
# 1. 페이지 설정 — set_page_config는 반드시 가장 먼저
# ════════════════════════════════════════════════════════════════
st.set_page_config(page_title="급등주 실시간 검증기 V3", layout="wide", initial_sidebar_state="auto")

# ════════════════════════════════════════════════════════════════
# #1 session_state 초기화 — 단일 위치, 중복 제거
# ════════════════════════════════════════════════════════════════
_defaults = {
    "favorites":        [],
    "selected_ticker":  "NVDA",
    "memos":            load_memos(),   # #9 파일에서 복원
    "scan_results":     [],
    "chart_period":     "2개월",        # 기술적 차트 기간 유지
    "show_heatmap":     False,          # 섹터 히트맵 토글 (사이드바 버튼보다 먼저 초기화)
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

@st.cache_data(ttl=300, show_spinner=False)
def fetch_yahoo_news(ticker: str) -> list:
    """yfinance 뉴스 목록 캐싱 — #14 try/except 추가"""
    try:
        return yf.Ticker(ticker).news or []
    except Exception:
        return []

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

    return df

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

def _fetch_detail(link: str, headers: dict):
    """상세 페이지에서 감성·임팩트를 병렬로 가져오는 내부 함수"""
    sentiment, impact = "Unknown", "Normal"
    try:
        detail_resp = requests.get(link, headers=headers, timeout=5)
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

def get_stock_titan_data(ticker: str) -> list:
    url     = f"https://www.stocktitan.net/overview/{ticker}/"
    headers = _random_headers()   # #13

    try:
        response = requests.get(url, headers=headers, timeout=8)
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

            # #4 날짜 파싱 시도 — 부모 태그에서 날짜 요소 탐색
            date_str = "날짜 미확인"
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
                        # ISO 형식 파싱 시도
                        dt = datetime.fromisoformat(raw_date[:19])
                        date_str = dt.strftime("%b %d, %Y")
                    except Exception:
                        date_str = raw_date[:20] if raw_date else "날짜 미확인"
                    break
                parent = parent.parent

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
# CSS
# ════════════════════════════════════════════════════════════════
st.markdown("""
<style>
    /* ── 폰트 임포트 ──────────────────────────────────────────────── *
     * 디스플레이: Space Grotesk (헤딩 — 개성)                         *
     * 본문: Inter (가독성)                                            *
     * 데이터: JetBrains Mono (가격/티커/지표 — 자릿수 정렬되는 단말기 느낌) */
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700;800&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600;700&display=swap');

    :root {
        --font-display: 'Space Grotesk', 'Segoe UI', sans-serif;
        --font-body:    'Inter', 'Segoe UI', system-ui, sans-serif;
        --font-mono:    'JetBrains Mono', 'Consolas', monospace;
        /* 섹션별 시그니처 컬러 — 보라/파랑/초록 단일톤 대신 의미별로 분리 */
        --c-amber:  #f5b942;   /* 자금/즐겨찾기 */
        --c-teal:   #2dd4bf;   /* 이동평균 */
        --c-indigo: #6366f1;   /* 차트/기술분석 */
        --c-violet: #a78bfa;   /* 메모 */
        --c-cyan:   #38bdf8;   /* 섹터 히트맵 */
        --c-rose:   #fb7185;   /* 뉴스 */
    }

    /* ── 전역 배경 & 폰트 ─────────────────────────────────────────── */
    html, body, [data-testid="stAppViewContainer"] {
        background: linear-gradient(135deg, #0a0a1a 0%, #0d0d2b 40%, #0a1628 100%) !important;
        font-family: var(--font-body);
    }
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
        background: linear-gradient(180deg, #0d0d2b 0%, #0a1628 100%) !important;
        border-right: 1px solid rgba(139, 92, 246, 0.2);
    }
    [data-testid="stSidebar"] .stTextInput input {
        background: rgba(255,255,255,0.05) !important;
        border: 1px solid rgba(139,92,246,0.4) !important;
        border-radius: 10px !important;
        color: #e2e8f0 !important;
        font-family: var(--font-mono) !important;
        font-size: 1rem !important;
        letter-spacing: 0.5px !important;
        padding: 0.6rem 0.8rem !important;
    }

    /* ── 헤더 배너 ─────────────────────────────────────────────────── */
    .app-header {
        background: linear-gradient(135deg, rgba(245,185,66,0.18) 0%, rgba(251,113,133,0.16) 45%, rgba(99,102,241,0.2) 100%);
        border: 1px solid rgba(245,185,66,0.3);
        border-radius: 18px;
        padding: 1.4rem 1.8rem;
        margin-bottom: 1.4rem;
        backdrop-filter: blur(12px);
        box-shadow: 0 8px 32px rgba(99,102,241,0.15), inset 0 1px 0 rgba(255,255,255,0.08);
    }
    .app-header h1 {
        margin: 0 0 0.2rem 0;
        font-size: 1.55rem;
        font-weight: 800;
        background: linear-gradient(90deg, #f5b942, #fb7185, #818cf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        letter-spacing: -0.3px;
    }
    .app-header p {
        margin: 0;
        color: rgba(148,163,184,0.85);
        font-size: 0.82rem;
    }

    /* ── 글래스 카드 공통 ──────────────────────────────────────────── */
    .glass-card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.09);
        border-radius: 14px;
        padding: 1.1rem 1.2rem;
        margin-bottom: 1rem;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 20px rgba(0,0,0,0.25);
    }
    .glass-card-title {
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 1.2px;
        text-transform: uppercase;
        color: rgba(148,163,184,0.7);
        margin-bottom: 0.6rem;
    }

    /* ── 메트릭 카드 ──────────────────────────────────────────────── */
    .metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-bottom: 1rem; }
    .metric-card {
        background: rgba(255,255,255,0.045);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 14px;
        padding: 1rem 1.1rem;
        backdrop-filter: blur(8px);
        box-shadow: 0 2px 12px rgba(0,0,0,0.2);
        transition: transform 0.15s;
    }
    .metric-card:hover { transform: translateY(-2px); }
    .metric-card { border-left: 3px solid transparent; }
    .mc-amber  { border-left-color: rgba(245,185,66,0.65) !important; }
    .mc-violet { border-left-color: rgba(167,139,250,0.65) !important; }
    .mc-rose   { border-left-color: rgba(251,113,133,0.65) !important; }
    .mc-cyan   { border-left-color: rgba(56,189,248,0.65) !important; }
    .mc-indigo { border-left-color: rgba(99,102,241,0.65) !important; }
    .mc-teal   { border-left-color: rgba(45,212,191,0.65) !important; }
    .metric-label { font-size: 0.7rem; color: rgba(148,163,184,0.7); font-weight: 600; letter-spacing: 0.8px; text-transform: uppercase; margin-bottom: 0.35rem; }
    .metric-value { font-size: 1.45rem; font-weight: 800; color: #f1f5f9; line-height: 1; }
    .metric-delta { font-size: 0.78rem; font-weight: 600; margin-top: 0.3rem; }
    .delta-up   { color: #34d399; }
    .delta-down { color: #f87171; }
    .delta-neu  { color: #94a3b8; }

    /* ── 신호 알림 배너 ────────────────────────────────────────────── */
    .alert-banner {
        background: linear-gradient(135deg, rgba(239,68,68,0.18), rgba(245,158,11,0.12));
        border: 1px solid rgba(239,68,68,0.45);
        border-radius: 14px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
        display: flex;
        align-items: flex-start;
        gap: 0.7rem;
        box-shadow: 0 0 20px rgba(239,68,68,0.12);
    }
    .alert-icon { font-size: 1.4rem; line-height: 1; }
    .alert-title { font-size: 0.72rem; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; color: #fca5a5; margin-bottom: 0.3rem; }
    .alert-signals { display: flex; flex-wrap: wrap; gap: 0.4rem; }
    .signal-chip {
        background: rgba(239,68,68,0.2);
        border: 1px solid rgba(239,68,68,0.35);
        border-radius: 20px;
        padding: 0.2rem 0.7rem;
        font-size: 0.75rem;
        font-weight: 600;
        color: #fca5a5;
    }

    /* ── 섹션 헤더 ─────────────────────────────────────────────────── */
    .section-header {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin: 1.3rem 0 0.7rem 0;
    }
    .section-icon {
        width: 28px; height: 28px;
        background: linear-gradient(135deg, rgba(139,92,246,0.3), rgba(59,130,246,0.2));
        border: 1px solid rgba(139,92,246,0.35);
        border-radius: 8px;
        display: flex; align-items: center; justify-content: center;
        font-size: 0.85rem;
    }
    /* 섹션별 시그니처 컬러 — 모든 섹션이 같은 보라톤이 아니라 의미로 구분됨 */
    .icon-amber  { background: linear-gradient(135deg, rgba(245,185,66,0.32), rgba(245,185,66,0.12)); border-color: rgba(245,185,66,0.45) !important; }
    .icon-teal   { background: linear-gradient(135deg, rgba(45,212,191,0.32), rgba(45,212,191,0.12)); border-color: rgba(45,212,191,0.45) !important; }
    .icon-indigo { background: linear-gradient(135deg, rgba(99,102,241,0.32), rgba(99,102,241,0.12)); border-color: rgba(99,102,241,0.45) !important; }
    .icon-violet { background: linear-gradient(135deg, rgba(167,139,250,0.32), rgba(167,139,250,0.12)); border-color: rgba(167,139,250,0.45) !important; }
    .icon-cyan   { background: linear-gradient(135deg, rgba(56,189,248,0.32), rgba(56,189,248,0.12)); border-color: rgba(56,189,248,0.45) !important; }
    .icon-rose   { background: linear-gradient(135deg, rgba(251,113,133,0.32), rgba(251,113,133,0.12)); border-color: rgba(251,113,133,0.45) !important; }
    .title-amber  { color: #f5b942 !important; }
    .title-teal   { color: #2dd4bf !important; }
    .title-indigo { color: #818cf8 !important; }
    .title-violet { color: #c4b5fd !important; }
    .title-cyan   { color: #38bdf8 !important; }
    .title-rose   { color: #fb7185 !important; }
    .section-title { font-size: 0.9rem; font-weight: 700; color: #e2e8f0; }

    /* ── 상태 배지 ─────────────────────────────────────────────────── */
    .status-row { display: flex; flex-direction: column; gap: 0.55rem; }
    .status-item {
        display: flex;
        align-items: center;
        gap: 0.7rem;
        background: rgba(255,255,255,0.035);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 10px;
        padding: 0.65rem 0.9rem;
    }
    .status-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
    .dot-green  { background: #34d399; box-shadow: 0 0 6px rgba(52,211,153,0.6); }
    .dot-yellow { background: #fbbf24; box-shadow: 0 0 6px rgba(251,191,36,0.6); }
    .dot-red    { background: #f87171; box-shadow: 0 0 6px rgba(248,113,113,0.6); }
    .dot-blue   { background: #60a5fa; box-shadow: 0 0 6px rgba(96,165,250,0.5); }
    .status-text { font-size: 0.82rem; color: #cbd5e1; flex: 1; line-height: 1.4; }
    .status-text strong { color: #f1f5f9; }

    /* ── 뉴스 카드 ─────────────────────────────────────────────────── */
    .news-card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.09);
        border-radius: 14px;
        padding: 1rem 1.1rem;
        margin-bottom: 0.8rem;
        backdrop-filter: blur(8px);
        transition: border-color 0.2s;
    }
    .news-card:hover { border-color: rgba(139,92,246,0.35); }
    .pos-card { border-left: 3px solid #34d399; background: rgba(52,211,153,0.06); }
    .neg-card { border-left: 3px solid #f87171; background: rgba(248,113,113,0.06); }
    .neu-card { border-left: 3px solid #fbbf24; background: rgba(251,191,36,0.06); }
    .news-meta { font-size: 0.7rem; color: rgba(148,163,184,0.7); margin-bottom: 0.4rem; display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
    .news-title { font-size: 0.9rem; font-weight: 600; color: #f1f5f9; line-height: 1.45; margin-bottom: 0.35rem; }
    .news-orig  { font-size: 0.72rem; color: rgba(148,163,184,0.55); margin-bottom: 0.5rem; font-style: italic; }
    .news-link  { font-size: 0.78rem; color: #818cf8; text-decoration: none; font-weight: 500; }
    .news-link:hover { color: #a78bfa; }
    .sentiment-badge {
        display: inline-flex; align-items: center; gap: 0.3rem;
        padding: 0.15rem 0.55rem;
        border-radius: 20px;
        font-size: 0.68rem;
        font-weight: 700;
    }
    .sent-pos { background: rgba(52,211,153,0.15); color: #34d399; border: 1px solid rgba(52,211,153,0.3); }
    .sent-neg { background: rgba(248,113,113,0.15); color: #f87171; border: 1px solid rgba(248,113,113,0.3); }
    .sent-neu { background: rgba(251,191,36,0.15);  color: #fbbf24; border: 1px solid rgba(251,191,36,0.3); }
    .impact-badge {
        background: rgba(96,165,250,0.15); color: #60a5fa;
        border: 1px solid rgba(96,165,250,0.3);
        padding: 0.15rem 0.55rem; border-radius: 20px;
        font-size: 0.68rem; font-weight: 700;
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
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid rgba(139,92,246,0.3) !important;
        border-radius: 12px !important;
        color: #e2e8f0 !important;
        font-size: 0.88rem !important;
        resize: vertical;
    }
    .stTextArea textarea:focus {
        border-color: rgba(139,92,246,0.6) !important;
        box-shadow: 0 0 0 2px rgba(139,92,246,0.15) !important;
    }

    /* ── 버튼 ──────────────────────────────────────────────────────── */
    .stButton button {
        background: linear-gradient(135deg, rgba(139,92,246,0.25), rgba(59,130,246,0.2)) !important;
        border: 1px solid rgba(139,92,246,0.4) !important;
        border-radius: 10px !important;
        color: #e2e8f0 !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        transition: all 0.2s !important;
        min-height: 2.5rem !important;
    }
    .stButton button:hover {
        background: linear-gradient(135deg, rgba(139,92,246,0.4), rgba(59,130,246,0.3)) !important;
        border-color: rgba(139,92,246,0.65) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 15px rgba(139,92,246,0.25) !important;
    }

    /* ── 탭 ────────────────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {
        background: rgba(255,255,255,0.04) !important;
        border-radius: 12px !important;
        padding: 0.3rem !important;
        gap: 0.3rem !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 9px !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        color: rgba(148,163,184,0.8) !important;
        padding: 0.55rem 1.1rem !important;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, rgba(139,92,246,0.35), rgba(59,130,246,0.25)) !important;
        color: #e2e8f0 !important;
        border: 1px solid rgba(139,92,246,0.4) !important;
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
    .sector-name { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.6px; text-transform: uppercase; color: rgba(255,255,255,0.7); margin-bottom: 0.3rem; }
    .sector-ticker { font-size: 0.62rem; color: rgba(255,255,255,0.4); margin-bottom: 0.4rem; }
    .sector-pct { font-size: 1.25rem; font-weight: 800; line-height: 1; }
    .sector-sub { font-size: 0.68rem; margin-top: 0.25rem; opacity: 0.7; }
    .sector-legend { display: flex; gap: 1.2rem; align-items: center; flex-wrap: wrap; margin-bottom: 0.9rem; }
    .legend-item { display: flex; align-items: center; gap: 0.35rem; font-size: 0.72rem; color: rgba(148,163,184,0.8); }
    .legend-dot { width: 10px; height: 10px; border-radius: 3px; }

    /* ── 구분선 ────────────────────────────────────────────────────── */
    hr { border-color: rgba(255,255,255,0.07) !important; margin: 1rem 0 !important; }

    /* ── 모바일 ────────────────────────────────────────────────────── */
    @media (max-width: 640px) {
        .block-container { padding: 0.8rem 0.9rem 2rem !important; }
        .app-header { padding: 1rem 1.1rem; border-radius: 14px; }
        .app-header h1 { font-size: 1.2rem; }
        .metric-value { font-size: 1.25rem; }
        .stButton button { min-height: 2.8rem !important; font-size: 0.95rem !important; }
    }
</style>
""", unsafe_allow_html=True)

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

ticker_input = st.sidebar.text_input(
    "티커명을 입력하세요 (예: NVDA, AAPL)",
    value=st.session_state.selected_ticker
).upper()

col_btn, col_star = st.sidebar.columns([3, 1])
with col_btn:
    search_button = st.button("실시간 정밀 검증 시작", use_container_width=True)
with col_star:
    is_fav = ticker_input in st.session_state.favorites
    if st.button("★" if is_fav else "☆", use_container_width=True, help="즐겨찾기 추가/제거"):
        if is_fav:
            st.session_state.favorites.remove(ticker_input)
        else:
            if ticker_input and ticker_input not in st.session_state.favorites:
                st.session_state.favorites.append(ticker_input)
        st.rerun()

# ── 즐겨찾기 목록 ────────────────────────────────────────────────
if st.session_state.favorites:
    st.sidebar.markdown("---")
    st.sidebar.markdown("**⭐ 즐겨찾기**")
    for fav in st.session_state.favorites:
        fav_col, del_col = st.sidebar.columns([4, 1])
        with fav_col:
            if st.button(fav, key=f"fav_{fav}", use_container_width=True):
                st.session_state.selected_ticker = fav
                st.rerun()
        with del_col:
            if st.button("✕", key=f"del_{fav}", use_container_width=True, help=f"{fav} 삭제"):
                st.session_state.favorites.remove(fav)
                st.rerun()

    # #5 즐겨찾기 일괄 스캔 — ThreadPoolExecutor로 병렬화
    st.sidebar.markdown("")
    if st.sidebar.button("🔍 즐겨찾기 전체 스캔", use_container_width=True,
                         help="즐겨찾기 종목을 한 번에 분석합니다"):
        scan_data  = []
        total      = len(st.session_state.favorites)
        progress   = st.sidebar.progress(0, text="스캔 중...")
        done_count = [0]   # 리스트로 감싸 클로저에서 변경 가능하게

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
                    rsi        = t['RSI']
                    macd_cross = t['MACD'] > t['MACD_SIG'] and y['MACD'] <= y['MACD_SIG']

                    signals = []
                    if vol_r  >= 200:  signals.append("🔥거래량")   # MA20 대비 200%+
                    if macd_cross:     signals.append("⚡MACD")
                    if rsi    <= 35:   signals.append("📉과매도")
                    if t['Close'] > t['MA120'] and y['Close'] <= y['MA120']:
                                       signals.append("🚀120일선")
                    alert = " ".join(signals) if signals else "—"

                    return {
                        "티커":      fav_ticker,
                        "현재가":    f"${t['Close']:.2f}",
                        "등락(%)":   f"{pct:+.2f}%",
                        "거래량(MA비%)": f"{vol_r:.0f}%",
                        "RSI":       f"{rsi:.1f}",
                        "🔔신호":    alert,
                    }
            except Exception:
                pass
            return {"티커": fav_ticker, "현재가": "오류", "등락(%)": "-",
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

# ── 섹터 히트맵 버튼 ─────────────────────────────────────────────
st.sidebar.markdown("---")
show_heatmap = st.sidebar.button(
    "📊 S&P 500 섹터 히트맵",
    use_container_width=True,
    help="11개 섹터 ETF의 당일/1주/1개월 성과를 히트맵으로 표시합니다"
)
if show_heatmap:
    st.session_state["show_heatmap"] = not st.session_state["show_heatmap"]

# ════════════════════════════════════════════════════════════════
# 렌더링 함수 — 기술적 분석
# ════════════════════════════════════════════════════════════════
def render_technical_analysis(ticker_input, hist, today, yesterday, vol_ratio,
                               vol_ma20_ratio, trading_value_krw_eok, threshold_eok,
                               high_52w, low_52w):
    """기술적 조건 & 수급 점검 + 차트 (탭1 또는 좌측 컬럼)"""

    # ── 변수 계산 ────────────────────────────────────────────────
    pct_chg      = (today['Close'] - yesterday['Close']) / yesterday['Close'] * 100
    rsi_val      = today['RSI']
    macd_val     = today['MACD']
    macd_sig_val = today['MACD_SIG']
    macd_cross   = macd_val > macd_sig_val and yesterday['MACD'] <= yesterday['MACD_SIG']
    macd_dead    = macd_val < macd_sig_val and yesterday['MACD'] >= yesterday['MACD_SIG']

    # ── 🔔 급등 신호 배너 ────────────────────────────────────────
    alert_signals = []
    if vol_ma20_ratio >= 200:    alert_signals.append(f"🔥 거래량 MA20 대비 {vol_ma20_ratio:.0f}%")
    if macd_cross:               alert_signals.append("⚡ MACD 골든크로스")
    if rsi_val <= 35:            alert_signals.append("📉 RSI 과매도")
    if today['Close'] > today['MA120'] and yesterday['Close'] <= yesterday['MA120']:
                                  alert_signals.append("🚀 120일선 돌파")
    if pct_chg >= 5:             alert_signals.append(f"📈 당일 +{pct_chg:.1f}%")

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
    macd_label = "골든크로스 🟢" if macd_cross else ("데드크로스 🔴" if macd_dead else ("상승" if macd_val > macd_sig_val else "하락"))
    macd_color = "delta-up" if (macd_cross or macd_val > macd_sig_val) else "delta-down"

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
            <div class="metric-label">MACD</div>
            <div class="metric-value">{macd_val:.3f}</div>
            <div class="metric-delta {macd_color}">{macd_label}</div>
        </div>
        <div class="metric-card mc-teal">
            <div class="metric-label">거래량 (MA20 대비)</div>
            <div class="metric-value">{vol_ma20_ratio:.0f}%</div>
            <div class="metric-delta {'delta-up' if vol_ma20_ratio >= 200 else 'delta-neu'}">
                {'🔥 폭증' if vol_ma20_ratio >= 200 else ('보통' if vol_ma20_ratio >= 80 else '저조')}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 수급 체크 ────────────────────────────────────────────────
    st.markdown("""<div class="section-header"><div class="section-icon icon-amber">💡</div><div class="section-title title-amber">실시간 자금 유입 체크</div></div>""", unsafe_allow_html=True)

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
    st.markdown("""<div class="section-header"><div class="section-icon icon-teal">📈</div><div class="section-title title-teal">이동평균선 배열</div></div>""", unsafe_allow_html=True)

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

    # ── #11 차트 기간 선택 ────────────────────────────────────────
    period_map   = {"1개월": 30, "2개월": 60, "3개월": 90, "6개월": 180, "1년": 252}
    period_keys  = list(period_map.keys())

    # #15 key="chart_period"는 이미 session_state 기본값("2개월")을 가지고 있으므로
    # index를 함께 넘기면 "default value + Session State" 충돌 오류가 날 수 있음.
    # key만으로도 이전 선택값이 자동 복원되므로 index는 제거.
    selected_period = st.radio(
        "차트 기간",
        period_keys,
        horizontal=True,
        key="chart_period",           # 전역 key — 리렌더링 후에도 자동 유지
        label_visibility="collapsed",
    )
    n_days  = period_map[selected_period]
    plot_df = hist.tail(n_days)

    st.markdown(f"""<div class="section-header"><div class="section-icon icon-indigo">📊</div><div class="section-title title-indigo">기술적 차트 ({selected_period})</div></div>""", unsafe_allow_html=True)

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.55, 0.22, 0.23],
        vertical_spacing=0.03,
    )

    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['BB_UPPER'], name='BB 상단',
        line=dict(color='rgba(139,92,246,0.4)', width=1, dash='dot'), showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['BB_LOWER'], name='BB 하단',
        line=dict(color='rgba(139,92,246,0.4)', width=1, dash='dot'),
        fill='tonexty', fillcolor='rgba(139,92,246,0.05)', showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['BB_MID'], name='BB 중심(20일)',
        line=dict(color='rgba(139,92,246,0.6)', width=1, dash='dash')), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Close'], name='주가',
        line=dict(color='#60a5fa', width=2.2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], name='MA20',
        line=dict(color='#fbbf24', width=1.3)), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA120'], name='MA120',
        line=dict(color='#f87171', width=1.3)), row=1, col=1)

    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['RSI'], name='RSI',
        line=dict(color='#a78bfa', width=1.5)), row=2, col=1)
    fig.add_hline(y=70, line_color='rgba(248,113,113,0.5)', line_dash='dot', line_width=1, row=2, col=1)
    fig.add_hline(y=30, line_color='rgba(52,211,153,0.5)', line_dash='dot', line_width=1, row=2, col=1)

    colors = ['#34d399' if v >= 0 else '#f87171' for v in plot_df['MACD_HIST']]
    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['MACD_HIST'], name='MACD Hist',
        marker_color=colors, opacity=0.6), row=3, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MACD'], name='MACD',
        line=dict(color='#60a5fa', width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MACD_SIG'], name='Signal',
        line=dict(color='#f97316', width=1.5)), row=3, col=1)

    fig.update_layout(
        template="plotly_dark",
        height=460,
        margin=dict(l=8, r=8, t=12, b=8),
        legend=dict(orientation="h", y=1.03, x=0, font_size=10),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(255,255,255,0.02)',
    )
    fig.update_xaxes(gridcolor='rgba(255,255,255,0.04)', zeroline=False)
    fig.update_yaxes(gridcolor='rgba(255,255,255,0.04)', zeroline=False)
    fig.update_yaxes(title_text="RSI", row=2, col=1, range=[0, 100])
    fig.update_yaxes(title_text="MACD", row=3, col=1)
    st.plotly_chart(fig, use_container_width=True)

    # ── 📝 분석 메모 ─────────────────────────────────────────────
    st.markdown("""<div class="section-header"><div class="section-icon icon-violet">📝</div><div class="section-title title-violet">분석 메모</div></div>""", unsafe_allow_html=True)
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
    st.markdown("""<div class="section-header"><div class="section-icon icon-cyan">📊</div>
    <div class="section-title title-cyan">S&P 500 섹터 히트맵</div></div>""", unsafe_allow_html=True)

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
# 렌더링 함수 — 뉴스
# ════════════════════════════════════════════════════════════════
def render_news_section(ticker_input):
    """스톡타이탄 뉴스 & Rhea-AI 호재 검증 (탭2 또는 우측 컬럼)"""
    st.markdown("""<div class="section-header"><div class="section-icon icon-rose">🔥</div><div class="section-title title-rose">스톡타이탄 실시간 호재 & Rhea-AI 분석</div></div>""", unsafe_allow_html=True)

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

        for news_item, title_ko in zip(parsed_list, translated):
            st.markdown(f"""
            <div class="news-card">
                <div class="news-meta">📰 {news_item['publisher']}</div>
                <div class="news-title">{title_ko}</div>
                <a class="news-link" href="{news_item['link']}" target="_blank">기사 원문 보기 →</a>
            </div>
            """, unsafe_allow_html=True)
    else:
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
        hist = fetch_history(active_ticker)

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

            # 거래대금 (실시간 환율 적용)
            trading_value_usd     = today['Close'] * today['Volume']
            trading_value_krw_eok = (trading_value_usd * fetch_usd_to_krw()) / 100_000_000   # #2 실시간 환율

            # #7 52주 최고/최저
            high_52w = hist['High'].max()
            low_52w  = hist['Low'].min()

            if desktop_mode:
                col1, col2 = st.columns([4, 5])
                with col1:
                    render_technical_analysis(
                        active_ticker, hist, today, yesterday,
                        vol_ratio, vol_ma20_ratio,
                        trading_value_krw_eok, TRADING_THRESHOLD,
                        high_52w, low_52w
                    )
                with col2:
                    render_news_section(active_ticker)
            else:
                tab1, tab2 = st.tabs(["📊 기술 분석", "📰 뉴스 & 호재"])
                with tab1:
                    render_technical_analysis(
                        active_ticker, hist, today, yesterday,
                        vol_ratio, vol_ma20_ratio,
                        trading_value_krw_eok, TRADING_THRESHOLD,
                        high_52w, low_52w
                    )
                with tab2:
                    render_news_section(active_ticker)