"""Forward risk (v2 §3.5) — CMA(μ,Σ) 기반 forward 기대손실.

**왜 forward인가.** 차단 지표가 실현 롤링 VaR면 강세장 표본에서 평시≈0으로 붕괴해
리스크를 과소 적립한다. forward 기대손실은 CMA(표본 무관 μ + shrinkage Σ)에서 나오므로
out-of-sample에서도 정직하게 리스크를 쌓는다 → 2d에서 compliance 차단 지표로 교체.

실현치(var95_annual·MDD)는 disclosed로 병기(차단 아님, R3).
"""
from __future__ import annotations

import numpy as np

from apex.schemas import CMASet
from apex.schemas.registry import ForwardRisk

# 정규 근사 5% 분위(하위 5% 손실). μ 과신 방지 haircut(불확실성 밴드의 보수 처리).
_Z95 = 1.645
_MU_CONFIDENCE = 0.5


def forward_stats(cma: CMASet, weights: dict[str, float]) -> tuple[float, float]:
    """포트폴리오 forward (연 기대수익 μ_p, 연 변동성 vol_p)."""
    w = np.array([weights.get(t, 0.0) for t in cma.tickers], dtype=float)
    mu_p = float(w @ cma.mu_vec())
    vol_p = float(np.sqrt(max(w @ cma.cov_mat() @ w, 0.0)))
    return mu_p, vol_p


def expected_loss_1y(mu_p: float, vol_p: float) -> float:
    """forward 1년 5% 꼬리 기대손실(연, 양수=손실). 0 하한.

    보수 처리: μ를 haircut(_MU_CONFIDENCE)해 기대수익 과신을 배제한 뒤 정규 근사
    하위 5% 손실 = z·σ − haircut·μ. 강세장 표본에 기대지 않는 forward 적립.
    """
    return max(_Z95 * vol_p - _MU_CONFIDENCE * mu_p, 0.0)


def forward_risk(cma: CMASet, weights: dict[str, float]) -> ForwardRisk:
    """CMA + 배분 → ForwardRisk(기대수익·변동성·forward 기대손실)."""
    mu_p, vol_p = forward_stats(cma, weights)
    return ForwardRisk(
        expected_return=round(mu_p, 6),
        vol=round(vol_p, 6),
        expected_loss_1y=round(expected_loss_1y(mu_p, vol_p), 6),
    )
