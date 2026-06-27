import re

import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from deep_translator import GoogleTranslator

# 1. 페이지 기본 설정
st.set_page_config(page_title="급등주 실시간 검증기", layout="wide")
st.title("🚀 급등주 조건 & 호재 실시간 검증 대시보드")

# 2. 사이드바 - 티커 입력 및 파라미터 설정
st.sidebar.header("🔍 주식 분석 설정")
ticker_input = st.sidebar.text_input("티커명을 입력하세요 (예: AAPL, NVDA, XMAX)", value="NVDA").upper()
search_button = st.sidebar.button("분석 시작")

# 3. 스톡타이탄 실시간 호재 크롤링 함수
def get_stock_titan_news(ticker):
    url = f"https://www.stocktitan.net/overview/{ticker}/"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        # [수정] status_index -> status_code (오타였습니다. status_index는 존재하지 않는
        # 속성이라 항상 예외가 발생 -> except로 빠져서 늘 빈 리스트를 반환하고 있었습니다.)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        news_list = []

        # [수정] 클래스명('news-item' 등)은 사이트 디자인이 바뀌면 쉽게 깨집니다.
        # 대신 스톡타이탄 기사 링크가 공통으로 갖는 URL 패턴
        #   /news/{티커}/제목-슬러그.html
        # 을 정규식으로 찾아서, 클래스명에 의존하지 않고 더 안정적으로 추출합니다.
        # (페이지네이션 링크인 /news/{티커}/page-2.html 같은 것은 제외)
        pattern = re.compile(
            rf"/news/{re.escape(ticker)}/(?!page-)[^/]+\.html$", re.IGNORECASE
        )
        anchors = soup.find_all('a', href=pattern)

        seen_links = set()
        for tag in anchors:
            title = tag.get_text(strip=True)
            href = tag.get('href')
            if not title or not href:
                continue
            if href.startswith('/'):
                href = "https://www.stocktitan.net" + href
            if href in seen_links:
                continue
            seen_links.add(href)
            # 개별 기사 발행일은 overview 페이지만으로는 안정적으로 가져오기 어려워서
            # 일단 빈 값으로 두고, 필요하면 기사 상세 페이지를 추가로 크롤링해서 채울 수 있습니다.
            news_list.append({"date": "", "title": title, "link": href})
            if len(news_list) >= 5:  # 최근 뉴스 5개만
                break

        return news_list
    except Exception:
        return []

# 4. A급 호재 키워드 매칭 함수
def check_keywords(title):
    keywords = ["Contract", "Partnership", "Agreement", "FDA", "Approval", "Acquisition", "Merger", "Insider", "Buy"]
    found = [kw for kw in keywords if kw.lower() in title.lower()]
    return found

# 4-0. 뉴스 제목을 한글로 번역하는 함수
# [추가] 키워드 탐지(check_keywords)는 항상 '번역 전' 영어 원문으로 먼저 수행해야 합니다.
# 번역을 먼저 하면 'Contract', 'FDA' 같은 키워드가 한글로 바뀌어서 더 이상 탐지가 안 됩니다.
# -> 그래서 아래 순서로 사용: ① 원문으로 키워드 탐지 -> ② 화면 표시용으로만 번역
@st.cache_data(ttl=3600, show_spinner=False)  # 같은 제목은 1시간 동안 캐시해서 번역 API 호출 절약
def translate_to_korean(text: str) -> str:
    if not text:
        return text
    try:
        return GoogleTranslator(source="auto", target="ko").translate(text)
    except Exception:
        # 번역 서버 오류/네트워크 문제 시, 원문을 그대로 보여줍니다 (앱이 죽지 않도록)
        return text

# 4-1. yfinance 뉴스 응답을 안전하게 파싱하는 함수
# [수정] 최신 yfinance는 .news 응답 구조가 바뀌어서, 데이터가 최상위가 아니라
# 'content' 키 안에 한 번 더 감싸진 형태로 옵니다. (KeyError: 'publisher'의 원인)
#   - 구버전: {'title': ..., 'publisher': ..., 'link': ...}
#   - 신버전: {'content': {'title': ..., 'provider': {'displayName': ...}, 'canonicalUrl': {'url': ...}}}
# 아래 함수는 두 구조를 모두 처리할 수 있도록 .get()으로 안전하게 꺼내옵니다.
def get_yfinance_news_safe(stock_obj, limit=3):
    try:
        raw_news = stock_obj.news or []
    except Exception:
        raw_news = []

    parsed = []
    for item in raw_news[:limit]:
        content = item.get("content", item)  # 신버전이면 content 안에서, 구버전이면 그대로
        title = content.get("title", "제목 없음")
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
        parsed.append({"title": title, "publisher": publisher, "link": link})
    return parsed

