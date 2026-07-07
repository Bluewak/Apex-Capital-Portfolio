"""Backtest Engine — Allocation → BacktestResult + ReturnSeries (05 §2).

M4 스켈레톤: 피닝 합성 스냅샷(data)으로 CAGR·MDD·누적 산출.
실 20년 벤치마크 3종·스트레스 3구간은 M5(08 §3). disclosed 스트레스는 참고(차단 아님, R3).
"""
from __future__ import annotations

import pandas as pd

from apex import data, metrics
from apex.schemas import Allocation, BacktestResult, Period, ScenarioResult


def run(alloc: Allocation, currency: str = "USD") -> tuple[BacktestResult, pd.Series]:
    """Allocation → (BacktestResult, ReturnSeries). ReturnSeries는 risk 입력 계약(08 §3 M4)."""
    ret = data.portfolio_returns(alloc.weights)
    series = data.build_return_series(ret, currency=currency)

    # disclosed 스트레스(참고): 합성 구간의 최악 롤링 1년 손실 1건(실 2008/2020/2022는 M5)
    worst_1y = metrics.var95_annual(ret)  # 근사 대역
    result = BacktestResult(
        currency_calc=currency,
        period=Period(start=str(series.index[0].date()), end=str(series.index[-1].date())),
        returns_daily_ref=f"{series.attrs['data_version']}:{alloc.profile}",
        cagr=metrics.cagr(ret),
        cumulative=metrics.cumulative(ret),
        scenarios=[ScenarioResult(name="worst_1y (synthetic, disclosed)", loss=-worst_1y)],
    )
    return result, series
