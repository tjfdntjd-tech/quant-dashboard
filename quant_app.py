import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import plotly.graph_objects as go
from deep_translator import GoogleTranslator  # 번역 라이브러리 추가

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

# 2. 사이드바 - 티커 입력 및 파라미터 설정
st.sidebar.header("🔍 주식 분석 설정")
ticker_input = st.sidebar.text_input("티커명을 입력하세요 (예: NVDA, AAPL)", value="NVDA").upper()
search_button = st.sidebar.button("실시간 정밀 검증 시작")

# 3. 스톡타이탄 Rhea-AI 감성 분석 및 뉴스 크롤링 함수
def get_stock_titan_data(ticker):
    url = f"https://www.stocktitan.net/overview/{ticker}/"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        news_list = []
        
        # 스톡타이탄 뉴스 목록 가져오기
        articles = soup.find_all('div', class_='news-item') or soup.find_all('article')
        
        for art in articles[:5]:  # 상위 5개 최신 뉴스
            link_tag = art.find('a')
            if not link_tag: continue
            
            title = link_tag.text.strip()
            link = "https://www.stocktitan.net" + link_tag['href'] if not link_tag['href'].startswith('http') else link_tag['href']
            
            date_tag = art.find('div', class_='date') or art.find('span', class_='date')
            date_str = date_tag.text.strip() if date_tag else datetime.today().strftime('%b %d, %Y')
            
            # --- 실시간 한글 번역 적용 ---
            try:
                title_ko = GoogleTranslator(source='en', target='ko').translate(title)
            except:
                title_ko = title  # 번역 실패 시 원문 유지
            
            # --- Rhea-AI 상세 페이지 감성지수 추가 크롤링 ---
            sentiment = "Unknown"
            impact = "Normal"
            try:
                detail_resp = requests.get(link, headers=headers)
                if detail_resp.status_code == 200:
                    detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
                    
                    # Rhea-AI 태그 탐색
                    sentiment_box = detail_soup.find(class_=lambda x: x and 'sentiment' in x.lower())
                    if sentiment_box:
                        text = sentiment_box.text.lower()
                        if 'positive' in text: sentiment = "Positive"
                        elif 'negative' in text: sentiment = "Negative"
                        elif 'neutral' in text: sentiment = "Neutral"
                    
                    # Impact 강도 확인
                    if 'high impact' in detail_soup.text.lower():
                        impact = "High Impact"
            except:
                pass
            
            news_list.append({
                "date": date_str,
                "title": title_ko,  # 번역된 제목 저장
                "title_en": title,  # 툴팁이나 대조용 원문 저장
                "link": link,
                "sentiment": sentiment,
                "impact": impact
            })
        return news_list
    except Exception as e:
        return []

# 4. 메인 대시보드 로직
if ticker_input:
    with st.spinner("야후 파이낸스 및 스톡타이탄에서 실시간 데이터를 분석 중입니다..."):
        # [A] 수급 및 주가 데이터 수집
        stock = yf.Ticker(ticker_input)
        hist = stock.history(period="1y")
        
        if hist.empty:
            st.error("❌ 올바르지 않은 티커명이거나 데이터를 불러올 수 없습니다. 영문 티커를 확인해 주세요.")
        else:
            hist = hist.dropna() # 데이터 NaN 제거
            
            # 기술적 지표 계산
            hist['MA5'] = hist['Close'].rolling(window=5).mean()
            hist['MA20'] = hist['Close'].rolling(window=20).mean()
            hist['MA120'] = hist['Close'].rolling(window=120).mean()
            
            today = hist.iloc[-1]
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
                
                # 상단 메트릭 스퀘어
                m1, m2 = st.columns(2)
                with m1:
                    st.metric("현재가 (Close)", f"${today['Close']:.2f}", f"{(today['Close']-yesterday['Close'])/yesterday['Close']*100:.2f}%")
                with m2:
                    st.metric("52주 최고가", f"${high_52w:.2f}", f"현재 격차 {((high_52w-today['Close'])/high_52w)*100:.1f}%")
                
                st.markdown("---")
                
                # 1번 조건 검증: 거래량 & 거래대금
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
                
                # 이평선 정배열 상태 진단
                st.markdown("#### 📈 이동평균선 배열 상태")
                if today['MA5'] > today['MA20'] > today['MA120']:
                    st.info("🔥 **완전 정배열 상태:** 강력한 상승 추세를 유지하고 있습니다.")
                elif today['Close'] > today['MA120'] and yesterday['Close'] <= yesterday['MA120']:
                    st.success("🚀 **장기 이평선 돌파:** 120일선을 강력하게 뚫어 올린 급등 초입 타점!")
                else:
                    st.write("📊 현재 이평선 밀집 및 에너지를 응축 중인 횡보 구간입니다.")
                
                # 고급 인터랙티브 차트 구현
                fig = go.Figure()
                plot_df = hist.tail(60)
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Close'], name='주가', line=dict(color='#3b82f6', width=2)))
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], name='20일선', line=dict(color='#f59e0b', width=1.5)))
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA120'], name='120일선', line=dict(color='#ef4444', width=1.5)))
                fig.update_layout(title=f"{ticker_input} 최근 60일 추세선", template="plotly_dark", height=300, margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig, use_container_width=True)
                
            # ----------------- 오른쪽 컬럼: 스톡타이탄 뉴스 & Rhea-AI 호재 검증 -----------------
            with col2:
                st.subheader("🔥 스톡타이탄 실시간 호재 & Rhea-AI 분석 (국문 번역)")
                
                news_data = get_stock_titan_data(ticker_input)
                
                if not news_data:
                    st.write("📢 스톡타이탄에서 최근 공시 뉴스를 크롤링하지 못했습니다. 대안으로 야후 파이낸스 실시간 뉴스를 노출합니다.")
                    for y_news in stock.news[:4]:
                        try:
                            y_title_ko = GoogleTranslator(source='en', target='ko').translate(y_news.get('title'))
                        except:
                            y_title_ko = y_news.get('title')
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