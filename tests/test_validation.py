"""검증 게이트 (v2 §3.2) — PSR·다중검정 보정·Kupiec·walk-forward. 순수 numpy·결정론."""
from __future__ import annotations

import numpy as np

from apex import validation


def test_norm_cdf_ppf_known_values():
    assert abs(validation.norm_cdf(0.0) - 0.5) < 1e-12
    assert abs(validation.norm_cdf(1.6448536) - 0.95) < 1e-4
    assert abs(validation.norm_ppf(0.975) - 1.959964) < 1e-4
    assert abs(validation.norm_ppf(validation.norm_cdf(0.7)) - 0.7) < 1e-6  # 왕복


def test_psr_high_for_strong_sharpe_low_for_noise():
    rng = np.random.default_rng(0)
    strong = rng.normal(0.001, 0.005, 2000)  # 일별 SR≈0.2
    noise = rng.normal(0.0, 0.01, 2000)  # SR≈0
    assert validation.probabilistic_sharpe(strong) > 0.99
    assert validation.probabilistic_sharpe(noise) < 0.9  # ≈0.5


def test_deflated_benchmark_grows_with_trials():
    sharpes = [0.05, 0.10, 0.15, 0.08, 0.12]
    sr_star = validation.deflated_sr_benchmark(sharpes)
    assert sr_star > 0
    assert validation.deflated_sr_benchmark([0.1]) == 0.0  # <2 시행
    # deflate가 PSR을 낮춘다(더 엄격)
    rng = np.random.default_rng(1)
    r = rng.normal(0.0005, 0.01, 1500)
    deflated = validation.probabilistic_sharpe(r, sr_benchmark=sr_star)
    assert deflated <= validation.probabilistic_sharpe(r)  # deflate가 PSR을 낮춤(더 엄격)


def test_kupiec_pass_on_correct_coverage_fail_on_tight_var():
    rng = np.random.default_rng(2)
    r = rng.normal(0, 0.01, 3000)
    var = abs(float(np.quantile(r, 0.05)))  # 표본 5% 분위 → 초과율≈5%
    _, ok = validation.kupiec_pof(r, var, alpha=0.05)
    assert ok
    _, ok_tight = validation.kupiec_pof(r, var * 0.3, alpha=0.05)  # 너무 타이트 → 초과 과다
    assert not ok_tight


def test_walk_forward_stability():
    rng = np.random.default_rng(3)
    up = rng.normal(0.0005, 0.01, 400)  # 양 반쪽 모두 양의 드리프트
    assert validation.walk_forward_stable(up)
    assert validation.walk_forward_stable(np.array([0.001, 0.002]))  # 짧으면 통과


def test_determinism():
    rng = np.random.default_rng(4)
    r = rng.normal(0, 0.01, 1000)
    assert validation.probabilistic_sharpe(r) == validation.probabilistic_sharpe(r)
    assert validation.kupiec_pof(r, 0.02) == validation.kupiec_pof(r, 0.02)
