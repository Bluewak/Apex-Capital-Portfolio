"""표본 개별종목 주가 핀 (v3-A Step 2 · E2 부분).

yfinance로 **소량 표본**(대량은 야후 429)의 일별 종가를 수집·피닝. 종목 CMA(밸류에이션·
수익률)·공분산·백테스트의 가격 입력. 전 유니버스 풀은 데이터 벽(야후 429/유료) — 표본으로
엔진을 세우고 실데이터로 검증하는 정직 패턴(EDGAR 재무·종료수익과 동일).

**한계 각인**: yfinance auto_adjust 종가는 소급 분할·배당 조정(as-of 아님) → 백테스트
look-ahead 소지. 정밀 PIT 조정은 로컬 TR(adjust.py)로 후속. 표본 엔진 검증엔 충분.
라이브 fetch는 pull에서만(핀 우선). 비ASCII 경로 SSL은 netfix로 우회.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

PRICES_DIR = Path("artifacts/stock_prices")
PRICES_PATH = PRICES_DIR / "prices.json"

# 표본 = 대형 현행 S&P500 종목(EDGAR 재무·가격 커버리지 보장). 결정론(고정 리스트).
SAMPLE_TICKERS: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO",
    "JPM", "V", "UNH", "XOM", "JNJ", "WMT", "MA", "PG",
    "HD", "COST", "ABBV", "KO", "PEP", "ADBE", "CRM", "MRK",
)


def pull_prices(tickers: tuple[str, ...] = SAMPLE_TICKERS, period: str = "10y",
                pin: bool = True, delay: float = 0.5) -> dict:
    """표본 일별 종가 수집·피닝. yfinance 소량(딜레이로 429 회피). 실패 종목은 제외."""
    from apex.data.netfix import ensure_ascii_ca

    ensure_ascii_ca()
    import yfinance as yf

    prices: dict[str, dict] = {}
    for t in tickers:
        try:
            h = yf.Ticker(t).history(period=period, auto_adjust=True)
            if len(h) > 100:
                prices[t] = {"dates": [d.date().isoformat() for d in h.index],
                             "close": [round(float(c), 4) for c in h["Close"]]}
        except Exception:  # noqa: BLE001 — 소싱 실패 종목은 제외(부분 표본 허용)
            pass
        time.sleep(delay)
    import hashlib

    ver = hashlib.sha256(json.dumps({t: p["close"][-1] for t, p in prices.items()},
                                    sort_keys=True).encode()).hexdigest()[:12]
    out = {"prices_version": ver, "period": period, "n": len(prices),
           "tickers": sorted(prices), "prices": prices}
    if pin:
        PRICES_DIR.mkdir(parents=True, exist_ok=True)
        PRICES_PATH.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def load_prices() -> dict:
    """피닝된 주가. 부재 시 빈 dict(오프라인 안전)."""
    if not PRICES_PATH.exists():
        return {}
    return json.loads(PRICES_PATH.read_text(encoding="utf-8"))


def close_frame(prices_doc: dict):
    """핀 주가 → 종가 DataFrame(행=날짜, 열=티커, 정렬·정합)."""
    import pandas as pd

    cols = {}
    for t, p in prices_doc.get("prices", {}).items():
        cols[t] = pd.Series(p["close"], index=pd.to_datetime(p["dates"]))
    return pd.DataFrame(cols).sort_index()


def returns_matrix(prices_doc: dict):
    """핀 주가 → 일별 수익률 DataFrame(공통 구간 정합). CMA 공분산 입력."""
    px = close_frame(prices_doc)
    return px.pct_change().dropna(how="all").dropna(axis=1)
