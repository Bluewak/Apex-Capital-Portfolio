"""Step 2b DoD — 결정론 유형단위 Optimizer (v2 §3.2).

합성 CMA로 검증(CI 오프라인). 결정론·합=1·per-ETF 캡·min_cash·성향 의도(밴드)·
vol 단조·클래스내 위험선호(초안정형=저변동 주식)·SPI Optimizer 준수.
optimize는 느리므로 (성향×min_cash)당 1회만 계산해 lru_cache로 공유.
"""
from __future__ import annotations

import functools

import numpy as np
import pandas as pd

from apex import cma, data, optimizer, spi
from apex.schemas.enums import Profile
from apex.universe import ASSET_CLASS, CORE_SLOTS


@functools.lru_cache(maxsize=1)
def _cma() -> cma.CMASet:
    idx = pd.bdate_range("2020-01-02", periods=500)
    mat = pd.DataFrame({t: data.pinned_ticker_returns(t, 500) for t in CORE_SLOTS}, index=idx)
    return cma.build(mat, data_version="test-dv")


@functools.cache
def _opt(profile: Profile, min_cash: float) -> tuple[tuple[str, float], ...]:
    """(성향, min_cash) → 정렬된 weights 튜플(해시가능·캐시)."""
    w = optimizer.optimize(_cma(), profile, min_cash).weights
    return tuple(sorted(w.items()))


def _w(profile: Profile, min_cash: float = 0.05) -> dict[str, float]:
    return dict(_opt(profile, min_cash))


def _class_sums(w: dict[str, float]) -> dict[str, float]:
    by: dict[str, float] = {}
    for t, v in w.items():
        by[ASSET_CLASS[t]] = by.get(ASSET_CLASS[t], 0.0) + v
    return by


def _pvol(w: dict[str, float]) -> float:
    c = _cma()
    wv = np.array([w.get(t, 0.0) for t in c.tickers])
    return float(np.sqrt(wv @ c.cov_mat() @ wv))


def test_optimizer_is_deterministic():
    a = optimizer.optimize(_cma(), Profile.NEUTRAL, min_cash=0.05)
    b = optimizer.optimize(_cma(), Profile.NEUTRAL, min_cash=0.05)
    assert a.weights == b.weights


def test_weights_sum_to_one_and_long_only():
    for p in Profile:
        w = _w(p)
        assert abs(sum(w.values()) - 1.0) < 1e-6
        assert all(v >= 0 for v in w.values())


def test_per_etf_concentration_cap():
    """단일 ETF 집중 상한(주식 30%·금 15%) 준수 — 클래스 밖 누출 없음."""
    for p in Profile:
        for t, v in _w(p).items():
            cap = optimizer._ETF_CAP[ASSET_CLASS[t]]
            assert v <= cap + 1e-6, f"{p.value} {t}={v} > {cap}"


def test_min_cash_guardrail_enforced():
    for p in Profile:
        cash = _class_sums(_w(p, 0.10)).get("CASH", 0.0)
        assert cash >= 0.10 - 1e-6, f"{p.value} cash={cash} < 0.10"


def test_profile_intent_preserved_by_bands():
    """성향 밴드가 성격 보존: 초안정형=현금 다수, 공격형=주식 다수. vol 단조."""
    cash_ultra = _class_sums(_w(Profile.ULTRA_CONSERVATIVE))["CASH"]
    eq_aggr = _class_sums(_w(Profile.AGGRESSIVE))["EQ"]
    assert cash_ultra >= 0.50  # near-cash
    assert eq_aggr >= 0.80  # 주식 다수
    vols = [_pvol(_w(p)) for p in Profile]  # 초안정형→공격형
    assert all(vols[i] < vols[i + 1] + 1e-9 for i in range(len(vols) - 1)), vols


def test_conservative_avoids_high_risk_equity():
    """클래스내 위험선호(λ): 초안정형은 저변동 주식(SPY) 위주, 고위험 EM은 미미."""
    w = _w(Profile.ULTRA_CONSERVATIVE)
    wa = _w(Profile.AGGRESSIVE)
    assert w.get("EEM", 0.0) <= 0.03  # 초안정형에 신흥 과다 금지
    assert wa.get("EEM", 0.0) > w.get("EEM", 0.0)  # 공격형은 EM 실림


def test_cma_optimizer_conforms_to_spi():
    opt = optimizer.CmaOptimizer()
    assert isinstance(opt, spi.Optimizer)
    assert opt.DETERMINISM_REQUIRED is True

    class _C:
        profile = Profile.GROWTH
        min_cash = 0.05

    w = opt.solve(_cma(), _C())
    assert abs(sum(w.values()) - 1.0) < 1e-6
