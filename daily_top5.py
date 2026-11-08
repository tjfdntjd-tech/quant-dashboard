"""
관심종목 엑셀 → 단기 모멘텀 점수 TOP 5 → 텔레그램 전송

사용법
  python daily_top5.py              # 계산 후 텔레그램 전송
  python daily_top5.py --dry-run    # 전송 없이 화면에만 출력
  python daily_top5.py --test       # 텔레그램 연결 테스트 메시지만 전송

필요 환경변수 (또는 같은 폴더의 .env 파일)
  TELEGRAM_BOT_TOKEN=123456:ABC...
  TELEGRAM_CHAT_ID=123456789
  WATCHLIST_PATH=C:\\Users\\tjfdn\\quant-dashboard\\관심종목_섹터별.xlsx   (선택, 기본: 스크립트 폴더)

주의: 거래량·추세·모멘텀 기반의 '선별 점수'이며 상승을 예측하거나 보장하지 않습니다.
"""
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent
KST = ZoneInfo("Asia/Seoul")
TOP_N = 5


# ────────────────────────── 설정 로딩 ──────────────────────────
def load_env():
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ────────────────────────── 엑셀 읽기 ──────────────────────────
def load_watchlist(path: Path) -> list[dict]:
    xl = pd.ExcelFile(path)
    sheet = "종목" if "종목" in xl.sheet_names else xl.sheet_names[0]
    # "NA"(Nano Labs) 티커가 결측치로 읽히지 않도록 기본 NA 변환을 끈다
    df = xl.parse(sheet, keep_default_na=False, na_values=[""])
    items, seen = [], set()
    for _, row in df.iterrows():
        t = row.get("티커")
        if pd.isna(t) or not str(t).strip():
            continue
        t = str(t).strip().upper()
        if t in seen:
            continue
        seen.add(t)
        name = row.get("종목명(한글)")
        sector = row.get("섹터")
        items.append({
            "ticker": t,
            "name": "" if pd.isna(name) else str(name).strip(),
            "sector": "미분류" if pd.isna(sector) else str(sector).strip(),
        })
    return items


# ────────────────────────── 시세 수집 ──────────────────────────
def download_prices(tickers: list[str]) -> dict[str, pd.DataFrame]:
    raw = yf.download(
        tickers, period="8mo", interval="1d", group_by="ticker",
        auto_adjust=False, threads=True, progress=False,
    )
    out = {}
    for t in tickers:
        try:
            df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            if len(df) >= 40:
                out[t] = df
        except Exception:
            continue
    return out


# ────────────────────────── 지표 / 점수 ──────────────────────────
def is_krw(ticker: str) -> bool:
    return ticker.endswith((".KS", ".KQ"))


