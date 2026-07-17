"""Step 2a DoD — CMA 엔진(빌딩블록 μ + Ledoit-Wolf Σ) (v2 §3.2).

핀 없이 합성 결정론 행렬로 검증(CI 오프라인). PSD·수축계수·μ 합리성·결정론·리니지.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from apex import cma, data
from apex.universe import CORE_SLOTS


def _synth_matrix(n: int = 500) -> pd.DataFrame:
    """합성 피닝 수익률로 9슬롯 일별 행렬(결정론)."""
    idx = pd.bdate_range("2020-01-02", periods=n)
    return pd.DataFrame({t: data.pinned_ticker_returns(t, n) for t in CORE_SLOTS}, index=idx)


def test_cma_is_deterministic():
    mat = _synth_matrix()
    a = cma.build(mat, data_version="test-dv")
    b = cma.build(mat, data_version="test-dv")
    assert a.model_dump() == b.model_dump()
    assert a.cma_version == b.cma_version


def test_covariance_symmetric_and_psd():
    c = cma.build(_synth_matrix(), data_version="test-dv")
    cov = c.cov_mat()
    assert np.allclose(cov, cov.T)  # 대칭
    eig = np.linalg.eigvalsh(cov)
    assert eig.min() >= -1e-10  # PSD(LW shrinkage 보장)


def test_shrinkage_in_unit_interval():
    c = cma.build(_synth_matrix(), data_version="test-dv")
    assert 0.0 <= c.shrinkage <= 1.0


def test_expected_returns_are_forward_building_blocks():
    """μ는 표본 무관 빌딩블록 — 자산군 순서(주식>채권>금 근방)·합리 범위."""
    c = cma.build(_synth_matrix(), data_version="test-dv")
    for t in CORE_SLOTS:
        assert 0.0 < c.mu[t] < 0.15, f"{t} μ={c.mu[t]} 비합리"
    assert c.mu["SPY"] > c.mu["SHY"]  # 주식 위험프리미엄 > 단기국채
    # GK에선 고성장주(QQQ)가 밸류에이션 드래그로 대형(SPY)과 동률/열위일 수 있음(정상).
    assert c.mu["EEM"] > c.mu["SPY"]  # 신흥(고성장·저밸류) 프리미엄 > 미 대형
    # 표본이 바뀌어도 μ는 불변(빌딩블록=forward 가정)
    other = cma.build(_synth_matrix(300), data_version="test-dv")
    assert other.mu == c.mu


def test_volatility_ordering_from_data():
    """Σ는 데이터 추정 — 변동성 순서가 자산 특성과 정합(단기국채<주식)."""
    c = cma.build(_synth_matrix(), data_version="test-dv")
    assert c.vol["SHY"] < c.vol["SPY"]
    assert c.vol["SHY"] < c.vol["QQQ"]


def test_cma_version_tracks_data_version():
    mat = _synth_matrix()
    a = cma.build(mat, data_version="dv-A")
    b = cma.build(mat, data_version="dv-B")
    assert a.cma_version != b.cma_version  # 리니지가 데이터버전을 반영


def test_ledoit_wolf_bounds_and_shape():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 0.01, (250, 9))
    sigma, delta = cma.ledoit_wolf(x)
    assert sigma.shape == (9, 9)
    assert 0.0 <= delta <= 1.0
    assert np.linalg.eigvalsh(sigma).min() >= -1e-12
