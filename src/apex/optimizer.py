"""Optimizer (v2 §3.2) — CMA → 결정론 유형단위 배분. 하드코딩 dict를 산출물로 교체.

**결정론 서빙**: 순수 numpy, 랜덤 없음, 고정 반복수 → 동일 CMA·성향 → 동일 배분.
**유형 단위**: 5성향 각각 1회 최적화(사전연산 가능). **의도 보존**: 07 §3 자산군 밴드
안에서 CMA가 tilt를 정한다(성향 성격 유지 + 밴드 내 선택은 데이터 주도).

방법 = **2단 분해**(각 하위문제가 box+합=1 = 캡드-심플렉스라 정확히 풀림):
1) 클래스 내 max-Sharpe(per-ETF 캡) → 클래스별 정규화 비중.
2) 클래스를 합성자산으로 보고 성향 밴드 안에서 클래스 예산 MVO(vol 타깃까지 λ-이분).
최종 = 클래스예산 × 클래스내비중. 비수렴/게이트 실패 시 **룰 dict 폴백**(사다리 최하단).
"""
from __future__ import annotations

import numpy as np

from apex.compliance import CLASS_BANDS as _PROFILE_BANDS  # 밴드·캡 정본 = compliance
from apex.compliance import ETF_CLASS_CAP as _ETF_CAP
from apex.schemas import Allocation, CMASet
from apex.schemas.enums import Profile
from apex.universe import ASSET_CLASS

OPT_METHOD_VERSION = "twolevel-mvo-v1"

# 성향별 vol 타깃(05 §3 평시 상한). 클래스 예산 MVO의 λ-이분 목표.
_VOL_TARGET: dict[Profile, float] = {
    Profile.ULTRA_CONSERVATIVE: 0.035, Profile.CONSERVATIVE: 0.06,
    Profile.NEUTRAL: 0.10, Profile.GROWTH: 0.15, Profile.AGGRESSIVE: 0.20,
}
# 클래스 내 위험회피 λ(성향별). 높을수록 저변동 선호 → 보수형은 SPY, 공격형은 EEM tilt.
# 클래스 내 선택이 성향 위험선호를 따르게 한다(초안정형에 EM이 실리지 않도록).
_LAMBDA_WITHIN: dict[Profile, float] = {
    Profile.ULTRA_CONSERVATIVE: 80.0, Profile.CONSERVATIVE: 40.0,
    Profile.NEUTRAL: 15.0, Profile.GROWTH: 6.0, Profile.AGGRESSIVE: 3.0,
}
_CLASSES = ("EQ", "BOND", "GOLD", "CASH")


# 결정론 반복 상수(핀). 사영 이분 32=τ 2^-32 정밀, 경사 150=소차원 QP 수렴, vol 이분 30.
_PROJ_ITERS, _MVO_ITERS, _VOL_BISECT = 32, 150, 30


