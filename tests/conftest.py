"""공유 테스트 픽스처 — 합성 레지스트리(서빙·웹 테스트 공용, 1회 빌드)."""
from __future__ import annotations

import functools

import pandas as pd
import pytest

from apex import cma, data, registry
from apex.schemas.enums import Profile
from apex.universe import CORE_SLOTS


@functools.cache
def build_synth_registry():
    """합성 CMA+행렬로 5성향×{0.05,0.10} 레지스트리(실현 포함). 캐시로 1회만."""
    idx = pd.bdate_range("2005-01-03", periods=1500)
    mat = pd.DataFrame({t: data.pinned_ticker_returns(t, 1500) for t in CORE_SLOTS}, index=idx)
    cset = cma.build(mat.iloc[:600], data_version="test-dv")
    return registry.build(cset, mat, min_cash_grid=(0.05, 0.10), profiles=tuple(Profile))


@pytest.fixture(scope="session")
def synth_registry():
    return build_synth_registry()