# 5. 메인 로직 실행
if search_button or ticker_input:
    with st.spinner("데이터를 가져오는 중입니다..."):
        # [A] 차트 및 수급 데이터 로드
        stock = yf.Ticker(ticker_input)
        hist = stock.history(period="1y") # 1년치 데이터
        
        if hist.empty:
            st.error("올바르지 않은 티커명이거나 데이터를 가져올 수 없습니다.")
        else:
            # 기술적 지표 계산
            hist['MA5'] = hist['Close'].rolling(window=5).mean()
            hist['MA20'] = hist['Close'].rolling(window=20).mean()
            hist['MA120'] = hist['Close'].rolling(window=120).mean()
            
            today = hist.iloc[-1]
            yesterday = hist.iloc[-2]
            
            # 52주 신고가 확인
            high_52w = hist['High'].max()
            is_near_high = "🔥 신고가 근접" if today['Close'] >= (high_52w * 0.95) else "일반 구간"

            # 거래량 급증 확인 (전일 거래량이 0인 비정상적인 경우 대비)
            vol_ratio = (today['Volume'] / yesterday['Volume']) * 100 if yesterday['Volume'] else 0
            
            # 레이아웃 분할
            col1, col2 = st.columns(2)
            
            # --- 왼쪽 컬럼: 수급 및 기술적 지표 점검 ---
            with col1:
                st.subheader("📊 기술적 조건 & 수급 점검")
                
                # 메트릭 표시
                st.metric("현재가 (종가)", f"${today['Close']:.2f}", f"{(today['Close']-yesterday['Close'])/yesterday['Close']*100:.2f}%")
                
                # 거래량 점검
                if vol_ratio >= 500:
                    st.success(f"✅ 거래량 폭발! 전일 대비 {vol_ratio:.1f}% 급증")
                else:
                    st.warning(f"⚠️ 거래량 보통 (전일 대비 {vol_ratio:.1f}%)")
                
                # 이평선 정배열/돌파 여부
                if today['Close'] > today['MA120'] and yesterday['Close'] <= yesterday['MA120']:
                    st.success("✅ 120일 장기 이평선 골든크로스 돌파!")
                elif today['MA5'] > today['MA20'] > today['MA120']:
                    st.info("📈 이동평균선 완전 정배열 상태 유지 중")
                else:
                    st.write("이평선 밀집/횡보 구간 분석 필요")
                
                # 52주 신고가 상태
                st.info(f"📍 52주 최고가: ${high_52w:.2f} ({is_near_high})")
                
                # 심플한 종가 차트 시각화
                st.line_chart(hist[['Close', 'MA20', 'MA120']].tail(60)) # 최근 60일 데이터
                
            # --- 오른쪽 컬럼: 스톡타이탄 실시간 뉴스 검증 ---
            with col2:
                st.subheader("🔥 스톡타이탄 실시간 호재(재료) 검증")
                news = get_stock_titan_news(ticker_input)
                
                if not news:
                    st.write("스톡타이탄에서 최근 공시/뉴스를 찾지 못했습니다. 야후 파이낸스 뉴스를 교차 확인하세요.")
                    # 대안으로 yfinance 뉴스 서빙
                    # [수정] y_news['publisher']로 바로 접근하면 신버전 구조에서 KeyError 발생
                    # -> get_yfinance_news_safe()로 신/구버전 모두 안전하게 처리
                    for y_news in get_yfinance_news_safe(stock, limit=3):
                        translated_title = translate_to_korean(y_news["title"])  # 한글로 번역해서 표시
                        if y_news["link"]:
                            st.write(f"🔹 **[{y_news['publisher']}]** [{translated_title}]({y_news['link']})")
                        else:
                            st.write(f"🔹 **[{y_news['publisher']}]** {translated_title}")
                else:
                    for idx, n in enumerate(news):
                        # ① 키워드 탐지는 영어 원문 제목으로 먼저 수행
                        detected_kws = check_keywords(n['title'])
                        # ② 화면에 보여줄 제목만 한글로 번역
                        translated_title = translate_to_korean(n['title'])

                        # 중요 키워드가 있으면 하이라이트
                        if detected_kws:
                            st.error(f"🚨 [A급 호재 탐지: {', '.join(detected_kws)}] {translated_title}")
                        else:
                            st.write(f"📄 {translated_title}")

                        with st.expander("🔎 영문 원문 보기"):
                            st.write(n['title'])

                        st.caption(f"발행일: {n['date']} | [스톡타이탄에서 원문 보기]({n['link']})")
                        st.write("---")