"""Tier 0 종목 룩스루 분석 (v3-A Step 1) — 실효 노출·집중도·단일종목 경고. 네트워크 없음."""
from __future__ import annotations

from apex import graph, lookthrough

_HOLD = {"SPY": {"NVDA": 0.10, "AAPL": 0.08}, "QQQ": {"NVDA": 0.12, "MSFT": 0.06}}
_MEM = {
    "NVDA": {"theme_group": "AI_HW", "subtheme": "AI_HW.SEMI"},
    "AAPL": {"theme_group": "AI_HW", "subtheme": "AI_HW.HW"},
    "MSFT": {"theme_group": "SW_CLD", "subtheme": "SW_CLD.SYS"},
}


def test_stock_exposure_weighted_no_double_count():
    eff, cov = graph.stock_exposure_lookthrough(
        {"SPY": 0.5, "QQQ": 0.5}, _HOLD, {"NVDA", "AAPL", "MSFT"})
    assert eff["NVDA"] == 0.11        # 0.5*0.10 + 0.5*0.12
    assert eff["AAPL"] == 0.04
    assert eff["MSFT"] == 0.03
    assert cov == 0.18               # 0.5*0.18 + 0.5*0.18


def test_direct_stock_full_coverage():
    eff, cov = graph.stock_exposure_lookthrough(
        {"NVDA": 0.3, "SPY": 0.7}, _HOLD, {"NVDA", "AAPL", "MSFT"})
    assert eff["NVDA"] == 0.3 + 0.7 * 0.10
    assert round(cov, 6) == round(0.3 + 0.7 * 0.18, 6)


def test_non_holdings_etf_skipped_from_coverage():
    """holdings 없는 ETF(채권 IEF)·미지 티커는 미분해 → 커버리지 제외."""
    eff, cov = graph.stock_exposure_lookthrough(
        {"IEF": 0.5, "SPY": 0.5}, _HOLD, {"NVDA", "AAPL"})
    assert "IEF" not in eff
    assert round(cov, 6) == round(0.5 * 0.18, 6)


def test_analyze_concentration_and_theme():
    rep = lookthrough.analyze({"SPY": 0.5, "QQQ": 0.5}, _HOLD, _MEM)
    assert rep.concentration.top_stock == "NVDA"
    assert rep.concentration.top_weight == 0.11
    assert rep.concentration.n_stocks == 3
    # 테마 룩스루: NVDA+AAPL→AI_HW, MSFT→SW_CLD
    assert round(rep.theme_exposure["AI_HW"], 4) == round(0.11 + 0.04, 4)
    assert round(rep.theme_exposure["SW_CLD"], 4) == 0.03


def test_analyze_flags_single_stock_breach():
    rep = lookthrough.analyze({"QQQ": 1.0}, {"QQQ": {"NVDA": 0.30}}, _MEM,
                              single_stock_cap=0.10)
    assert len(rep.breaches) == 1
    b = rep.breaches[0]
    assert b.metric == "stock_concentration:NVDA" and b.actual == 0.30
    assert b.because == ["NVDA"]


def test_analyze_breach_boundary_by_cap():
    """cap 0.10이면 NVDA 0.11>0.10 → 경고 1건, cap 0.15면 경고 없음(경계)."""
    assert len(lookthrough.analyze({"SPY": 0.5, "QQQ": 0.5}, _HOLD, _MEM,
                                   single_stock_cap=0.10).breaches) == 1
    assert lookthrough.analyze({"SPY": 0.5, "QQQ": 0.5}, _HOLD, _MEM,
                               single_stock_cap=0.15).breaches == []


def test_coverage_is_partial_and_honest():
    rep = lookthrough.analyze({"SPY": 1.0}, _HOLD, _MEM)
    assert rep.coverage == 0.18     # top-N 합(<1) — 부분 룩스루
