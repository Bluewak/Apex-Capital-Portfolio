"""신호 캘리브레이션 (v3-B) — 이산 신호 → (Q,Ω), Ω 하한 불변식·어휘 강제. 네트워크 없음."""
from __future__ import annotations

import pytest

from apex import signal_calibration as sc


def test_all_classes_return_q_and_omega_above_floor():
    for s in sc.SIGNAL_CLASSES:
        q, om = sc.view_qomega(s)
        assert -0.06 <= q <= 0.06
        assert om >= sc.OMEGA_FLOOR   # Ω 하한 불변식(과확신 차단)


def test_q_is_monotone_in_signal():
    q = [sc.view_qomega(s)[0] for s in ("strong_neg", "neg", "neutral", "pos", "strong_pos")]
    assert q == sorted(q) and q[0] < 0 < q[-1] and q[2] == 0.0


def test_invalid_signal_hard_fails():
    with pytest.raises(ValueError, match="미지 신호"):
        sc.view_qomega("boom")


def test_is_valid_signal():
    assert sc.is_valid_signal("pos") and not sc.is_valid_signal("BOOM")


def test_calib_version_stable_and_prefixed():
    assert sc.calib_version() == sc.calib_version()
    assert sc.calib_version().startswith("signal-calib-v1-")
