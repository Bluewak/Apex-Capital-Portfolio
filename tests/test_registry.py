"""Step 2c DoD — forward risk + 사전연산 레지스트리 (v2 §3.2·§3.5·§3.6).

forward 손실(표본 무관)·레지스트리 빌드/조회/저장·리니지·실현 병기. 합성으로 CI 오프라인.
"""
from __future__ import annotations

import functools

import pandas as pd

from apex import cma, data, forward, registry
from apex.provenance import ENV_HASH
from apex.schemas import Registry
from apex.schemas.enums import Profile
from apex.universe import CORE_SLOTS


@functools.cache
def _cma() -> cma.CMASet:
    idx = pd.bdate_range("2020-01-02", periods=500)
    mat = pd.DataFrame({t: data.pinned_ticker_returns(t, 500) for t in CORE_SLOTS}, index=idx)
    return cma.build(mat, data_version="test-dv")


@functools.cache
def _mat() -> pd.DataFrame:
    idx = pd.bdate_range("2005-01-03", periods=1500)
    return pd.DataFrame({t: data.pinned_ticker_returns(t, 1500) for t in CORE_SLOTS}, index=idx)


# ── forward risk 수식 ──
def test_expected_loss_is_conservative_tail():
    """z·σ − haircut·μ, 0 하한. μ가 커도 σ 큰 자산은 손실이 크게 적립."""
    assert forward.expected_loss_1y(0.05, 0.20) > forward.expected_loss_1y(0.05, 0.05)
    assert forward.expected_loss_1y(0.10, 0.0) == 0.0  # 무변동·양의 μ → 손실 0
    # 강세장 표본과 무관하게 forward σ가 손실을 지배
    hi_vol = forward.expected_loss_1y(0.06, 0.17)
    assert hi_vol > 0.15  # 공격형급 forward 손실은 유의미(실현 VaR≈0과 대비)


def test_forward_risk_from_cma():
    c = _cma()
    from apex import optimizer
    w = optimizer.optimize(c, Profile.AGGRESSIVE, min_cash=0.05).weights
    fr = forward.forward_risk(c, w)
    assert fr.vol > 0 and fr.expected_return > 0
    assert fr.expected_loss_1y >= 0


# ── 레지스트리 ──
_SMALL = (Profile.ULTRA_CONSERVATIVE, Profile.AGGRESSIVE)


def test_registry_build_is_deterministic_with_lineage():
    c = _cma()
    a = registry.build(c, min_cash_grid=(0.0, 0.10), profiles=_SMALL)
    b = registry.build(c, min_cash_grid=(0.0, 0.10), profiles=_SMALL)
    assert a.model_dump() == b.model_dump()
    assert a.cma_version == c.cma_version and a.data_version == "test-dv"
    assert a.env_hash == ENV_HASH and a.model_version.startswith("opt-")
    assert len(a.entries) == 4  # 2성향 × 2 min_cash


def test_registry_forward_loss_orders_by_profile():
    """공격형 forward 손실 > 초안정형(리스크 단조)."""
    reg = registry.build(_cma(), min_cash_grid=(0.05,), profiles=_SMALL)
    ultra = reg.lookup(Profile.ULTRA_CONSERVATIVE, 0.05)
    aggr = reg.lookup(Profile.AGGRESSIVE, 0.05)
    assert aggr.forward.expected_loss_1y > ultra.forward.expected_loss_1y


def test_registry_lookup_snaps_min_cash_conservative():
    """조회 min_cash는 그리드 중 ≤요청의 최대로 스냅(보수)."""
    reg = registry.build(_cma(), min_cash_grid=(0.0, 0.05, 0.10), profiles=(Profile.NEUTRAL,))
    assert reg.lookup(Profile.NEUTRAL, 0.07).min_cash == 0.05  # 0.07 → 0.05로 스냅
    assert reg.lookup(Profile.NEUTRAL, 0.12).min_cash == 0.10


def test_registry_realized_when_matrix_given():
    """행렬 주입 시 실현 지표 병기(백테스트), 없으면 None."""
    reg_fwd = registry.build(_cma(), min_cash_grid=(0.05,), profiles=(Profile.NEUTRAL,))
    assert reg_fwd.entries[0].realized_var95_annual is None
    reg_real = registry.build(_cma(), _mat(), min_cash_grid=(0.05,), profiles=(Profile.NEUTRAL,))
    assert reg_real.entries[0].realized_var95_annual is not None


def test_registry_save_load_roundtrip(tmp_path):
    reg = registry.build(_cma(), min_cash_grid=(0.05,), profiles=_SMALL)
    registry.save(reg, tmp_path)
    loaded = Registry(**__import__("json").loads((tmp_path / "latest.json").read_text("utf-8")))
    assert loaded.model_dump() == reg.model_dump()
