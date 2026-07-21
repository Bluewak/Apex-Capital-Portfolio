"""종목 optimizer (v3-A Step 2) — 캡·Σw=1·성향 λ 단조·집중도. 네트워크 없음."""
from __future__ import annotations

import pytest

from apex import stock_optimizer
from apex.schemas import CMASet
from apex.schemas.enums import Profile


def _cma(n=8):
    tickers = [f"S{i}" for i in range(n)]
    mu = {t: 0.06 + 0.01 * i for i, t in enumerate(tickers)}
    # 대각 우세 공분산(고번호일수록 고변동) — 결정론
    vol = [0.15 + 0.02 * i for i in range(n)]
    cov = [[(0.3 if i != j else 1.0) * vol[i] * vol[j] for j in range(n)] for i in range(n)]
    return CMASet(tickers=tickers, mu=mu, vol={t: vol[i] for i, t in enumerate(tickers)},
                  cov=cov, shrinkage=0.1, as_of="2026-07-20", data_version="dv",
                  cma_version="scma-test")


def test_weights_respect_cap_and_sum_to_one():
    w = stock_optimizer.optimize(_cma(), Profile.NEUTRAL, single_stock_cap=0.20)
    assert abs(sum(w.values()) - 1.0) < 1e-6
    assert all(-1e-9 <= v <= 0.20 + 1e-6 for v in w.values())


def test_profile_lambda_monotone_vol():
    """보수형(높은 λ) 바스켓 변동성 ≤ 공격형(낮은 λ)."""
    cma = _cma()
    w_cons = stock_optimizer.optimize(cma, Profile.ULTRA_CONSERVATIVE, single_stock_cap=0.25)
    w_aggr = stock_optimizer.optimize(cma, Profile.AGGRESSIVE, single_stock_cap=0.25)
    v_cons = stock_optimizer.basket_metrics(cma, w_cons)["vol"]
    v_aggr = stock_optimizer.basket_metrics(cma, w_aggr)["vol"]
    assert v_cons <= v_aggr + 1e-9


def test_cap_too_tight_raises():
    with pytest.raises(ValueError, match="캡 완화"):
        stock_optimizer.optimize(_cma(n=8), Profile.NEUTRAL, single_stock_cap=0.10)  # 0.10*8<1


def test_basket_metrics_fields():
    cma = _cma()
    w = stock_optimizer.optimize(cma, Profile.GROWTH, single_stock_cap=0.25)
    m = stock_optimizer.basket_metrics(cma, w)
    assert m["n_holdings"] == len(w)
    assert 0 < m["vol"] < 1 and 0 <= m["herfindahl"] <= 1
    assert m["top_stock"] in w
    assert m["top_weight"] == pytest.approx(max(w.values()))


def test_optimize_all_profiles_covers_five():
    out = stock_optimizer.optimize_all_profiles(_cma(), single_stock_cap=0.25)
    assert set(out) == {p.value for p in Profile}
    assert all(abs(sum(r["weights"].values()) - 1.0) < 1e-6 for r in out.values())
    # E[r] 단조: 공격형 ≥ 초안정형
    assert (out[Profile.AGGRESSIVE.value]["metrics"]["expected_return"]
            >= out[Profile.ULTRA_CONSERVATIVE.value]["metrics"]["expected_return"] - 1e-9)
