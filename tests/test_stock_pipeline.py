"""v3-A 오케스트레이터 (Step 2 다지기) — 조립·결정론·재현성(numeric_hash). 네트워크 없음."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apex import stock_cma, stock_optimizer, stock_pipeline
from apex.schemas.enums import Profile


def _synthetic():
    t = np.arange(220)
    data = {f"S{i}": 0.001 * np.sin(t / (5 + i)) + 0.0006 * np.cos(t / (3 + i))
            for i in range(6)}
    rm = pd.DataFrame(data)
    gk = {f"S{i}": {"mu": 0.06 + 0.01 * i} for i in range(6)}
    return rm, gk


def test_numeric_hash_excludes_itself_and_is_stable():
    r = {"a": 1.0, "b": [0.123456789, {"c": 0.987654321}], "numeric_hash": "OLD"}
    h1 = stock_pipeline.numeric_hash(r)
    h2 = stock_pipeline.numeric_hash({**r, "numeric_hash": "DIFFERENT"})
    assert h1 == h2  # numeric_hash 자신은 해시에서 제외
    assert len(h1) == 16


def test_v3a_chain_deterministic_on_synthetic():
    """핀·네트워크 없이 CMA→optimizer→hash가 동일 입력에 동일 출력(결정론)."""
    rm, gk = _synthetic()
    cma1 = stock_cma.build(rm, gk, data_version="dv", as_of="2026-07-20")
    cma2 = stock_cma.build(rm, gk, data_version="dv", as_of="2026-07-20")
    assert cma1.cma_version == cma2.cma_version
    assert cma1.cov == cma2.cov and cma1.mu == cma2.mu   # 정확 일치(rtol 0)
    b1 = stock_optimizer.optimize_all_profiles(cma1, single_stock_cap=0.25)
    b2 = stock_optimizer.optimize_all_profiles(cma2, single_stock_cap=0.25)
    assert b1 == b2
    r1 = {"cma_version": cma1.cma_version, "mu": cma1.mu, "baskets": b1}
    r2 = {"cma_version": cma2.cma_version, "mu": cma2.mu, "baskets": b2}
    assert stock_pipeline.numeric_hash(r1) == stock_pipeline.numeric_hash(r2)


def test_v3a_run_reproducible_and_wellformed_if_pinned():
    """핀 존재 시 run() 2회 동일 numeric_hash + 산출물 정합(없으면 skip)."""
    from apex.data.stock_prices import load_prices
    if not load_prices() or not stock_cma.load_gk_inputs():
        pytest.skip("핀 부재 — pull_prices/pull_gk_inputs 선행 필요")
    r1 = stock_pipeline.run()
    r2 = stock_pipeline.run()
    assert r1["numeric_hash"] == r2["numeric_hash"]                 # 재현성
    assert set(r1["baskets"]) == {p.value for p in Profile}          # 5성향
    for b in r1["baskets"].values():
        assert abs(sum(b["weights"].values()) - 1.0) < 1e-6          # Σw=1
    assert set(r1["backtest"]["per_profile"]) == {p.value for p in Profile}


def test_run_hard_fails_without_pins(monkeypatch):
    """핀 우선: 핀 부재 시 하드 실패([11] §5.3)."""
    monkeypatch.setattr(stock_pipeline, "load_prices", lambda: {})
    with pytest.raises(RuntimeError, match="핀 부재"):
        stock_pipeline.run()
