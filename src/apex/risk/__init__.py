"""Risk Engine — ReturnSeries + Allocation → RiskReport (05 §1·§4).

바인딩 지표 `var95_annual`(R5) 포함. 합성 스냅샷엔 위기 구간이 없어 평시≈전구간(스켈레톤).
실 위기 3구간 제외 평시 산출은 M5(08 §3).
"""
from __future__ import annotations

import pandas as pd

from apex import data, metrics
from apex.schemas import Allocation, Concentration, RiskReport

# 티커 → 대분류 (집중도용, 07 §1)
_ASSET_CLASS = {
    "SPY": "EQ", "QQQ": "EQ", "EFA": "EQ", "EEM": "EQ",
    "IEF": "BOND", "TLT": "BOND", "AGG": "BOND",
    "SHY": "CASH", "GLD": "GOLD",
}


def report(series: pd.Series, alloc: Allocation, display_currency: str = "KRW") -> RiskReport:
    """ReturnSeries → RiskReport. 로드 시 ReturnSeries 계약 검증(하드 실패)."""
    data.validate_return_series(series)
    ret = series.to_numpy()

    by_class: dict[str, float] = {}
    for t, w in alloc.weights.items():
        by_class[_ASSET_CLASS[t]] = by_class.get(_ASSET_CLASS[t], 0.0) + w

    return RiskReport(
        calc_currency=series.attrs["currency"],
        display_currency=display_currency,
        vol_annual=metrics.vol_annual(ret),
        mdd=metrics.mdd(ret),
        var95_1d=metrics.var95_1d(ret),
        cvar95_1d=metrics.cvar95_1d(ret),
        var95_annual=metrics.var95_annual(ret),
        sharpe=metrics.sharpe(ret),
        calmar=metrics.calmar(ret),
        currency_exposure={"USD": 1.0},  # 전 슬롯 USD 표시(EFA/EEM도 USD ETF)
        concentration=Concentration(
            max_asset_class=max(by_class.values()),
            max_etf=max(alloc.weights.values()),
        ),
    )
