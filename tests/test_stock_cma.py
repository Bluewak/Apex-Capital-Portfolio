"""종목 CMA (v3-A Step 2) — Grinold-Kroner μ·강한 shrink·constant-corr Σ. 네트워크 없음."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apex import stock_cma

_FUND = {
    "net_income": {"2018-12-31": {"val": 100}, "2019-12-31": {"val": 110},
                   "2023-12-31": {"val": 200}},
    "dividends_paid": {"2023-12-31": {"val": 10}},
    "buybacks": {"2023-12-31": {"val": 20}},
    "diluted_shares": {"2023-12-31": {"val": 1000}},
}


def test_gk_expected_return_components():
    gk = stock_cma.gk_expected_return(_FUND, last_price=5.0)  # mktcap=5000
    assert gk["div_yield"] == pytest.approx(0.002)      # 10/5000
    assert gk["buyback_yield"] == pytest.approx(0.004)  # 20/5000
    # cagr = 2^(1/5)-1 = 0.148698, shrunk = 0.35*0.148698 + 0.65*0.06
    assert gk["growth_raw"] == pytest.approx(0.148698, abs=1e-5)
    assert gk["growth_shrunk"] == pytest.approx(0.35 * 0.148698 + 0.65 * 0.06, abs=1e-5)
    assert gk["mu"] == pytest.approx(0.002 + 0.004 + gk["growth_shrunk"], abs=1e-5)


def test_growth_shrink_pulls_extremes_toward_prior():
    """폭발적 성장(clip 0.20)도 강하게 축소 → prior 근처(종목 μ 잡음 통제)."""
    hi = {**_FUND, "net_income": {"2013-12-31": {"val": 1}, "2018-12-31": {"val": 100},
                                  "2023-12-31": {"val": 1000}}}
    gk = stock_cma.gk_expected_return(hi, last_price=5.0)
    assert gk["growth_raw"] > 0.20                  # 원 cagr ≈0.995(clip 전)
    assert gk["growth_shrunk"] == pytest.approx(0.35 * 0.20 + 0.65 * 0.06)  # clip 0.20→축소 0.109


def test_cagr_falls_back_on_sign_change():
    assert stock_cma._cagr({"2020-12-31": {"val": -5}, "2021-12-31": {"val": 10},
                            "2022-12-31": {"val": 20}}) is None  # 음수 시작 → None


def test_ledoit_wolf_cc_is_psd_symmetric_and_preserves_diagonal():
    t = np.linspace(0, 8 * np.pi, 240)
    x = np.column_stack([np.sin(t), np.sin(t) + 0.3 * np.cos(2 * t), np.cos(t)]) * 0.01
    sig, delta = stock_cma.ledoit_wolf_cc(x)
    assert np.allclose(sig, sig.T)                     # 대칭
    assert np.linalg.eigvalsh(sig).min() >= -1e-12     # PSD
    assert 0.0 <= delta <= 1.0
    s = (x - x.mean(0)).T @ (x - x.mean(0)) / len(x)   # 표본공분산
    assert np.allclose(np.diag(sig), np.diag(s))       # 대각(분산) 보존 = identity 아님


def test_build_intersects_tickers_and_versions():
    rm = pd.DataFrame({"AAA": [0.01, -0.02, 0.03, 0.0, 0.01] * 20,
                       "BBB": [0.0, 0.01, -0.01, 0.02, 0.0] * 20})
    gk = {"AAA": {"mu": 0.10}, "BBB": {"mu": 0.08}, "CCC": {"mu": 0.05}}
    cma = stock_cma.build(rm, gk, data_version="dv1", as_of="2026-07-20")
    assert cma.tickers == ["AAA", "BBB"]     # 교집합·정렬(CCC는 가격 없음)
    assert cma.mu == {"AAA": 0.10, "BBB": 0.08}
    assert cma.cma_version.startswith("scma-")
