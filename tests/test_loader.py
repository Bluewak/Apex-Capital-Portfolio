"""실 스냅샷 로더·게이트 단위 테스트 (M5). 네트워크 없음 — 픽스처."""
from __future__ import annotations

import numpy as np
import pandas as pd

from apex.data import loader
from apex.gate import GateRow


def _mat(dates, **cols) -> pd.DataFrame:
    return pd.DataFrame(cols, index=pd.DatetimeIndex(dates))


def test_portfolio_single_ticker_identity():
    """단일 티커 100% → 포트 수익률 == 그 티커 수익률(리밸 무관)."""
    dates = pd.bdate_range("2021-01-04", periods=5)
    mat = _mat(dates, A=[0.01, -0.02, 0.0, 0.03, -0.01], B=[0.0, 0.0, 0.0, 0.0, 0.0])
    port = loader.portfolio_returns_quarterly(mat, {"A": 1.0})
    assert np.allclose(port.to_numpy(), mat["A"].to_numpy())


def test_portfolio_first_day_weighted():
    """첫날은 목표비중 가중합(드리프트 전)."""
    dates = pd.bdate_range("2021-01-04", periods=2)
    mat = _mat(dates, A=[0.10, 0.0], B=[-0.10, 0.0])
    port = loader.portfolio_returns_quarterly(mat, {"A": 0.5, "B": 0.5})
    assert np.isclose(port.iloc[0], 0.0)  # 0.5*0.10 + 0.5*(-0.10)


def test_quarterly_rebalance_resets_at_boundary():
    """분기 경계에서 목표비중 복귀(에러 없이 전 구간 처리)."""
    dates = pd.to_datetime(["2021-03-30", "2021-03-31", "2021-04-01", "2021-04-02"])
    mat = _mat(dates, A=[0.5, 0.5, 0.5, 0.5], B=[-0.1, -0.1, -0.1, -0.1])
    port = loader.portfolio_returns_quarterly(mat, {"A": 0.5, "B": 0.5})
    assert len(port) == 4 and not port.isna().any()


def test_split_normal_stress_excludes_window():
    dates = pd.bdate_range("2020-01-02", "2020-04-30")
    s = pd.Series(0.001, index=dates)
    normal, windows = loader.split_normal_stress(s)
    lo, hi = pd.Timestamp("2020-02-19"), pd.Timestamp("2020-03-23")
    assert not windows["2020"].empty
    assert ((windows["2020"].index >= lo) & (windows["2020"].index <= hi)).all()
    # 평시 개수 = 전체 - 위기창
    in_win = (s.index >= lo) & (s.index <= hi)
    assert len(normal) == int((~in_win).sum())


def test_window_drawdown():
    s = pd.Series([0.10, -0.20, 0.05], index=pd.bdate_range("2008-10-01", periods=3))
    assert np.isclose(loader.window_drawdown(s), -0.20)


def test_gate_row_binding_is_var():
    """게이트 차단 판정은 var(R5). vol/mdd는 참고 플래그."""
    lim = {"vol": 0.06, "mdd": -0.10, "var": 0.08}
    ok = GateRow("안정형", vol=0.05, mdd_normal=-0.08, var_annual=0.07, lim=lim,
                 cagr_full=0.05, stress={})
    bad = GateRow("안정형", vol=0.05, mdd_normal=-0.08, var_annual=0.09, lim=lim,
                  cagr_full=0.05, stress={})
    assert ok.passed and not bad.passed
    assert ok.vol_ok and ok.mdd_ok