def score_ticker(ticker: str, df: pd.DataFrame) -> dict | None:
    c, v = df["Close"], df["Volume"]
    last_date = df.index[-1]
    # 최근 7일 이상 거래 없는 종목(상폐/거래정지 의심)은 제외
    if (pd.Timestamp.now(tz=None).normalize() - pd.Timestamp(last_date).tz_localize(None).normalize()).days > 7:
        return None

    # 유동성 필터: 20일 평균 거래대금 (미국 $50만 / 한국 10억원 미만 제외)
    avg_value = float((c * v).tail(20).mean())
    if avg_value < (1e9 if is_krw(ticker) else 5e5):
        return None

    ma5, ma20 = c.rolling(5).mean(), c.rolling(20).mean()
    vol_ma20 = v.rolling(20).mean()

    delta = c.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))

    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    hist = macd - macd.ewm(span=9, adjust=False).mean()

    close = float(c.iloc[-1])
    chg1 = (close / float(c.iloc[-2]) - 1) * 100
    chg5 = (close / float(c.iloc[-6]) - 1) * 100
    vol_ratio20 = float(v.iloc[-1] / vol_ma20.iloc[-1] * 100) if vol_ma20.iloc[-1] > 0 else 0
    v3d, v3m = float(v.tail(3).mean()), float(v.tail(63).mean())
    surge = v3d / v3m if v3m > 0 else 0
    rsi_v = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else None

    tags, score = [], 0.0

    # 추세 (25)
    if close > ma5.iloc[-1]:
        score += 8
    if ma5.iloc[-1] > ma20.iloc[-1]:
        score += 9
        tags.append("정배열")
    if close > ma20.iloc[-1]:
        score += 8

    # 모멘텀 (20): 5일 수익률 0~15% 구간에서 비례 가점
    score += min(max(chg5, 0), 15) / 15 * 20
    if chg5 > 5:
        tags.append(f"5일 {chg5:+.1f}%")

    # 거래량 (25)
    score += min(max(vol_ratio20, 0), 300) / 300 * 15
    score += min(max(surge, 0), 3) / 3 * 10
    if vol_ratio20 >= 150:
        tags.append(f"거래량 20일평균의 {vol_ratio20 / 100:.1f}배")

    # MACD (15)
    if hist.iloc[-1] > 0:
        score += 8
    if hist.iloc[-1] > hist.iloc[-2]:
        score += 7
        tags.append("MACD 개선")

    # RSI (10)
    if rsi_v is None:
        score += 5
    elif 50 <= rsi_v <= 72:
        score += 10
    elif rsi_v <= 80 and rsi_v > 72:
        score += 10 - (rsi_v - 72) * 1.25
    elif rsi_v < 50:
        score += rsi_v / 50 * 5

    # 감점: 이미 과열된 급등 추격 / 동전주 리스크
    if chg1 >= 40:
        score -= 15
        tags.append("당일 급등 과열")
    if rsi_v is not None and rsi_v > 80:
        tags.append("RSI 과매수")
    if not is_krw(ticker) and close < 1:
        score -= 5
        tags.append("$1 미만(상폐 리스크)")

    return {
        "ticker": ticker, "close": close, "chg1": chg1, "chg5": chg5,
        "rsi": rsi_v, "score": round(max(score, 0), 1),
        "tags": tags[:3], "asof": pd.Timestamp(last_date).strftime("%m/%d"),
    }


# ────────────────────────── 메시지 / 전송 ──────────────────────────
def build_message(top: list[dict], scanned: int, total: int) -> str:
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    lines = [f"📈 오늘의 단기 모멘텀 TOP {len(top)}  ({now} KST)",
             f"관심종목 {total}개 중 {scanned}개 분석", ""]
    for i, r in enumerate(top, 1):
        unit = "₩" if is_krw(r["ticker"]) else "$"
        price = f"{unit}{r['close']:,.0f}" if is_krw(r["ticker"]) else f"{unit}{r['close']:,.2f}"
        lines.append(f"{i}. {r['ticker']} {r['name']}  [{r['sector']}]")
        lines.append(f"   {price} (1일 {r['chg1']:+.1f}%, 5일 {r['chg5']:+.1f}%) · 점수 {r['score']} · 기준 {r['asof']}")
        if r["tags"]:
            lines.append("   · " + " / ".join(r["tags"]))
        lines.append("")
    lines.append("⚠️ 거래량·추세 기반 참고용 선별입니다. 상승 보장이 아니며 투자 판단과 책임은 본인에게 있습니다.")
    return "\n".join(lines)


def send_telegram(text: str):
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        sys.exit("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 가 설정되지 않았습니다. (.env 파일 확인)")
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": text[:4000]}, timeout=20,
    )
    if not r.ok:
        sys.exit(f"텔레그램 전송 실패: {r.status_code} {r.text}")
    print("텔레그램 전송 완료")


# ────────────────────────── main ──────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()
    load_env()

    if args.test:
        send_telegram("✅ 텔레그램 연결 테스트 성공 (daily_top5.py)")
        return

    path = Path(os.environ.get("WATCHLIST_PATH", BASE_DIR / "관심종목_섹터별.xlsx"))
    if not path.exists():
        sys.exit(f"엑셀 파일을 찾을 수 없습니다: {path}")

    items = load_watchlist(path)
    meta = {it["ticker"]: it for it in items}
    prices = download_prices(list(meta))

    results = []
    for t, df in prices.items():
        r = score_ticker(t, df)
        if r:
            r["name"], r["sector"] = meta[t]["name"], meta[t]["sector"]
            results.append(r)

    if not results:
        msg = "⚠️ 오늘은 분석 가능한 종목 데이터를 가져오지 못했습니다. (네트워크/yfinance 확인)"
    else:
        results.sort(key=lambda x: x["score"], reverse=True)
        msg = build_message(results[:TOP_N], len(results), len(items))

    print(msg)
    if not args.dry_run:
        send_telegram(msg)


if __name__ == "__main__":
    main()
