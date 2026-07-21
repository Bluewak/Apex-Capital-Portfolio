"""골든 대사 (v2 §3.1) — 독립 계보 대조 로직. 네트워크 없음(monkeypatch)."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from apex.data import golden


def _series(n=300, mu=0.0003, seed=0):
    idx = pd.bdate_range("2015-01-02", periods=n)
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(mu, 0.01, n), index=idx)


def test_reconcile_passes_when_feeds_agree(monkeypatch):
    r = _series()
    monkeypatch.setattr(golden, "_our_returns", lambda *a, **k: r)
    monkeypatch.setattr(golden, "_reference_returns", lambda *a, **k: r.copy())
    out = golden.reconcile_golden("SPY")
    assert out["passed"] and out["ann_dev"] < 1e-9
    assert out["lineage"].startswith("2nd-vendor")


def test_reconcile_fails_on_annualized_divergence(monkeypatch):
    """독립 피드가 연율로 벌어지면 검출(자기참조가 놓칠 진짜 괴리)."""
    r = _series()
    monkeypatch.setattr(golden, "_our_returns", lambda *a, **k: r)
    monkeypatch.setattr(golden, "_reference_returns", lambda *a, **k: r + 0.0002)  # 일별 드리프트
    out = golden.reconcile_golden("069500.KS")
    assert not out["passed"] and out["ann_dev"] > 0.01  # 연 1%+ 괴리


def test_reconcile_insufficient_overlap(monkeypatch):
    short = _series(n=5)
    monkeypatch.setattr(golden, "_our_returns", lambda *a, **k: short)
    monkeypatch.setattr(golden, "_reference_returns", lambda *a, **k: short)
    out = golden.reconcile_golden("SPY")
    assert not out["passed"] and out.get("error")


def test_load_golden_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(golden, "GOLDEN_DIR", tmp_path)
    (tmp_path / "golden.json").write_text(
        json.dumps({"start": "2010-01-01", "rows": [], "golden_version": "abc"}), encoding="utf-8"
    )
    assert golden.load_golden()["golden_version"] == "abc"
    monkeypatch.setattr(golden, "GOLDEN_DIR", tmp_path / "none")
    assert golden.load_golden() is None
