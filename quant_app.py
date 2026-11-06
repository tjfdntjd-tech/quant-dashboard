import json
import os
import random
import re
import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from deep_translator import GoogleTranslator
from concurrent.futures import ThreadPoolExecutor, as_completed

# ════════════════════════════════════════════════════════════════
# 공통 유틸리티 — HTTP 세션 재사용 & 재사용 가능한 UI 컴포넌트
# ════════════════════════════════════════════════════════════════
@st.cache_resource
def get_http_session() -> requests.Session:
    """
    앱 전체에서 재사용할 HTTP 세션 (커넥션 풀 / Keep-Alive).
    매 요청마다 TCP·TLS 연결을 새로 맺는 낭비를 줄여 줍니다.
    st.cache_resource 덕분에 서버 전체에서 딱 한 번만 만들어집니다.
    """
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def ui_section_header(icon: str, title: str, color_class: str = "title-cyan", icon_class: str = "icon-cyan"):
    """
    반복되던 섹션 헤더 HTML을 한 곳으로 모은 함수.
    icon_class(아이콘 배경색)와 color_class(제목 글자색)를 따로 받아서
    기존에 섞여 쓰이던 색 조합을 그대로 재현할 수 있습니다.
    """
    st.markdown(
        f"""<div class="section-header">
            <div class="section-icon {icon_class}">{icon}</div>
            <div class="section-title {color_class}">{title}</div>
        </div>""",
        unsafe_allow_html=True,
    )

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
        resp = get_http_session().get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        rate = data["rates"]["KRW"]
        return float(rate)
    except Exception:
        return 1400.0  # 폴백: 조회 실패 시 고정값 사용

TRADING_THRESHOLD = 500           # 거래대금 기준 (억 원)
MEMO_FILE         = "memos.json"  # #9 메모 영구 저장 파일

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
# 1. 페이지 설정 — set_page_config는 반드시 가장 먼저
# ════════════════════════════════════════════════════════════════
st.set_page_config(page_title="급등주 실시간 검증기 V3", layout="wide", initial_sidebar_state="auto")

