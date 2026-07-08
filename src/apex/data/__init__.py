"""Data Layer — M4 스켈레톤용 **결정론적 합성 피닝 스냅샷**.

실 yfinance raw 수집·로컬 TR 조정은 M4.5(08 §3). 스켈레톤은 플럼빙·강등 루프·재현성을
증명하는 게 목표이므로, 공통 시장팩터 + 티커별 idiosyncratic으로 상관을 반영한
**결정론적**(시드 고정) 합성 수익률을 "피닝 조정종가" 대역으로 쓴다.

`DATA_VERSION`을 바꾸면 스냅샷이 바뀐다(재현성 스코프 = 핀 고정 스냅샷).
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

DATA_VERSION = "synthetic-v1"
N_DAYS = 5040  # ≈ 20년 (252 × 20)
TRADING_DAYS = 252
_BASE_SEED = 20260707  # 리터럴 시드(플랫폼·시간 무관) — 결정론 보장

# 티커별 (시장베타, 알파_연율, idio_연율). 통상 범위 손추정(M5 실측 전).
# drift(수익추세)는 낮게 — 실측처럼 연율 VaR tail이 유의미하게 나오도록(스켈레톤 튜닝).
_TICKERS: dict[str, tuple[float, float, float]] = {
    "SPY": (1.00, 0.010, 0.05),
    "QQQ": (1.25, 0.015, 0.09),
    "EFA": (0.95, 0.005, 0.08),
    "EEM": (1.10, 0.005, 0.13),
    "IEF": (-0.15, 0.015, 0.05),
    "TLT": (-0.35, 0.010, 0.10),
    "AGG": (-0.05, 0.015, 0.04),
    "SHY": (0.00, 0.010, 0.012),
    "GLD": (0.10, 0.020, 0.14),
}
_MARKET_MU, _MARKET_SIGMA = 0.03, 0.20


@lru_cache(maxsize=4)
def _market_returns(n_days: int) -> np.ndarray:
    rng = np.random.default_rng(_BASE_SEED)
    return rng.normal(_MARKET_MU / TRADING_DAYS, _MARKET_SIGMA / np.sqrt(TRADING_DAYS), n_days)


@lru_cache(maxsize=64)
def pinned_ticker_returns(ticker: str, n_days: int = N_DAYS) -> np.ndarray:
    """결정론적 합성 일별 수익률(피닝 스냅샷 대역). 동일 티커 → 항상 동일 시계열.

    결정론이라 캐시(재현성 유지). 호출자는 반환 배열을 변형하지 않는다(읽기 전용).
    """
    beta, alpha, idio = _TICKERS[ticker]
    market = _market_returns(n_days)
    idx = sorted(_TICKERS).index(ticker)
    rng = np.random.default_rng(_BASE_SEED + 1 + idx)
    noise = rng.normal(0.0, idio / np.sqrt(TRADING_DAYS), n_days)
    return alpha / TRADING_DAYS + beta * market + noise


def portfolio_returns(weights: dict[str, float], n_days: int = N_DAYS) -> np.ndarray:
    """비중 가중 포트폴리오 일별 수익률(일별 리밸런싱 근사)."""
    arr = np.zeros(n_days)
    for ticker, w in weights.items():
        arr += w * pinned_ticker_returns(ticker, n_days)
    return arr


def build_return_series(
    returns: np.ndarray,
    *,
    currency: str,
    data_version: str = DATA_VERSION,
    index: pd.DatetimeIndex | None = None,
) -> pd.Series:
    """ReturnSeries 파케이 계약(08 §3 M4) 준수 객체 생성 + 검증.

    tz-aware DatetimeIndex · 단일 float64 `ret` · NaN 금지 · 메타(currency, data_version).
    ``index``=None이면 영업일 근사(합성 M4); 실데이터(M5)는 실 거래일 인덱스를 주입.
    """
    if index is None:
        idx = pd.bdate_range("2005-01-03", periods=len(returns), tz="UTC")
    else:
        idx = pd.DatetimeIndex(index)
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
    s = pd.Series(np.asarray(returns, dtype="float64"), index=idx, name="ret")
    s.attrs["currency"] = currency
    s.attrs["data_version"] = data_version
    validate_return_series(s)
    return s


def validate_return_series(s: pd.Series) -> None:
    """ReturnSeries 계약 검증. 위반 = 하드 실패(backtest 출력·risk 입력 로드 시)."""
    if not isinstance(s.index, pd.DatetimeIndex) or s.index.tz is None:
        raise ValueError("ReturnSeries: tz-aware DatetimeIndex 필요")
    if s.dtype != np.float64:
        raise ValueError(f"ReturnSeries: float64 단일 컬럼 필요(현재 {s.dtype})")
    if s.name != "ret":
        raise ValueError("ReturnSeries: 컬럼명 'ret' 필요")
    if bool(s.isna().any()):
        raise ValueError("ReturnSeries: NaN 금지(fill은 M4 게이트①)")
    if "currency" not in s.attrs or "data_version" not in s.attrs:
        raise ValueError("ReturnSeries: currency·data_version 메타 필요")
