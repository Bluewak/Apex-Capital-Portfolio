"""종목 optimizer (v3-A Step 2) — 종목 CMA → **유형단위 예시 종목 바스켓**(결정론).

자산군 optimizer([optimizer.py])의 프리미티브(사영·MVO)를 재사용해 종목 μ·Σ에서 성향별
바스켓을 낸다. **유형 단위(예시 모델포트폴리오)** — 개인화 아님(docs/13 §3 Tier 2 경계).
잡음 큰 종목 μ에서 raw MVO는 error-max이므로 **성향 λ 위험회피 + 단일종목 캡**으로 통제
(보수형=min-var 쪽, 공격형=수익추구). 롱온리·Σw=1.

이 산출물(종목 비중)은 Tier 2 판정이므로 numeric_hash에 들어감(docs/13 §3 — 종목=판정).
개인화 딜리버리는 v3-B/규제 게이트 뒤(현 단계 예시 프레이밍).
"""
from __future__ import annotations

import numpy as np

from apex import optimizer
from apex.schemas import CMASet
from apex.schemas.enums import Profile

STOCK_OPT_METHOD = "stock-capped-mvo-v1"
DEFAULT_STOCK_CAP = 0.10   # 단일종목 실효 상한(UCITS 10% 준용)

# 성향별 위험회피 λ(종목 바스켓). 높을수록 저변동 tilt(보수), 낮을수록 수익추구(공격).
_STOCK_LAMBDA: dict[Profile, float] = {
    Profile.ULTRA_CONSERVATIVE: 60.0, Profile.CONSERVATIVE: 25.0,
    Profile.NEUTRAL: 10.0, Profile.GROWTH: 4.0, Profile.AGGRESSIVE: 2.0,
}


def optimize(cma: CMASet, profile: Profile, single_stock_cap: float = DEFAULT_STOCK_CAP,
             min_weight: float = 5e-4) -> dict[str, float]:
    """종목 CMA + 성향 → 종목 바스켓(비중 dict). 롱온리·캡·Σw=1, 결정론."""
    n = len(cma.tickers)
    lo, hi = np.zeros(n), np.full(n, single_stock_cap)
    if hi.sum() < 1.0 - 1e-9:
        raise ValueError(f"단일종목 캡 {single_stock_cap}×{n}종 < 1 — 캡 완화 또는 종목 확대 필요")
    w = optimizer._mvo(cma.mu_vec(), cma.cov_mat(), _STOCK_LAMBDA[profile], lo, hi)
    weights = {t: float(x) for t, x in zip(cma.tickers, w, strict=True) if x > min_weight}
    s = sum(weights.values())
    weights = {k: round(v / s, 6) for k, v in weights.items()}
    top = max(weights, key=weights.get)  # 반올림 잔차 흡수 → 합=1 정확
    weights[top] = round(weights[top] + (1.0 - sum(weights.values())), 6)
    return dict(sorted(weights.items(), key=lambda kv: -kv[1]))


def basket_metrics(cma: CMASet, weights: dict[str, float]) -> dict:
    """바스켓 기대수익·변동성·집중도(감사·표시용)."""
    idx = [cma.tickers.index(t) for t in weights]
    w = np.array([weights[t] for t in weights])
    mu = cma.mu_vec()[idx]
    cov = cma.cov_mat()[np.ix_(idx, idx)]
    exp_ret = float(w @ mu)
    vol = float(np.sqrt(max(w @ cov @ w, 0.0)))
    top = max(weights.items(), key=lambda kv: kv[1])
    return {"expected_return": round(exp_ret, 6), "vol": round(vol, 6),
            "n_holdings": len(weights), "top_stock": top[0], "top_weight": round(top[1], 6),
            "herfindahl": round(float(np.sum(w * w)), 6)}


def optimize_all_profiles(cma: CMASet, single_stock_cap: float = DEFAULT_STOCK_CAP) -> dict:
    """5성향 예시 종목 바스켓 사전연산(유형단위·결정론)."""
    out = {}
    for p in Profile:
        w = optimize(cma, p, single_stock_cap)
        out[p.value] = {"weights": w, "metrics": basket_metrics(cma, w)}
    return out