# ════════════════════════════════════════════════════════════════
# #1 session_state 초기화 — 단일 위치, 중복 제거
# ════════════════════════════════════════════════════════════════
_defaults = {
    "favorites":        [],
    "selected_ticker":  "",
    "memos":            load_memos(),   # #9 파일에서 복원
    "scan_results":     [],
    "show_heatmap":     False,          # 섹터 히트맵 토글 (사이드바 버튼보다 먼저 초기화)
    "has_searched":     False,          # #15 검색 실행 여부 — 기간 변경 등 리렌더링 후에도 결과 유지
    "active_ticker":    "",             # #15 마지막으로 검색을 실행한 티커
    "dark_mode":        True,           # 다크/라이트 모드 토글
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

def _extract_titan_date(link_tag) -> str:
    """
    스톡타이탄 기사 링크의 부모 태그를 최대 4단계 올라가며 날짜 요소를 찾아
    'May 01, 2024' 형식으로 돌려줍니다. 못 찾으면 "날짜 미확인".
    (get_stock_titan_data 안에 있던 로직을 그대로 옮긴 것 — 동작 동일)
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
                # 1차: ISO 형식 (2024-05-01T12:34:56...)
                return datetime.fromisoformat(raw_date[:19]).strftime("%b %d, %Y")
            except Exception:
                # 2차: 정규식으로 YYYY-MM-DD 또는 "May 1, 2024" 패턴 추출
                _m = re.search(
                    r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})'
                    r'|(\w{3,9})\s+(\d{1,2}),?\s+(\d{4})',
                    raw_date or ""
                )
                if _m:
                    try:
                        if _m.group(1):
                            return datetime(int(_m.group(1)), int(_m.group(2)), int(_m.group(3))).strftime("%b %d, %Y")
                        raw_eng = f"{_m.group(4)} {_m.group(5)} {_m.group(6)}"
                        fmt = "%B %d %Y" if len(_m.group(4)) > 3 else "%b %d %Y"
                        return datetime.strptime(raw_eng, fmt).strftime("%b %d, %Y")
                    except Exception:
                        return raw_date[:20] if raw_date else "날짜 미확인"
                # 3차: 원문 앞부분 그대로
                return raw_date[:20].strip() if raw_date else "날짜 미확인"
        parent = parent.parent
    return "날짜 미확인"

def get_stock_titan_data(ticker: str) -> list:
    url     = f"https://www.stocktitan.net/overview/{ticker}/"
    headers = _random_headers()   # #13

    try:
        response = get_http_session().get(url, headers=headers, timeout=8)
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

            # #4 날짜 파싱 — 독립 함수로 분리 (가독성 향상)
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
        resp = get_http_session().get(url, headers=headers, timeout=6)
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

@st.cache_data(ttl=180, show_spinner=False)
def fetch_reddit_posts(ticker: str) -> list:
    """
    Reddit JSON API — r/stocks, r/wallstreetbets, r/investing 병렬 수집.
    제목(title) + 본문(selftext) 모두 가져옵니다.
    """
    subreddits = ["stocks", "wallstreetbets", "investing"]

    def _fetch_sub(sub: str) -> list:
        url = (f"https://www.reddit.com/r/{sub}/search.json"
               f"?q={ticker}&sort=new&limit=5&restrict_sr=1&t=week")
        try:
            headers = {
                "User-Agent": f"Mozilla/5.0 quant_app/2.0 (by /u/quant_user)",
                "Accept": "application/json",
            }
            resp = get_http_session().get(url, headers=headers, timeout=8)
            if resp.status_code != 200:
                return []
            out = []
            for p in resp.json().get("data", {}).get("children", []):
                d = p.get("data", {})
                title = (d.get("title") or "").strip()
                if not title:
                    continue
                # selftext: 본문 내용 (없으면 빈 문자열)
                selftext = (d.get("selftext") or "").strip()
                # 너무 긴 본문은 300자로 자름
                if len(selftext) > 300:
                    selftext = selftext[:297] + "..."
                out.append({
                    "subreddit": sub,
                    "title":     title,
                    "selftext":  selftext,
                    "ups":       d.get("ups", 0),
                    "comments":  d.get("num_comments", 0),
                    "link":      "https://www.reddit.com" + (d.get("permalink") or ""),
                })
            return out
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=3) as ex:
        all_posts = list(ex.map(_fetch_sub, subreddits))

    merged = [p for sub_list in all_posts for p in sub_list]
    merged.sort(key=lambda x: x["ups"], reverse=True)
    return merged[:6]


def render_social_section(ticker_input: str):
    """소셜 미디어 의견 탭 — StockTwits + Reddit"""
    ui_section_header("💬", "소셜 미디어 투자자 의견", "title-cyan", "icon-cyan")

    with st.spinner("StockTwits · Reddit 실시간 데이터 수집 중..."):
        st_data     = fetch_stocktwits(ticker_input)
        reddit_data = fetch_reddit_posts(ticker_input)

    # ── StockTwits / Yahoo Finance fallback ─────────────────────
    src = st_data.get("source", "") if st_data else ""
    if src == "stocktwits":
        src_icon  = "🐦"
        src_label = "StockTwits"
        src_color = "#38bdf8"
        src_badge_cls = "platform-badge"
    else:
        src_icon  = "📰"
        src_label = "Yahoo Finance 뉴스 감성 분석"
        src_color = "#a78bfa"
        src_badge_cls = "platform-badge"

    st.markdown(
        f'''<div class="section-header" style="margin-top:0.3rem;">
            <div class="section-icon icon-cyan" style="font-size:0.8rem;">{src_icon}</div>
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

    # ── Reddit ───────────────────────────────────────────────────
    st.markdown(
        """<div class="section-header">
            <div class="section-icon"
                 style="background:rgba(255,106,0,0.18);border-color:rgba(255,106,0,0.35);font-size:0.8rem;">🤖</div>
            <div class="section-title"
                 style="color:#ff6a00;font-size:0.88rem;">Reddit (r/stocks · r/wallstreetbets · r/investing)</div>
        </div>""",
        unsafe_allow_html=True,
    )

    if not reddit_data:
        st.markdown(
            """<div class="glass-card"><div class="status-row"><div class="status-item">
                <div class="status-dot dot-yellow"></div>
                <div class="status-text">이번 주 해당 티커 관련 Reddit 게시글이 없거나 불러올 수 없습니다.</div>
            </div></div></div>""",
            unsafe_allow_html=True,
        )
    else:
        for post in reddit_data:
            selftext_html = (
                f'<div class="social-selftext">{post["selftext"]}</div>'
                if post.get("selftext") else ""
            )
            st.markdown(f"""
            <div class="social-card">
                <div class="social-meta">
                    <span class="reddit-badge">r/{post['subreddit']}</span>
                    <span>·</span>
                    <span>⬆️ {post['ups']:,}</span>
                    <span>·</span>
                    <span>💬 {post['comments']:,}개 댓글</span>
                </div>
                <div class="social-body">{post['title']}</div>
                {selftext_html}
                <div class="social-stats">
                    <a href="{post['link']}" target="_blank"
                       style="color:rgba(148,163,184,0.4);text-decoration:none;font-size:0.72rem;">
                        Reddit에서 보기 →
                    </a>
                </div>
            </div>""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# CSS — 다크/라이트 모드 동적 주입
# ════════════════════════════════════════════════════════════════
def inject_css(dark: bool = True):
    if dark:
        bg_main      = "linear-gradient(135deg, #0a0a1a 0%, #0d0d2b 40%, #0a1628 100%)"
        bg_sidebar   = "linear-gradient(180deg, #0d0d2b 0%, #0a1628 100%)"
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

    st.session_state["_plotly_template"] = plotly_tmpl

    st.markdown(f"""
<style>
    /* ── 폰트 임포트 ──────────────────────────────────────────────── *
     * 디스플레이: Space Grotesk (헤딩 — 개성)                         *
     * 본문: Inter (가독성)                                            *
     * 데이터: JetBrains Mono (가격/티커/지표 — 자릿수 정렬되는 단말기 느낌) */
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700;800&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600;700&display=swap');

    :root {{
        --font-display: 'Space Grotesk', 'Segoe UI', sans-serif;
        --font-body:    'Inter', 'Segoe UI', system-ui, sans-serif;
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
        background: {bg_main} !important;
        font-family: var(--font-body);
    }}
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
        border-radius: 18px;
        padding: 1.4rem 1.8rem;
        margin-bottom: 1.4rem;
        backdrop-filter: blur(12px);
        box-shadow: 0 8px 32px rgba(99,102,241,0.15), inset 0 1px 0 rgba(255,255,255,0.08);
    }}
    .app-header h1 {{
        margin: 0 0 0.2rem 0;
        font-size: 1.55rem;
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
        font-size: 0.82rem;
    }}

    /* ── 글래스 카드 공통 ──────────────────────────────────────────── */
    .glass-card {{
        background: {glass_bg};
        border: 1px solid {glass_border};
        border-radius: 14px;
        padding: 1.1rem 1.2rem;
        margin-bottom: 1rem;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 20px rgba(0,0,0,0.25);
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
        border-radius: 14px;
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
        width: 28px; height: 28px;
        background: linear-gradient(135deg, var(--c-violet-std), var(--c-indigo-a20));
        border: 1px solid var(--c-violet-bdr);
        border-radius: 8px;
        display: flex; align-items: center; justify-content: center;
        font-size: 0.85rem;
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

    /* ── 버튼 ──────────────────────────────────────────────────────── */
    .stButton button {{
        background: linear-gradient(135deg, rgba(139,92,246,0.25), rgba(59,130,246,0.2)) !important;
        border: 1px solid rgba(139,92,246,0.4) !important;
        border-radius: 10px !important;
        color: {text_primary} !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        transition: all 0.2s !important;
        min-height: 2.5rem !important;
    }}
    .stButton button:hover {{
        background: linear-gradient(135deg, rgba(139,92,246,0.4), rgba(59,130,246,0.3)) !important;
        border-color: rgba(139,92,246,0.65) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 15px rgba(139,92,246,0.25) !important;
    }}

    /* ── 탭 ────────────────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {{
        background: {tab_bg} !important;
        border-radius: 12px !important;
        padding: 0.3rem !important;
        gap: 0.3rem !important;
        border: 1px solid {tab_bdr} !important;
    }}
    .stTabs [data-baseweb="tab"] {{
        border-radius: 9px !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        color: {text_muted} !important;
        padding: 0.55rem 1.1rem !important;
    }}
    .stTabs [aria-selected="true"] {{
        background: linear-gradient(135deg, rgba(139,92,246,0.35), rgba(59,130,246,0.25)) !important;
        color: {text_primary} !important;
        border: 1px solid rgba(139,92,246,0.4) !important;
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
        .app-header h1 {{ font-size: 1.2rem; }}
        .metric-value {{ font-size: 1.25rem; }}
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

inject_css(st.session_state.get("dark_mode", True))

# ════════════════════════════════════════════════════════════════
# 🧱 뉴브루탈리즘(Neo-Brutalism) 테마
#   - 기존 inject_css() 위에 "덧입히는" 오버라이드 레이어입니다.
#     (뒤에 나오는 CSS가 앞의 CSS를 이기기 때문에, 이 함수를 inject_css() 다음에 호출)
#   - 핵심 4가지: ① 두꺼운 검정 테두리 ② 번짐 없는 딱딱한 그림자
#                 ③ 핑크·노랑·라임 3색 ④ 툭 튀어나오는 등장 애니메이션
#   - 다크/라이트 모드는 색 변수(--nb-ink, --nb-paper)만 바뀌고 나머지 규칙은 동일합니다.
# ════════════════════════════════════════════════════════════════
def inject_neobrutal_theme(dark: bool = True):
    # 모드별 색: ink = 테두리·그림자·글자색 / paper = 카드 배경 / bg = 화면 바탕
    if dark:
        bg, paper, ink, grid = "#17141f", "#2a2633", "#f4f1ea", "rgba(255,255,255,0.07)"
    else:
        bg, paper, ink, grid = "#fff4dc", "#ffffff", "#111111", "rgba(0,0,0,0.10)"

    # CSS 안에 중괄호가 많아서 f-string 대신 일반 문자열 + replace() 방식을 씁니다.
    # (f-string 이중 중괄호 실수로 CSS가 깨졌던 버그를 다시 겪지 않기 위함)
    css = """<style>
    /* ── 색 변수 ─────────────────────────────────────────────── */
    :root {
        --nb-bg: __BG__;  --nb-paper: __PAPER__;  --nb-ink: __INK__;  --nb-grid: __GRID__;
        --nb-pink: #ff6fb5;  --nb-yellow: #ffe14a;  --nb-lime: #b6f23a;  --nb-red: #ff5a5a;
        --nb-on: #111111;                      /* 색칠된 면 위의 글자는 항상 검정 */
        --nb-shadow: 6px 6px 0 var(--nb-ink);  /* 번짐(blur) 0 = 딱딱한 그림자 */
    }

    /* ── 바탕: 점 격자 무늬 ───────────────────────────────────── */
    html, body, [data-testid="stAppViewContainer"] {
        background-color: var(--nb-bg) !important;
        background-image: radial-gradient(var(--nb-grid) 2px, transparent 2px) !important;
        background-size: 24px 24px !important;
    }
    [data-testid="stHeader"] { background: transparent !important; }
    .block-container { padding-bottom: 6rem !important; }            /* 하단 띠 글자 자리 */
    [data-testid="stSidebarUserContent"] { padding-bottom: 4rem !important; }

    /* ── 사이드바 ─────────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        background: var(--nb-paper) !important;
        border-right: 5px solid var(--nb-ink) !important;
    }

    /* ── 입력창 ───────────────────────────────────────────────── */
    [data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {
        background: var(--nb-paper) !important;
        border: 3px solid var(--nb-ink) !important;
        border-radius: 0 !important;
        box-shadow: 4px 4px 0 var(--nb-ink) !important;
    }
    [data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within {
        background: var(--nb-yellow) !important;
    }
    [data-baseweb="input"]:focus-within input, [data-baseweb="textarea"]:focus-within textarea {
        color: var(--nb-on) !important;
    }
    /* 안쪽 input 은 테두리를 없애 바깥 wrapper 의 테두리와 겹치지 않게 함 */
    .stTextInput input, [data-testid="stSidebar"] .stTextInput input,
    .stTextArea textarea, .stTextArea textarea:focus {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        color: var(--nb-ink) !important;
        font-weight: 700 !important;
    }

    /* ── 헤더 배너 + 별 스티커 ────────────────────────────────── */
    .app-header {
        position: relative;
        background: var(--nb-pink) !important;
        border: 5px solid var(--nb-ink) !important;
        border-radius: 0 !important;
        box-shadow: 10px 10px 0 var(--nb-ink) !important;
        backdrop-filter: none !important;
        margin-bottom: 1.8rem !important;
        animation: nb-pop .6s cubic-bezier(.2,1.6,.4,1) backwards;
    }
    .app-header h1 {
        background: none !important;
        -webkit-text-fill-color: var(--nb-on) !important;
        color: var(--nb-on) !important;
        font-weight: 800 !important;
    }
    .app-header p { color: var(--nb-on) !important; font-weight: 700 !important; }
    .app-header::after {                       /* 오른쪽 위 모서리에 붙는 노란 별 */
        content: "";
        position: absolute; right: -10px; top: -30px;
        width: 64px; height: 64px;
        background: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><polygon points='50,6 62,38 96,38 68,58 79,92 50,71 21,92 32,58 4,38 38,38' fill='%23ffe14a' stroke='%23111' stroke-width='6' stroke-linejoin='round'/></svg>") center / contain no-repeat;
        filter: drop-shadow(4px 4px 0 var(--nb-ink));
        transform: rotate(12deg);
        animation: nb-star .9s .35s cubic-bezier(.2,1.6,.4,1) backwards;
    }

    /* ── 카드류: 두꺼운 테두리 + 딱딱한 그림자 ─────────────────── */
    .glass-card, .metric-card, .news-card, .social-card, .scan-header, .sentiment-bar-wrap {
        background: var(--nb-paper) !important;
        border: 4px solid var(--nb-ink) !important;
        border-radius: 0 !important;
        box-shadow: var(--nb-shadow) !important;
        backdrop-filter: none !important;
        animation: nb-pop .45s cubic-bezier(.2,1.6,.4,1) backwards;
    }
    /* 호재/악재 카드는 왼쪽 두꺼운 색 막대로 의미를 표시 (라임=호재, 빨강=악재) */
    .pos-card, .social-bull { border-left: 14px solid var(--nb-lime) !important; }
    .neg-card, .social-bear { border-left: 14px solid var(--nb-red) !important; }
    .neu-card               { border-left: 14px solid var(--nb-yellow) !important; }

    /* ── 경고 배너들: 면 전체를 색칠 ──────────────────────────── */
    .alert-banner, .china-banner, .split-banner {
        border: 4px solid var(--nb-ink) !important;
        border-radius: 0 !important;
        box-shadow: var(--nb-shadow) !important;
        backdrop-filter: none !important;
        animation: nb-pop .45s cubic-bezier(.2,1.6,.4,1) backwards;
    }
    .alert-banner { background: var(--nb-yellow) !important; }
    .china-banner { background: var(--nb-red) !important; }
    .split-banner { background: var(--nb-yellow) !important; }
    .alert-banner *, .china-banner *, .split-banner * { color: var(--nb-on) !important; }
    .alert-banner .signal-chip {
        background: var(--nb-pink) !important;
        border: 3px solid var(--nb-on) !important;
        border-radius: 0 !important;
        font-weight: 800 !important;
    }

    /* ── 섹션 헤더: 붙여 놓은 스티커 라벨 느낌 ────────────────── */
    .section-header {
        background: var(--nb-paper) !important;
        border: 4px solid var(--nb-ink) !important;
        border-radius: 0 !important;
        box-shadow: 5px 5px 0 var(--nb-ink) !important;
        padding: .45rem .8rem !important;
        margin: 1.4rem 0 1rem 0 !important;
        width: fit-content; max-width: 100%;
        animation: nb-pop .45s cubic-bezier(.2,1.6,.4,1) backwards;
    }
    .section-icon {
        background: var(--nb-yellow) !important;
        border: 3px solid var(--nb-on) !important;
        border-radius: 0 !important;
        box-shadow: none !important;
        color: var(--nb-on) !important;
    }
    .icon-rose, .icon-violet { background: var(--nb-pink) !important; }
    .icon-teal, .icon-cyan   { background: var(--nb-lime) !important; }
    .icon-amber, .icon-indigo{ background: var(--nb-yellow) !important; }
    .section-header .section-title { color: var(--nb-ink) !important; font-weight: 800 !important; }

    /* ── 상태 줄 · 점 · 뱃지: 각진 모양 ───────────────────────── */
    .status-item {
        background: var(--nb-paper) !important;
        border: 2px solid var(--nb-ink) !important;
        border-radius: 0 !important;
    }
    .status-dot { width: 13px !important; height: 13px !important; border: 2px solid var(--nb-ink); border-radius: 0 !important; box-shadow: none !important; }
    .dot-green  { background: var(--nb-lime)   !important; }
    .dot-yellow { background: var(--nb-yellow) !important; }
    .dot-red    { background: var(--nb-red)    !important; }
    .dot-blue   { background: #5ad7ff          !important; }
    .sentiment-badge, .impact-badge, .platform-badge, .reddit-badge, .bull-badge, .bear-badge {
        border: 2px solid var(--nb-ink) !important;
        border-radius: 0 !important;
        font-weight: 800 !important;
    }

    /* ── 버튼: 누르면 그림자가 사라지며 "꾹" 눌림 ──────────────── */
    .stButton button, .stDownloadButton button,
    [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-primary"] {
        background: var(--nb-lime) !important;
        border: 4px solid var(--nb-ink) !important;
        border-radius: 0 !important;
        box-shadow: 5px 5px 0 var(--nb-ink) !important;
        font-weight: 800 !important;
        transition: transform .08s, box-shadow .08s !important;
    }
    .stButton button p, .stButton button div, .stDownloadButton button p { color: var(--nb-on) !important; }
    .stButton button:hover { background: var(--nb-yellow) !important; transform: translate(-2px,-2px) !important; box-shadow: 7px 7px 0 var(--nb-ink) !important; }
    .stButton button:active { background: var(--nb-pink) !important; transform: translate(5px,5px) !important; box-shadow: 0 0 0 var(--nb-ink) !important; }
    .stButton button[kind="primary"], [data-testid="stBaseButton-primary"] { background: var(--nb-pink) !important; }

    /* ── 탭 ───────────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {
        background: var(--nb-paper) !important;
        border: 4px solid var(--nb-ink) !important;
        border-radius: 0 !important;
        box-shadow: 5px 5px 0 var(--nb-ink) !important;
    }
    .stTabs [data-baseweb="tab"] { border-radius: 0 !important; font-weight: 800 !important; }
    .stTabs [data-baseweb="tab"] p { color: var(--nb-ink) !important; }
    .stTabs [aria-selected="true"] {
        background: var(--nb-yellow) !important;
        border: 3px solid var(--nb-on) !important;
        box-shadow: 3px 3px 0 var(--nb-ink) !important;
    }
    .stTabs [aria-selected="true"] p { color: var(--nb-on) !important; }
    .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none !important; }

    /* ── 섹터 히트맵 · 표 · 구분선 · 익스팬더 ─────────────────── */
    .sector-cell { border: 3px solid var(--nb-ink) !important; border-radius: 0 !important; box-shadow: 4px 4px 0 var(--nb-ink) !important; }
    [data-testid="stDataFrame"], [data-testid="stExpander"] {
        border: 4px solid var(--nb-ink) !important;
        border-radius: 0 !important;
        box-shadow: var(--nb-shadow) !important;
    }
    hr { border-color: var(--nb-ink) !important; border-top-width: 3px !important; opacity: 1 !important; }

    /* ── 맨 아래 띠 글자 (핑크 → 노랑 → 라임 순환) ───────────── */
    .nb-ticker {
        position: fixed; left: 0; right: 0; bottom: 0; z-index: 999;
        background: var(--nb-paper);
        border-top: 5px solid var(--nb-ink);
        overflow: hidden;
        padding-bottom: env(safe-area-inset-bottom, 0px);
    }
    .nb-track { display: flex; width: max-content; animation: nb-slide 18s linear infinite; }
    .nb-set { display: flex; }
    .nb-set span {
        padding: 10px 20px;
        font: 800 17px/1 var(--font-display);
        letter-spacing: 1px; white-space: nowrap;
        color: var(--nb-on);
        border-right: 4px solid var(--nb-on);
    }
    .nb-set span:nth-child(3n+1) { background: var(--nb-pink); }
    .nb-set span:nth-child(3n+2) { background: var(--nb-yellow); }
    .nb-set span:nth-child(3n+3) { background: var(--nb-lime); }

    /* ── 애니메이션 정의 ──────────────────────────────────────── */
    @keyframes nb-pop {        /* 위에서 툭 떨어졌다가 살짝 넘치고 제자리 */
        0%   { opacity: 0; transform: translateY(-28px) scale(.92) rotate(-1.5deg); }
        60%  { opacity: 1; transform: translateY(5px) scale(1.02); }
        100% { opacity: 1; transform: none; }
    }
    @keyframes nb-star {       /* 별 스티커가 빙글 돌며 척 붙음 */
        0%   { opacity: 0; transform: scale(0) rotate(-90deg); }
        100% { opacity: 1; transform: scale(1) rotate(12deg); }
    }
    @keyframes nb-slide { from { transform: translateX(0); } to { transform: translateX(-50%); } }

    /* 움직임 줄이기 설정을 켠 사용자: 애니메이션 끄기 */
    @media (prefers-reduced-motion: reduce) {
        .glass-card, .metric-card, .news-card, .social-card, .scan-header, .sentiment-bar-wrap,
        .alert-banner, .china-banner, .split-banner, .section-header, .app-header, .app-header::after { animation: none !important; }
        .nb-track { animation-duration: 90s; }
    }
    /* 모바일: 테두리·그림자를 조금 줄여 화면 낭비 방지 */
    @media (max-width: 640px) {
        :root { --nb-shadow: 4px 4px 0 var(--nb-ink); }
        .glass-card, .metric-card, .news-card, .social-card { border-width: 3px !important; }
        .app-header { box-shadow: 6px 6px 0 var(--nb-ink) !important; }
        .app-header::after { width: 48px; height: 48px; right: -4px; top: -24px; }
        .nb-set span { font-size: 14px; padding: 9px 14px; }
    }
    </style>"""
    for key, val in {"__BG__": bg, "__PAPER__": paper, "__INK__": ink, "__GRID__": grid}.items():
        css = css.replace(key, val)
    st.markdown(css, unsafe_allow_html=True)

    # 하단 띠 글자: 같은 묶음(.nb-set)을 두 번 이어 붙이고 절반(-50%)만 이동 → 끊김 없이 무한 반복
    # (9개 = 3의 배수여야 두 번째 묶음에서도 핑크·노랑·라임 순서가 어긋나지 않음)
    # 주의: 마크다운이 '$'를 수식으로 오해할 수 있어 '1달러'로 씀, HTML 안에 빈 줄도 넣지 않음
    items = ["급등주 실시간 검증기 V3", "★ 거래량 급증", "오퍼링 이력 체크",
             "나스닥 1달러 규정", "중국 기업 주의", "주식병합 감시",
             f"환율 ₩{fetch_usd_to_krw():,.0f}", "하루 100%+ 이력", "★★★"]
    one_set = "".join(f"<span>{t}</span>" for t in items)
    st.markdown(
        f'<div class="nb-ticker" aria-hidden="true"><div class="nb-track">'
        f'<div class="nb-set">{one_set}</div><div class="nb-set">{one_set}</div></div></div>',
        unsafe_allow_html=True,
    )


inject_neobrutal_theme(st.session_state.get("dark_mode", True))

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
_is_dark = st.session_state.get("dark_mode", True)
_toggle_label = "☀️ 라이트 모드로 전환" if _is_dark else "🌙 다크 모드로 전환"
if st.sidebar.button(_toggle_label, use_container_width=True):
    st.session_state["dark_mode"] = not _is_dark
    st.rerun()
st.sidebar.markdown("")

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
                    gap_up_pct = (t['Open'] - y['Close']) / y['Close'] * 100

                    signals = []
                    if vol_r  >= 200:  signals.append("🔥거래량")   # MA20 대비 200%+
                    if macd_cross:     signals.append("⚡MACD")
                    if rsi    <= 35:   signals.append("📉과매도")
                    if t['Close'] > t['MA120'] and y['Close'] <= y['MA120']:
                                       signals.append("🚀120일선")
                    if gap_up_pct >= 5:
                                       signals.append("⬆️갭업")     # 시초가 전일종가 대비 5%+
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

    # ── 🚀 100%+ 급등 이력 ───────────────────────────────────────
    ui_section_header("🚀", "하루 100%+ 급등 이력", "title-rose", "icon-rose")
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
    ui_section_header("📜", "오퍼링(유상증자) 관련 공시 이력", "title-amber", "icon-amber")
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
    ui_section_header("💡", "실시간 자금 유입 체크", "title-amber", "icon-amber")

    # #8 거래량: 전일 대비 + MA20 대비 둘 다 표시
    vol_dot  = "dot-green"  if vol_ma20_ratio >= 200 else "dot-yellow"
    vol_text = (f"<strong>거래량 폭증!</strong> MA20 대비 <strong>{vol_ma20_ratio:.0f}%</strong> "
                f"(전일 대비 {vol_ratio:.0f}%)"
                if vol_ma20_ratio >= 200