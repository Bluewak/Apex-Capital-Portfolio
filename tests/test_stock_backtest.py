"""이벤트 구동 종목 백테스트 (v3-A Step 2) — 리밸·가변 유니버스·상폐 현금화. 네트워크 없음."""
from __future__ import annotations

import numpy as np
import pandas as pd

from apex import stock_backtest


def _prices(n_days=260):
    idx = pd.bdate_range("2020-01-01", periods=n_days)
    # AAA +0.05%/일 복리, BBB +0.10%/일 — 결정론
    aaa = 100 * (1.0005 ** np.arange(n_days))
    bbb = 100 * (1.0010 ** np.arange(n_days))
    return pd.DataFrame({"AAA": aaa, "BBB": bbb}, index=idx)


def test_rebalance_dates_are_quarterly():
    px = _prices()
    rd = stock_backtest.rebalance_dates(px.index)
    assert len(rd) == 4  # 2020 4개 분기
    assert all(isinstance(d, pd.Timestamp) for d in rd)


def test_backtest_equal_weight_returns():
    px = _prices()
    def wf(universe, asof):
        return {t: 1.0 / len(universe) for t in universe}
    s = stock_backtest.backtest(px, wf)
    assert len(s) > 200
    # 두 종목 평균 성장 사이 → 총수익 양수, BBB 단독보다 작음
    tot = float((1 + s).prod() - 1)
    assert tot > 0


def test_variable_universe_excludes_non_members():
    px = _prices()
    def wf(universe, asof):
        return {t: 1.0 / len(universe) for t in universe}
    # BBB만 멤버 → AAA 제외
    s = stock_backtest.backtest(px, wf, members_asof=lambda asof: {"BBB"})
    s_bbb = px["BBB"].pct_change().loc[s.index]
    assert np.allclose(s.to_numpy(), s_bbb.to_numpy(), atol=1e-9)


def test_delisting_cash_out_applies_terminal_return():
    """보유 종목이 중간에 상폐(NaN) → 첫 결측일에 종료수익 적용 후 현금화."""
    px = _prices(60).copy()
    px.loc[px.index[30:], "BBB"] = np.nan  # BBB 31일째부터 상폐
    def wf(universe, asof):
        return {t: 1.0 / len(universe) for t in universe if t in universe}
    s = stock_backtest.backtest(px, wf, terminal_returns={"BBB": -0.5})
    # 상폐일 근처에 BBB의 −50% 종료수익이 포트에 반영(음의 튐 존재)
    assert s.min() < 0  # 종료수익 −50%가 포트 수익에 음수 충격
    assert s.notna().all()


def test_metrics_and_validate_baskets():
    px = _prices()
    def wf(u, a):
        return {t: 1.0 / len(u) for t in u}
    s = stock_backtest.backtest(px, wf)
    m = stock_backtest.metrics(s)
    assert m["cagr"] > 0 and m["vol_annual"] >= 0 and "psr_vs_zero" in m
    res = stock_backtest.validate_baskets({"a": s, "b": s})
    assert "sr_star_daily" in res and set(res["per_profile"]) == {"a", "b"}
