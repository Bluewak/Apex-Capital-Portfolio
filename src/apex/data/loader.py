"""실 스냅샷 로더 (M5): raw → 로컬 TR → 정렬 → 분기 리밸 포트 수익률 + 평시/스트레스 분리.

M4.5 대사를 통과한 로컬 TR 엔진(adjust)을 실 raw(snapshot.fetch_raw)에 적용해
포트폴리오 백테스트 입력을 만든다. 거래비용·리밸·환산 상수는 08 §4-6.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from apex.data import snapshot
from apex.data.adjust import local_tr_returns
from apex.scenarios import STRESS_WINDOWS, normal_mask, window_drawdown

# 거래비용(편도) 기본 상수 (08 §4-6: 0 또는 편도 5bps). 리밸 회전율에 적용.
DEFAULT_COST_BPS = 0.0005

__all__ = [
    "STRESS_WINDOWS",
    "window_drawdown",
    "load_ticker_returns",
    "load_returns_matrix",
    "portfolio_returns_quarterly",
    "split_normal_stress",
    "DEFAULT_COST_BPS",
]


def load_ticker_returns(
    ticker: str, start: str = "2005-01-01", end: str | None = None
) -> pd.Series:
    """단일 티커 raw → 로컬 TR 일별 수익률 Series (tz-naive 날짜 인덱스)."""
    df = snapshot.fetch_raw(ticker, start, end)
    df = df.dropna(subset=["Close"])
    df = df[df["Close"] > 0]
    close = df["Close"].to_numpy(dtype=float)

    def _col(name: str) -> np.ndarray:
        return df[name].fillna(0).to_numpy(dtype=float) if name in df else np.zeros(len(df))

    div = _col("Dividends")
    capg = _col("Capital Gains")
    ret = local_tr_returns(close, div, np.zeros(len(df)), capg)  # Close 분할조정 전제
    idx = df.index[1:].tz_localize(None).normalize()
    return pd.Series(ret, index=idx, name=ticker)


def load_returns_matrix(
    tickers: tuple[str, ...], start: str = "2005-01-01", end: str | None = None
) -> pd.DataFrame:
    """여러 티커를 공통 거래일(inner join)로 정렬한 일별 수익률 행렬."""
    cols = [load_ticker_returns(t, start, end) for t in tickers]
    mat = pd.concat(cols, axis=1, join="inner").dropna()
    return mat


def portfolio_returns_quarterly(
    returns: pd.DataFrame, weights: dict[str, float], cost_bps: float = 0.0
) -> pd.Series:
    """분기말 리밸런싱 포트폴리오 일별 수익률 (08 §4-6: 리밸=분기말).

    목표비중에서 일간 드리프트 → 분기 경계에서 목표로 복귀. ``cost_bps``(편도)는
    리밸 회전율(Σ|목표−드리프트|/2)에 적용해 해당일 수익에서 차감.
    """
    cols = list(weights.keys())
    mat = returns[cols].to_numpy()
    dates = returns.index
    w0 = np.array([weights[c] for c in cols], dtype=float)
    cur = w0.copy()
    out = np.empty(len(dates))
    for i in range(len(dates)):
        r = mat[i]
        out[i] = float(np.dot(cur, r))
        grown = cur * (1.0 + r)
        cur = grown / grown.sum()
        if i + 1 < len(dates) and dates[i + 1].quarter != dates[i].quarter:
            turnover = float(np.abs(w0 - cur).sum()) / 2.0  # 편도 회전율
            out[i] -= turnover * cost_bps  # 거래비용 차감
            cur = w0.copy()  # 분기말 리밸
    return pd.Series(out, index=dates, name="port")


def split_normal_stress(series: pd.Series) -> tuple[np.ndarray, dict[str, pd.Series]]:
    """평시(위기 3구간 제외) 수익률 + 구간별 수익률 (05 §3 R3 평시 판정)."""
    windows: dict[str, pd.Series] = {}
    idx = series.index
    for name, (lo, hi) in STRESS_WINDOWS.items():
        in_win = (idx >= pd.Timestamp(lo)) & (idx <= pd.Timestamp(hi))
        windows[name] = series[in_win]
    return series.to_numpy()[normal_mask(idx)], windows
