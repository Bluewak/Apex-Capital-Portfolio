"""실 스냅샷 로더 (M5): raw → 로컬 TR → 정렬 → 분기 리밸 포트 수익률 + 평시/스트레스 분리.

M4.5 대사를 통과한 로컬 TR 엔진(adjust)을 실 raw(snapshot.fetch_raw)에 적용해
포트폴리오 백테스트 입력을 만든다. 거래비용·리밸·환산 상수는 08 §4-6.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from apex.data import snapshot
from apex.data.adjust import local_tr_returns

# 실측 스트레스 구간 (05 §2). 평시 판정에서 제외(R3: 스트레스는 공시, 차단은 평시).
STRESS_WINDOWS: dict[str, tuple[str, str]] = {
    "2008": ("2007-10-01", "2009-03-31"),
    "2020": ("2020-02-19", "2020-03-23"),
    "2022": ("2022-01-01", "2022-10-31"),
}


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


def portfolio_returns_quarterly(returns: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """분기말 리밸런싱 포트폴리오 일별 수익률 (08 §4-6: 리밸=분기말, 거래비용 0 가정).

    목표비중에서 일간 드리프트 → 분기 경계에서 목표로 복귀.
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
            cur = w0.copy()  # 분기말 리밸
    return pd.Series(out, index=dates, name="port")


def split_normal_stress(series: pd.Series) -> tuple[np.ndarray, dict[str, pd.Series]]:
    """평시(위기 3구간 제외) 수익률 + 구간별 수익률 (05 §3 R3 평시 판정)."""
    mask = pd.Series(True, index=series.index)
    windows: dict[str, pd.Series] = {}
    for name, (lo, hi) in STRESS_WINDOWS.items():
        in_win = (series.index >= pd.Timestamp(lo)) & (series.index <= pd.Timestamp(hi))
        windows[name] = series[in_win]
        mask &= ~in_win
    return series[mask].to_numpy(), windows


def window_drawdown(series: pd.Series) -> float:
    """구간 내 최대낙폭(peak-to-trough), 음수. 스트레스 공시용."""
    if series.empty:
        return 0.0
    cum = np.cumprod(1.0 + series.to_numpy())
    peak = np.maximum.accumulate(cum)
    return float((cum / peak - 1.0).min())
