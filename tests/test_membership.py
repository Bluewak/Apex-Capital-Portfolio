"""개별종목 KG 소속 (v2 E1) — 종목→테마 노출·근거경로. 네트워크 없음(픽스처)."""
from __future__ import annotations

from apex import graph

_MEM = {
    "NVDA": {"theme_group": "AI_HW", "subtheme": "AI_HW.SEMI"},
    "AMD": {"theme_group": "AI_HW", "subtheme": "AI_HW.SEMI"},
    "MSFT": {"theme_group": "SW_CLD", "subtheme": "SW_CLD.SYS"},
    "JPM": {"theme_group": "FIN", "subtheme": "FIN.BANK"},
}


def test_theme_group_exposure_aggregates_stocks():
    holdings = {"NVDA": 0.30, "AMD": 0.20, "JPM": 0.50}
    exp = graph.theme_exposure(holdings, _MEM)
    assert exp == {"AI_HW": 0.50, "FIN": 0.50}
    assert abs(sum(exp.values()) - 1.0) < 1e-9


def test_subtheme_level_and_because_path():
    holdings = {"NVDA": 0.3, "AMD": 0.2, "MSFT": 0.5}
    sub = graph.theme_exposure(holdings, _MEM, level="subtheme")
    assert sub["AI_HW.SEMI"] == 0.5 and sub["SW_CLD.SYS"] == 0.5
    assert graph.because_theme("AI_HW", holdings, _MEM) == ["AMD", "NVDA"]


def test_etf_without_lookthrough_excluded():
    """ETF는 보유종목 룩스루 데이터 부재 시 테마 집계에서 제외(E3, 개별종목분만)."""
    exp = graph.theme_exposure({"SPY": 0.5, "NVDA": 0.5}, _MEM)
    assert exp == {"AI_HW": 0.5}  # SPY 제외


def test_ticker_normalization():
    """BRK.B 형태 → BRK-B 정규화 매칭."""
    mem = {"BRK-B": {"theme_group": "FIN", "subtheme": "FIN.HOLD"}}
    assert graph.theme_exposure({"BRK.B": 1.0}, mem) == {"FIN": 1.0}


def test_load_membership_empty_when_absent(monkeypatch, tmp_path):
    from apex.data import membership as mem

    monkeypatch.setattr(mem, "MEMBERSHIP_DIR", tmp_path / "none")
    assert mem.load_membership() == {}
