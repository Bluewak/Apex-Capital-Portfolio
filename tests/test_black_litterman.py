"""Black-Litterman (v3-B) — 시총균형 prior·null-view 항등성·뷰 방향. 네트워크 없음."""
from __future__ import annotations

import numpy as np

from apex import black_litterman as bl
from apex.schemas import CMASet


def _cma(n=5):
    tickers = [f"S{i}" for i in range(n)]
    mu = {t: 0.06 + 0.01 * i for i, t in enumerate(tickers)}
    vol = [0.15 + 0.02 * i for i in range(n)]
    cov = [[(0.3 if i != j else 1.0) * vol[i] * vol[j] for j in range(n)] for i in range(n)]
    return CMASet(tickers=tickers, mu=mu, vol={t: vol[i] for i, t in enumerate(tickers)},
                  cov=cov, shrinkage=0.1, as_of="2026-07-20", data_version="dv",
                  cma_version="scma-test")


def test_null_view_posterior_is_prior_exactly():
    cma = _cma()
    pi = cma.mu_vec()
    post = bl.posterior(pi, cma.cov_mat(), None)
    assert np.allclose(post, pi, atol=1e-12)
    # blend에서 신호 없음 → GK μ 정확
    mu = bl.blend(cma, {})
    assert np.allclose([mu[t] for t in cma.tickers], pi, atol=1e-12)


def test_positive_view_raises_and_negative_lowers_target_mu():
    cma = _cma()
    base = cma.mu
    up = bl.blend(cma, {"S1": "strong_pos"})
    dn = bl.blend(cma, {"S1": "strong_neg"})
    assert up["S1"] > base["S1"]
    assert dn["S1"] < base["S1"]


def test_build_views_filters_neutral_and_unknown():
    cma = _cma()
    assert bl.build_views({}, cma.tickers) is None
    assert bl.build_views({"S0": "neutral"}, cma.tickers) is None      # 중립 제외
    assert bl.build_views({"NOPE": "pos"}, cma.tickers) is None        # 미지 티커 제외
    v = bl.build_views({"S0": "pos", "S2": "neg"}, cma.tickers)
    assert v is not None and v[0].shape == (2, len(cma.tickers))       # P: 2×n


def test_equilibrium_returns_and_mktcap_weights():
    cma = _cma()
    w = bl.mktcap_weights(cma.tickers, {t: 100.0 for t in cma.tickers})
    assert np.isclose(w.sum(), 1.0)
    pi = bl.equilibrium_returns(cma.cov_mat(), w)
    assert pi.shape == (len(cma.tickers),)
