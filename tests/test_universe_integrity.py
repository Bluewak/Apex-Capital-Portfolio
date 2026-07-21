"""유니버스 정합성 (v3-A 다지기) — 표본 전 층 연결·membership 2소스 일치. 핀 있으면 검사."""
from __future__ import annotations

import pytest

from apex.data.stock_prices import SAMPLE_TICKERS


def _norm_ok(t: str) -> bool:
    return t == t.strip().upper() and t != "" and t == t.replace(".", "-")


def test_sample_tickers_wellformed():
    """데이터 없이: 표본 티커가 고유·정규화(대문자·'.'→'-')·합리적 규모."""
    assert len(SAMPLE_TICKERS) == len(set(SAMPLE_TICKERS))   # 중복 없음
    assert all(_norm_ok(t) for t in SAMPLE_TICKERS)
    assert 10 <= len(SAMPLE_TICKERS) <= 100


def _load_layers():
    from apex.data.membership import load_membership
    from apex.data.membership_pit import load_membership_pit
    from apex.data.stock_prices import load_prices
    from apex.stock_cma import load_gk_inputs

    pit = load_membership_pit().get("stocks", {})
    theme = load_membership()
    prices = load_prices().get("prices", {})
    gk = load_gk_inputs()
    if not (pit and theme and prices and gk):
        pytest.skip("핀 부재 — membership/prices/gk 선행 필요")
    return pit, theme, prices, gk


def test_sample_universe_fully_connected_if_pinned():
    """표본 24종이 PIT현행·CIK·테마·주가·재무 전 층에 존재(갭 0)."""
    pit, theme, prices, gk = _load_layers()
    pit_current = {t for t, r in pit.items() if r["status"] == "current"}
    gaps = [t for t in SAMPLE_TICKERS
            if not (t in pit_current and pit.get(t, {}).get("cik")
                    and t in theme and t in prices and t in gk)]
    assert gaps == [], f"표본 유니버스 갭: {gaps}"


def test_pit_and_theme_membership_agree_on_current_if_pinned():
    """독립 2소스(GitHub 권위 PIT vs 위키 테마 E1) 현행 구성원 정확 일치 — 유니버스 골든."""
    pit, theme, _, _ = _load_layers()
    pit_current = {t for t, r in pit.items() if r["status"] == "current"}
    assert pit_current == set(theme), (
        f"membership 불일치: PIT만 {sorted(pit_current - set(theme))[:5]}, "
        f"테마만 {sorted(set(theme) - pit_current)[:5]}")
