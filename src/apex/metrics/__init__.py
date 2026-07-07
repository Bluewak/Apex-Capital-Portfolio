"""공유 계산 커널 (05). backtest·risk가 지표를 중복 구현하지 않도록 단일 소스.

모든 함수는 순수·결정론적(동일 입력 → 동일 출력). 수익률은 단순수익률(05 §0).
"""
from __future__ import annotations

import numpy as np

TRADING_DAYS = 252


def cagr(returns: np.ndarray, ppy: int = TRADING_DAYS) -> float:
    """연복리수익률."""
    cum = float(np.prod(1.0 + returns))
    years = len(returns) / ppy
    if years <= 0 or cum <= 0:
        return 0.0
    return cum ** (1.0 / years) - 1.0


def cumulative(returns: np.ndarray) -> float:
    """누적 성장배수 - 1 (전 구간 총수익)."""
    return float(np.prod(1.0 + returns) - 1.0)


def vol_annual(returns: np.ndarray, ppy: int = TRADING_DAYS) -> float:
    """일별 수익률 표준편차의 연율화 (05 §1.1)."""
    return float(np.std(returns, ddof=1) * np.sqrt(ppy))


def mdd(returns: np.ndarray) -> float:
    """최대낙폭 (05 §1.2). 음수."""
    cum = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(cum)
    dd = cum / peak - 1.0
    return float(dd.min())


def var95_1d(returns: np.ndarray) -> float:
    """1일 Historical VaR95, 양수 손실률 (05 §1.3)."""
    return float(-np.quantile(returns, 0.05))


def cvar95_1d(returns: np.ndarray) -> float:
    """1일 Historical CVaR95, 양수 손실률 (05 §1.4)."""
    q = np.quantile(returns, 0.05)
    tail = returns[returns <= q]
    return float(-tail.mean()) if tail.size else var95_1d(returns)


def var95_annual(returns: np.ndarray, window: int = TRADING_DAYS) -> float:
    """연율 VaR95 — Historical 롤링 1년 누적수익의 5% 분위수, 양수 손실률 (05 §1.3 R3 단일식).

    컴플라이언스 바인딩 지표(R5). 정규가정 없이 실측 분포만 사용.
    """
    if len(returns) <= window:
        # 데이터 부족 시 √기간 스케일 폴백(스켈레톤 한정, 실운영은 20년 확보로 미발생)
        return float(-np.quantile(returns, 0.05) * np.sqrt(window))
    logr = np.log1p(returns)
    clog = np.concatenate([[0.0], np.cumsum(logr)])
    roll = np.exp(clog[window:] - clog[:-window]) - 1.0  # 겹치는 1년 누적수익
    return float(-np.quantile(roll, 0.05))


def sharpe(returns: np.ndarray, rf_annual: float = 0.02, ppy: int = TRADING_DAYS) -> float:
    """Sharpe = (연평균수익 - 무위험) / 연변동성 (05 §1.6)."""
    v = vol_annual(returns, ppy)
    return float((cagr(returns, ppy) - rf_annual) / v) if v > 0 else 0.0


def calmar(returns: np.ndarray, ppy: int = TRADING_DAYS) -> float:
    """Calmar = 연평균수익 / |MDD| (05 §1.6)."""
    m = mdd(returns)
    return float(cagr(returns, ppy) / abs(m)) if m < 0 else 0.0
