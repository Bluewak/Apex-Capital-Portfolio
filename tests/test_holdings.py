"""ETF 보유종목 룩스루 (v2 E3) — ETF 포트 → 종목/테마 분해. 네트워크 없음(픽스처)."""
from __future__ import annotations

from apex import graph

_MEM = {
    "NVDA": {"theme_group": "AI_HW", "subtheme": "AI_HW.SEMI"},
    "AAPL": {"theme_group": "AI_HW", "subtheme": "AI_HW.HW"},
    "JPM": {"theme_group": "FIN", "subtheme": "FIN.BANK"},
}


def test_etf_lookthrough_decomposes_to_themes():
    """ETF 배정비중 × 보유비중 → 종목 테마(§8 분수, 이중계상 없음)."""
    etf_h = {"SPY": {"NVDA": 0.5, "JPM": 0.5}}
    exp = graph.theme_exposure_lookthrough({"SPY": 1.0}, _MEM, etf_h)
    assert exp == {"AI_HW": 0.5, "FIN": 0.5}


def test_lookthrough_mixes_etf_and_direct_stock():
    """ETF 룩스루 + 개별종목 직접 편입 혼합."""
    exp = graph.theme_exposure_lookthrough(
        {"SPY": 0.5, "AAPL": 0.5}, _MEM, {"SPY": {"NVDA": 1.0}}
    )
    assert exp == {"AI_HW": 1.0}  # SPY0.5×NVDA1.0 + AAPL0.5 직접 = AI_HW 1.0


def test_lookthrough_ignores_unmapped_foreign_holdings():
    """해외 보유종목(membership 밖)은 미집계 → 커버리지<100%(정직)."""
    exp = graph.theme_exposure_lookthrough({"EEM": 1.0}, _MEM, {"EEM": {"2330-TW": 1.0}})
    assert exp == {}


def test_bond_etf_no_holdings_contributes_nothing():
    exp = graph.theme_exposure_lookthrough({"IEF": 1.0}, _MEM, {"IEF": {}})
    assert exp == {}


def test_load_holdings_empty_when_absent(monkeypatch, tmp_path):
    from apex.data import holdings

    monkeypatch.setattr(holdings, "HOLDINGS_DIR", tmp_path / "none")
    assert holdings.load_holdings() == {}


def test_ensure_ascii_ca_noop_on_ascii(monkeypatch):
    """CA 경로가 ASCII면 env 무변경(멱등·no-op)."""
    import certifi

    from apex.data import netfix

    monkeypatch.setattr(certifi, "where", lambda: "/ascii/path/cacert.pem")
    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
    netfix.ensure_ascii_ca()
    import os

    assert os.environ.get("CURL_CA_BUNDLE") is None  # ASCII → 설정 안 함
