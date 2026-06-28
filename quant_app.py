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

# ── 캐시 래퍼 함수 ──────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)   # 5분 캐시
def fetch_history(ticker: str) -> pd.DataFrame:
    """yfinance 1년치 OHLCV — 동일 티커 재검색 시 재다운로드 없이 즉시 반환"""
    return yf.Ticker(ticker).history(period="1y")

@st.cache_data(ttl=300, show_spinner=False)   # 5분 캐시
def fetch_yahoo_news(ticker: str) -> list:
    """yfinance 뉴스 목록 캐싱 — fallback 경로에서도 반복 호출 방지"""
    return yf.Ticker(ticker).news

@st.cache_data(ttl=3600, show_spinner=False)  # 1시간 캐시 (번역 결과는 잘 안 바뀜)
def translate_text(text: str) -> str:
    """GoogleTranslator 호출 결과 캐싱 — 동일 문장 재번역 방지"""
    if not text:
        return text
    try:
        return GoogleTranslator(source='en', target='ko').translate(text)
    except Exception:
        return text
# ────────────────────────────────────────────────────────────────

# ── 기술적 지표 계산 함수 ────────────────────────────────────────
def calc_indicators(df: pd.DataFrame) -> pd.DataFrame:
    c = df['Close']

    # 이동평균선
    df['MA5']   = c.rolling(5,   min_periods=1).mean()
    df['MA20']  = c.rolling(20,  min_periods=1).mean()
    df['MA120'] = c.rolling(120, min_periods=1).mean()

    # ── RSI (14일) ───────────────────────────────────────────────
    delta = c.diff()
    gain  = delta.clip(lower=0).rolling(14, min_periods=1).mean()
    loss  = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
    rs    = gain / loss.replace(0, float('nan'))
    df['RSI'] = 100 - (100 / (1 + rs))

    # ── 볼린저밴드 (20일, ±2σ) ──────────────────────────────────
    mid             = c.rolling(20, min_periods=1).mean()
    std             = c.rolling(20, min_periods=1).std()
    df['BB_MID']    = mid
    df['BB_UPPER']  = mid + 2 * std
    df['BB_LOWER']  = mid - 2 * std
    df['BB_WIDTH']  = (df['BB_UPPER'] - df['BB_LOWER']) / mid * 100  # %B 폭

    # ── MACD (12/26 EMA, Signal 9) ──────────────────────────────
    ema12         = c.ewm(span=12, adjust=False).mean()
    ema26         = c.ewm(span=26, adjust=False).mean()
    df['MACD']    = ema12 - ema26
    df['MACD_SIG']  = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_HIST'] = df['MACD'] - df['MACD_SIG']

    return df
# ────────────────────────────────────────────────────────────────

# 1. 페이지 기본 설정
st.set_page_config(page_title="급등주 실시간 검증기 V2", layout="wide", initial_sidebar_state="expanded")

