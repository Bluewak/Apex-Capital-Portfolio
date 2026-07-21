"""무위험금리·환율 실소싱 (v2 §3.1) — 핀 로드·폴백. 네트워크 없음(픽스처)."""
from __future__ import annotations

import json

from apex.data import rates


def test_load_pinned_rates_fallback_to_defaults(monkeypatch, tmp_path):
    """핀 부재 시 문서화 기본값(오프라인 안전)."""
    monkeypatch.setattr(rates, "RATES_DIR", tmp_path / "none")
    r = rates.load_pinned_rates()
    assert r["rates_version"] == "default"
    assert 0 < r["usd_rf"] < 0.1 and 0 < r["krw_rf"] < 0.1


def test_load_pinned_rates_reads_artifact(monkeypatch, tmp_path):
    """피닝된 rates.json을 읽는다."""
    monkeypatch.setattr(rates, "RATES_DIR", tmp_path)
    (tmp_path / "rates.json").write_text(
        json.dumps({"usd_rf": 0.015, "krw_rf": 0.023, "fx_krwusd": 1501.0,
                    "rates_version": "abc123"}),
        encoding="utf-8",
    )
    r = rates.load_pinned_rates()
    assert r["usd_rf"] == 0.015 and r["krw_rf"] == 0.023
    assert r["rates_version"] == "abc123"


def test_gate_uses_pinned_rates_not_hardcoded():
    """gate 모듈에 하드코딩 rf 상수가 없다(실소싱으로 대체)."""
    import apex.gate as gate

    assert not hasattr(gate, "_RF_USD") and not hasattr(gate, "_RF_KRW")