def _project_capped_simplex(v: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """v를 {lo≤w≤hi, Σw=1}에 사영(τ 이분). 가정: Σlo ≤ 1 ≤ Σhi."""
    tau_lo, tau_hi = float((v - hi).min() - 1.0), float((v - lo).max() + 1.0)
    for _ in range(_PROJ_ITERS):
        tau = 0.5 * (tau_lo + tau_hi)
        s = np.clip(v - tau, lo, hi).sum()
        if s > 1.0:
            tau_lo = tau  # τ↑ → 합↓
        else:
            tau_hi = tau
    return np.clip(v - 0.5 * (tau_lo + tau_hi), lo, hi)


def _mvo(mu: np.ndarray, cov: np.ndarray, lam: float, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """max μ·w − (λ/2)wᵀΣw s.t. box+합=1. 사영경사(고정 스텝·반복=결정론)."""
    lmax = float(np.linalg.eigvalsh(cov).max())
    step = 1.0 / (lam * lmax + 1e-9)  # Lipschitz 역수(수렴 보장)
    w = _project_capped_simplex(np.full_like(lo, 1.0 / len(lo)), lo, hi)
    for _ in range(_MVO_ITERS):
        w = _project_capped_simplex(w + step * (mu - lam * cov @ w), lo, hi)
    return w


def _vol(w: np.ndarray, cov: np.ndarray) -> float:
    return float(np.sqrt(max(w @ cov @ w, 0.0)))


def _solve_to_vol(
    mu: np.ndarray, cov: np.ndarray, lo: np.ndarray, hi: np.ndarray, vol_target: float
) -> np.ndarray:
    """box+합=1 안에서 vol≤타깃 중 기대수익 최대(λ 기하이분). 최소vol>타깃이면 최소vol."""
    w_minvol = _mvo(mu, cov, 1e6, lo, hi)
    if _vol(w_minvol, cov) > vol_target:
        return w_minvol  # 밴드 안 최소vol도 타깃 초과 → 최선노력(게이트가 판정)
    lam_lo, lam_hi = 1e-3, 1e6
    for _ in range(_VOL_BISECT):
        lam = float(np.sqrt(lam_lo * lam_hi))
        if _vol(_mvo(mu, cov, lam, lo, hi), cov) > vol_target:
            lam_lo = lam  # 위험초과 → λ↑
        else:
            lam_hi = lam
    return _mvo(mu, cov, lam_hi, lo, hi)


def _within_class(cma: CMASet, cls: str, lam: float, cap_within: float) -> dict[str, float]:
    """클래스 내 티커 비중(성향 λ 위험회피 tilt). per-ETF 캡을 **클래스 내부**에서 반영
    (cap_within = 글로벌캡/클래스밴드상한 → 예산×비중 ≤ 글로벌캡, 클래스 밖 누출 없음)."""
    tickers = [t for t in cma.tickers if ASSET_CLASS[t] == cls]
    if len(tickers) == 1:
        return {tickers[0]: 1.0}
    idx = [cma.tickers.index(t) for t in tickers]
    mu = cma.mu_vec()[idx]
    cov = cma.cov_mat()[np.ix_(idx, idx)]
    lo = np.zeros(len(tickers))
    hi = np.full(len(tickers), min(cap_within, 1.0))
    if hi.sum() < 1.0:  # 캡이 너무 빡빡해 합=1 불가 → 캡 해제(게이트가 최종 판정)
        hi = np.ones(len(tickers))
    w = _mvo(mu, cov, lam, lo, hi)  # 성향 위험회피 λ로 클래스 내 tilt
    return dict(zip(tickers, w, strict=True))


def optimize(cma: CMASet, profile: Profile, min_cash: float = 0.0) -> Allocation:
    """CMA + 성향 → Allocation. 2단 분해 최적화. 실패 시 룰 dict 폴백."""
    from datetime import date

    try:
        w = _optimize_weights(cma, profile, min_cash)
        _validate(w, profile, min_cash)
        w = {k: v for k, v in w.items() if v > 5e-4}  # 미미한 비중 절사
        s = sum(w.values())
        w = {k: round(v / s, 6) for k, v in w.items()}
        top = max(w, key=w.get)  # 반올림 잔차를 최대 비중에 흡수 → 합=1 정확
        w[top] = round(w[top] + (1.0 - sum(w.values())), 6)
        return Allocation(
            profile=profile, model_portfolio=profile.model_portfolio, weights=w,
            as_of=date.fromisoformat(cma.as_of), model_version="cma-opt-" + OPT_METHOD_VERSION,
        )
    except (ValueError, _OptFailure):
        from apex import allocation as _alloc
        a = _alloc.build(profile, min_cash=min_cash)  # 폴백: 룰 dict(사다리 최하단)
        return a.model_copy(update={"model_version": "rule-fallback"})


class _OptFailure(Exception):
    """최적화 게이트 실패 → 폴백 트리거(내부)."""


def _optimize_weights(cma: CMASet, profile: Profile, min_cash: float) -> dict[str, float]:
    bands = _PROFILE_BANDS[profile]
    lam_w = _LAMBDA_WITHIN[profile]
    # 클래스 내 비중(성향 λ) — per-ETF 캡을 클래스 내부에서 반영(누출 방지)
    within = {
        c: _within_class(cma, c, lam_w, _ETF_CAP[c] / bands[c][1] if bands[c][1] > 0 else 1.0)
        for c in _CLASSES
    }
    # 클래스 합성자산 μ·Σ (클래스내 비중으로 축약)
    vmat = np.zeros((len(_CLASSES), len(cma.tickers)))
    for ci, c in enumerate(_CLASSES):
        for t, wv in within[c].items():
            vmat[ci, cma.tickers.index(t)] = wv
    mu_cls = vmat @ cma.mu_vec()
    cov_cls = vmat @ cma.cov_mat() @ vmat.T

    # 성향 밴드 → 클래스 box (min_cash가 CASH 하한을 밀어올림)
    lo = np.array([bands[c][0] for c in _CLASSES])
    hi = np.array([bands[c][1] for c in _CLASSES])
    ci_cash = _CLASSES.index("CASH")
    lo[ci_cash] = max(lo[ci_cash], min_cash)
    hi[ci_cash] = max(hi[ci_cash], lo[ci_cash])  # min_cash 가드레일 우선
    if lo.sum() > 1.0 or hi.sum() < 1.0:
        raise _OptFailure("클래스 밴드 비가용")

    budget = _solve_to_vol(mu_cls, cov_cls, lo, hi, _VOL_TARGET[profile])

    # 최종 = 클래스예산 × 클래스내비중 (per-ETF 캡은 클래스 내부에서 이미 보장, 누출 없음)
    w: dict[str, float] = {}
    for ci, c in enumerate(_CLASSES):
        for t, wv in within[c].items():
            w[t] = w.get(t, 0.0) + budget[ci] * wv
    return w


def _validate(w: dict[str, float], profile: Profile, min_cash: float) -> None:
    """게이트: 합=1·음수 없음·per-ETF 캡·min_cash. 위반 → 폴백."""
    if abs(sum(w.values()) - 1.0) > 1e-6 or any(v < -1e-9 for v in w.values()):
        raise _OptFailure("합≠1 또는 음수")
    for t, v in w.items():
        if v > _ETF_CAP[ASSET_CLASS[t]] + 1e-6:
            raise _OptFailure(f"{t} per-ETF 캡 초과")
    cash = sum(v for t, v in w.items() if ASSET_CLASS[t] == "CASH")
    if cash < min_cash - 1e-6:
        raise _OptFailure("min_cash 미달")


class CmaOptimizer:
    """SPI Optimizer 어댑터(결정론). solve(cma, constraints)→ 티커 비중 dict."""

    DETERMINISM_REQUIRED = True

    def solve(self, cma: CMASet, constraints: object) -> dict[str, float]:
        profile = getattr(constraints, "profile", Profile.NEUTRAL)
        min_cash = float(getattr(constraints, "min_cash", 0.0))
        return dict(optimize(cma, profile, min_cash).weights)