# CSS를 활용한 디자인 커스텀 (가독성 및 카드 스타일 적용)
st.markdown("""
<style>
    .reportview-container { background-color: #0e1117; }
    .news-card {
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 15px;
        border-left: 5px solid #6b7280;
        background-color: #1f2937;
    }
    .pos-card { border-left: 6px solid #10b981; background-color: #064e3b; }
    .neg-card { border-left: 6px solid #ef4444; background-color: #7f1d1d; }
    .neu-card { border-left: 6px solid #f59e0b; background-color: #78350f; }
    .impact-badge {
        background-color: #3b82f6; color: white; padding: 2px 6px;
        border-radius: 4px; font-size: 11px; font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

st.title("🚀 급등주 조건 & Rhea-AI 호재 실시간 검증기 V2")
st.markdown("---")

# 2. session_state 초기화
if "favorites" not in st.session_state:
    st.session_state.favorites = []          # 즐겨찾기 티커 목록
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = "NVDA"  # 클릭으로 선택된 티커

# 3. 사이드바 - 티커 입력 및 파라미터 설정
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

# ── 즐겨찾기 목록 표시 ──────────────────────────────────────────
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
else:
    st.sidebar.markdown("---")
    st.sidebar.caption("☆ 버튼으로 즐겨찾기를 추가하세요")
# ────────────────────────────────────────────────────────────────

# 3. 스톡타이탄 Rhea-AI 감성 분석 및 뉴스 크롤링 함수
def _fetch_detail(link, headers):
    """상세 페이지에서 감성·임팩트를 병렬로 가져오는 내부 함수"""
    sentiment, impact = "Unknown", "Normal"
    try:
        detail_resp = requests.get(link, headers=headers, timeout=5)
        if detail_resp.status_code == 200:
            detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
            sentiment_box = detail_soup.find(class_=lambda x: x and 'sentiment' in x.lower())
            if sentiment_box:
                text = sentiment_box.text.lower()
                if 'positive' in text: sentiment = "Positive"
                elif 'negative' in text: sentiment = "Negative"
                elif 'neutral' in text: sentiment = "Neutral"
            if 'high impact' in detail_soup.text.lower():
                impact = "High Impact"
    except:
        pass
    return sentiment, impact

def get_stock_titan_data(ticker):
    url = f"https://www.stocktitan.net/overview/{ticker}/"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = soup.find_all('div', class_='news-item') or soup.find_all('article')
        
        # 1단계: 기사 목록 파싱 (번역 포함)
        raw_list = []
        for art in articles[:5]:
            link_tag = art.find('a')
            if not link_tag: continue
            title = link_tag.text.strip()
            link = "https://www.stocktitan.net" + link_tag['href'] if not link_tag['href'].startswith('http') else link_tag['href']
            date_tag = art.find('div', class_='date') or art.find('span', class_='date')
            date_str = date_tag.text.strip() if date_tag else datetime.today().strftime('%b %d, %Y')
            title_ko = translate_text(title)
            raw_list.append({"date": date_str, "title": title_ko, "title_en": title, "link": link})

        # 2단계: 상세 페이지 병렬 요청 (순차 최대 15초 → 병렬 약 3~5초로 단축)
        detail_results = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_link = {executor.submit(_fetch_detail, item["link"], headers): item["link"] for item in raw_list}
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

# 4. 메인 대시보드 로직
if search_button:
    with st.spinner("야후 파이낸스 및 스톡타이탄에서 실시간 데이터를 분석 중입니다..."):
        # [A] 수급 및 주가 데이터 수집 (캐시: 동일 티커 5분 내 재검색 시 즉시 반환)
        hist = fetch_history(ticker_input)
        stock = yf.Ticker(ticker_input)  # news fallback용
        
        if hist.empty:
            st.error("❌ 올바르지 않은 티커명이거나 데이터를 불러올 수 없습니다. 영문 티커를 확인해 주세요.")
        else:
            hist = hist.dropna()

            # 데이터 최소 요건 확인 (최소 2거래일 필요)
            if len(hist) < 2:
                st.error("❌ 데이터가 너무 적습니다. 상장된 지 얼마 안 된 종목이거나 거래 정지 상태일 수 있습니다.")
                st.stop()

            # 기술적 지표 계산 (MA / RSI / 볼린저밴드 / MACD)
            hist      = calc_indicators(hist)
            today     = hist.iloc[-1]
            yesterday = hist.iloc[-2]
            
            # 거래량 및 거래대금 산출
            vol_ratio = (today['Volume'] / yesterday['Volume']) * 100
            trading_value_usd = today['Close'] * today['Volume'] # 당일 거래대금(달러)
            trading_value_krw_billion = (trading_value_usd * 1350) / 1000000000 # 원화 환산(대략 1350원 기준)
            
            high_52w = hist['High'].max()
            
            # 화면 레이아웃 분할 (기술 점검 | 호재 뉴스)
            col1, col2 = st.columns([4, 5])
            
            # ----------------- 왼쪽 컬럼: 기술적 조건 & 수급 점검 -----------------
            with col1:
                st.subheader("📊 기술적 수급 및 이동평균선 점검")
                
                # ── 상단 메트릭 4칸 ─────────────────────────────────
                m1, m2, m3, m4 = st.columns(4)
                pct_chg = (today['Close'] - yesterday['Close']) / yesterday['Close'] * 100
                with m1:
                    st.metric("현재가", f"${today['Close']:.2f}", f"{pct_chg:.2f}%")
                with m2:
                    st.metric("52주 최고가", f"${high_52w:.2f}", f"격차 {((high_52w - today['Close']) / high_52w) * 100:.1f}%")
                with m3:
                    rsi_val = today['RSI']
                    rsi_label = "과매수" if rsi_val >= 70 else ("과매도" if rsi_val <= 30 else "중립")
                    st.metric("RSI (14)", f"{rsi_val:.1f}", rsi_label)
                with m4:
                    macd_val  = today['MACD']
                    macd_sig  = today['MACD_SIG']
                    macd_label = "골든크로스" if (today['MACD'] > today['MACD_SIG'] and yesterday['MACD'] <= yesterday['MACD_SIG']) else ("상승" if macd_val > macd_sig else "하락")
                    st.metric("MACD", f"{macd_val:.3f}", macd_label)

                st.markdown("---")

                # ── 거래량 & 거래대금 ────────────────────────────────
                st.markdown("#### 💡 실시간 자금 유입 체크")
                if vol_ratio >= 500:
                    st.success(f"🟢 **거래량 조건 통과!** 전일 대비 **{vol_ratio:.1f}%** 폭발적 급증")
                else:
                    st.warning(f"🟡 **거래량 미달:** 전일 대비 {vol_ratio:.1f}% 수준 (500% 이상 추천)")
                if trading_value_krw_billion >= 50:
                    st.success(f"🟢 **거래대금 조건 통과!** 당일 약 **{trading_value_krw_billion:.1f}억 원** 유입")
                else:
                    st.warning(f"🟡 **거래대금 부족:** 당일 약 {trading_value_krw_billion:.1f}억 원 (500억 이상 추천)")

                st.markdown("---")

                # ── 이동평균선 배열 ──────────────────────────────────
                st.markdown("#### 📈 이동평균선 배열 상태")
                if today['MA5'] > today['MA20'] > today['MA120']:
                    st.info("🔥 **완전 정배열:** 강력한 상승 추세 유지 중")
                elif today['Close'] > today['MA120'] and yesterday['Close'] <= yesterday['MA120']:
                    st.success("🚀 **120일선 돌파:** 급등 초입 타점!")
                else:
                    st.write("📊 이평선 밀집 — 에너지 응축 횡보 구간")

                # ── RSI 판단 ─────────────────────────────────────────
                st.markdown("#### 📉 RSI 모멘텀")
                if rsi_val >= 70:
                    st.warning(f"🟡 **RSI {rsi_val:.1f} — 과매수 구간.** 단기 조정 가능성 주의")
                elif rsi_val <= 30:
                    st.success(f"🟢 **RSI {rsi_val:.1f} — 과매도 구간.** 반등 매수 타점 탐색")
                else:
                    st.info(f"🔵 **RSI {rsi_val:.1f} — 중립 구간** (30~70)")

                # ── 볼린저밴드 판단 ──────────────────────────────────
                st.markdown("#### 🎯 볼린저밴드 위치")
                bb_pct = (today['Close'] - today['BB_LOWER']) / (today['BB_UPPER'] - today['BB_LOWER']) * 100
                if today['Close'] >= today['BB_UPPER']:
                    st.warning(f"🟡 **상단 밴드 터치 ({bb_pct:.0f}%).** 과열 — 밴드 타고 오르는지 확인 필요")
                elif today['Close'] <= today['BB_LOWER']:
                    st.success(f"🟢 **하단 밴드 터치 ({bb_pct:.0f}%).** 과매도 반등 구간")
                else:
                    st.info(f"🔵 밴드 내부 위치 {bb_pct:.0f}%  |  밴드폭 {today['BB_WIDTH']:.1f}%")

                # ── MACD 판단 ────────────────────────────────────────
                st.markdown("#### ⚡ MACD 신호")
                hist_val = today['MACD_HIST']
                prev_hist = yesterday['MACD_HIST']
                if macd_val > macd_sig and yesterday['MACD'] <= yesterday['MACD_SIG']:
                    st.success(f"🟢 **MACD 골든크로스 발생!** 상승 전환 신호")
                elif macd_val < macd_sig and yesterday['MACD'] >= yesterday['MACD_SIG']:
                    st.error(f"🔴 **MACD 데드크로스 발생.** 하락 전환 주의")
                elif hist_val > 0 and hist_val > prev_hist:
                    st.info(f"🔵 MACD 히스토그램 확대 중 — 상승 모멘텀 강화")
                else:
                    st.write(f"📊 MACD {macd_val:.3f}  /  Signal {macd_sig:.3f}  /  Hist {hist_val:.3f}")

                st.markdown("---")

                # ── 차트: 주가 + 볼린저밴드 (서브플롯: RSI / MACD) ──
                plot_df = hist.tail(60)

                fig = make_subplots(
                    rows=3, cols=1,
                    shared_xaxes=True,
                    row_heights=[0.55, 0.22, 0.23],
                    vertical_spacing=0.03,
                )

                # [1] 주가 + MA + 볼린저밴드
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['BB_UPPER'], name='BB 상단',
                    line=dict(color='#6b7280', width=1, dash='dot'), showlegend=False), row=1, col=1)
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['BB_LOWER'], name='BB 하단',
                    line=dict(color='#6b7280', width=1, dash='dot'),
                    fill='tonexty', fillcolor='rgba(107,114,128,0.08)', showlegend=False), row=1, col=1)
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['BB_MID'], name='BB 중심(20일)',
                    line=dict(color='#9ca3af', width=1, dash='dash')), row=1, col=1)
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Close'], name='주가',
                    line=dict(color='#3b82f6', width=2)), row=1, col=1)
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], name='MA20',
                    line=dict(color='#f59e0b', width=1.2)), row=1, col=1)
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA120'], name='MA120',
                    line=dict(color='#ef4444', width=1.2)), row=1, col=1)

                # [2] RSI + 과매수/과매도 기준선
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['RSI'], name='RSI',
                    line=dict(color='#a78bfa', width=1.5)), row=2, col=1)
                fig.add_hline(y=70, line_color='#ef4444', line_dash='dot', line_width=1, row=2, col=1)
                fig.add_hline(y=30, line_color='#10b981', line_dash='dot', line_width=1, row=2, col=1)

                # [3] MACD 히스토그램 + MACD / Signal 선
                colors = ['#10b981' if v >= 0 else '#ef4444' for v in plot_df['MACD_HIST']]
                fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['MACD_HIST'], name='MACD Hist',
                    marker_color=colors, opacity=0.7), row=3, col=1)
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MACD'], name='MACD',
                    line=dict(color='#60a5fa', width=1.5)), row=3, col=1)
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MACD_SIG'], name='Signal',
                    line=dict(color='#f97316', width=1.5)), row=3, col=1)

                fig.update_layout(
                    title=f"{ticker_input} 기술적 분석 (최근 60일)",
                    template="plotly_dark",
                    height=560,
                    margin=dict(l=20, r=20, t=40, b=20),
                    legend=dict(orientation="h", y=1.02, x=0, font_size=11),
                )
                fig.update_yaxes(title_text="RSI", row=2, col=1, range=[0, 100])
                fig.update_yaxes(title_text="MACD", row=3, col=1)
                st.plotly_chart(fig, use_container_width=True)
                
            # ----------------- 오른쪽 컬럼: 스톡타이탄 뉴스 & Rhea-AI 호재 검증 -----------------
            with col2:
                st.subheader("🔥 스톡타이탄 실시간 호재 & Rhea-AI 분석 (국문 번역)")
                
                news_data = get_stock_titan_data(ticker_input)
                
                if not news_data:
                    st.write("📢 스톡타이탄에서 최근 공시 뉴스를 크롤링하지 못했습니다. 대안으로 야후 파이낸스 실시간 뉴스를 노출합니다.")
                    for y_news in fetch_yahoo_news(ticker_input)[:4]:
                        y_title_ko = translate_text(y_news.get('title', ''))
                        st.info(f"🔹 **[{y_news.get('publisher')}]** {y_title_ko}\n\n[링크 이동]({y_news.get('link')})")
                else:
                    for n in news_data:
                        card_class = "news-card"
                        badge_html = ""
                        
                        if n['sentiment'] == "Positive":
                            card_class += " pos-card"
                            badge_html = "<span style='color:#10b981; font-weight:bold;'>🟢 Rhea-AI 호재 (Positive)</span>"
                        elif n['sentiment'] == "Negative":
                            card_class += " neg-card"
                            badge_html = "<span style='color:#ef4444; font-weight:bold;'>🔴 Rhea-AI 악재 (Negative)</span>"
                        elif n['sentiment'] == "Neutral":
                            card_class += " neu-card"
                            badge_html = "<span style='color:#f59e0b; font-weight:bold;'>🟡 Rhea-AI 중립 (Neutral)</span>"
                        else:
                            badge_html = "<span style='color:#9ca3af;'>⚪ Rhea-AI 분석 대기</span>"
                            
                        if n['impact'] == "High Impact":
                            badge_html += " <span class='impact-badge'>⚡ HIGH IMPACT</span>"
                        
                        # 뉴스 카드 렌더링 (영어 원문은 마우스 오버 툴팁이나 작은 캡션으로 처리 가능)
                        st.markdown(f"""
                        <div class="{card_class}">
                            <p style='font-size:12px; color:#9ca3af; margin-bottom:5px;'>📅 {n['date']} | {badge_html}</p>
                            <h5 style='margin-top:0; margin-bottom:5px; font-size:15px; line-height:1.4; color:#ffffff;'>{n['title']}</h5>
                            <p style='font-size:11px; color:#9ca3af; margin-bottom:10px; font-style:italic;'>원문: {n['title_en']}</p>
                            <a href="{n['link']}" target="_blank" style='color:#60a5fa; text-decoration:none; font-size:13px;'>🔍 스톡타이탄에서 원문 정보 보기 →</a>
                        </div>
                        """, unsafe_allow_html=True)