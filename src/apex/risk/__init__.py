"""Risk Engine — ReturnSeries + Allocation → RiskReport (05 §1·§4).

바인딩 지표 `var95_annual`(R5) 포함. 합성 스냅샷엔 위기 구간이 없어 평시≈전구간(스켈레톤).
실 위기 3구간 제외 평시 산출은 M5(08 §3).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from apex import data, metrics
from apex.scenarios import STRESS_WINDOWS, normal_mask, window_drawdown
from apex.schemas import Allocation, Concentration, PrecomputedEntry, RiskReport, StressResult
from apex.universe import ASSET_CLASS


def report(
    series: pd.Series,
    alloc: Allocation,
    display_currency: str = "KRW",
    normal_only: bool = False,
) -> RiskReport:
    """ReturnSeries → RiskReport. 로드 시 ReturnSeries 계약 검증(하드 실패).

    ``normal_only=True``(M5 실데이터): 상한 판정 지표(vol/MDD/var95_annual)를 **평시**
    (위기 3구간 제외)로 산출하고, 위기 구간 낙폭을 disclosed 스트레스로 채운다(R3).
    """
    data.validate_return_series(series)
    full = series.to_numpy()

    stress: list[StressResult] = []
    if normal_only:
        limit_ret = full[normal_mask(series.index)]
        naive = series.index.tz_localize(None) if series.index.tz is not None else series.index
        for name, (lo, hi) in STRESS_WINDOWS.items():
            in_win = np.asarray((naive >= pd.Timestamp(lo)) & (naive <= pd.Timestamp(hi)))
            if in_win.any():
                stress.append(StressResult(scenario=name, loss=window_drawdown(full[in_win])))
    else:
        limit_ret = full

    by_class: dict[str, float] = {}
    for t, w in alloc.weights.items():
        by_class[ASSET_CLASS[t]] = by_class.get(ASSET_CLASS[t], 0.0) + w

    return RiskReport(
        calc_currency=series.attrs["currency"],
        display_currency=display_currency,
        vol_annual=metrics.vol_annual(limit_ret),
        mdd=metrics.mdd(limit_ret),
        var95_1d=metrics.var95_1d(full),
        cvar95_1d=metrics.cvar95_1d(full),
        var95_annual=metrics.var95_annual(limit_ret),
        sharpe=metrics.sharpe(full),
        calmar=metrics.calmar(full),
        currency_exposure={"USD": 1.0},  # 전 슬롯 USD 표시(EFA/EEM도 USD ETF)
        concentration=Concentration(
            max_asset_class=max(by_class.values()),
            max_etf=max(alloc.weights.values()),
        ),
        stress=stress,
    )


def assemble(entry: PrecomputedEntry, display_currency: str = "KRW") -> RiskReport:
    """레지스트리 엔트리 → 서빙용 RiskReport (v2 §3.3).

    실현 RiskReport(disclosed·사전연산)에 **forward 기대손실**(compliance 차단 지표)과
    표시 통화를 오버레이. 20년 백테스트를 반복하지 않는 O(1) 조립.
    """
    base = entry.realized
    if base is None:
        raise ValueError("실현 RiskReport 없는 엔트리 — `apex model build`로 사전연산 필요")
    return base.model_copy(
        update={
            "display_currency": display_currency,
            "expected_loss_1y_forward": entry.forward.expected_loss_1y,
        }
    )
