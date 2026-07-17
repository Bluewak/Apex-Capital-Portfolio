"""Compliance Guardrail — RiskReport + InvestorProfile → 차단/강등/보류 (03 §4, 05 §3).

바인딩(차단) 지표 = `var95_annual`(R5, MDD 아님). binding = min(성향 평시 상한, |Q6|)
(둘 중 더 보수적, 05 §3). 위반 시 한 등급 강등(revised_profile 재발행), 사다리 소진 시 hold.
MDD는 disclosed(차단 아님, R3).
"""
from __future__ import annotations

from apex import graph
from apex.schemas import Allocation, ComplianceDecision, InvestorProfile, RiskReport
from apex.schemas.enums import Profile
from apex.schemas.risk import Breach
from apex.universe import ASSET_CLASS, CLASS_LABEL

# 05 §3 평시 상한 — vol(연변동성)·mdd(평시 최대낙폭, 음수)·var(연율 VaR95 양수손실).
# R5: 초안정형 행 추가. 바인딩(차단)은 var(R5); vol·mdd는 게이트 참고.
PROFILE_LIMITS: dict[Profile, dict[str, float]] = {
    Profile.ULTRA_CONSERVATIVE: {"vol": 0.035, "mdd": -0.07, "var": 0.05},
    Profile.CONSERVATIVE: {"vol": 0.06, "mdd": -0.10, "var": 0.08},
    Profile.NEUTRAL: {"vol": 0.10, "mdd": -0.18, "var": 0.15},
    Profile.GROWTH: {"vol": 0.15, "mdd": -0.28, "var": 0.22},
    Profile.AGGRESSIVE: {"vol": 0.20, "mdd": -0.40, "var": 0.32},
}
VAR_LIMIT: dict[Profile, float] = {p: lim["var"] for p, lim in PROFILE_LIMITS.items()}

# 단일 ETF 집중 하드캡(자산군별, 07 §3). compliance가 실제 검증(docs/10 §3.5).
ETF_CLASS_CAP: dict[str, float] = {"EQ": 0.30, "BOND": 0.40, "GOLD": 0.15, "CASH": 1.00}

# 성향별 자산군 밴드(07 §3) — 정본(optimizer가 이걸 import). 키=EQ/BOND/GOLD/CASH.
CLASS_BANDS: dict[Profile, dict[str, tuple[float, float]]] = {
    Profile.ULTRA_CONSERVATIVE: {
        "EQ": (0.0, 0.15), "BOND": (0.10, 0.30), "GOLD": (0.0, 0.10), "CASH": (0.55, 0.80),
    },
    Profile.CONSERVATIVE: {
        "EQ": (0.20, 0.40), "BOND": (0.40, 0.65), "GOLD": (0.0, 0.15), "CASH": (0.03, 0.15),
    },
    Profile.NEUTRAL: {
        "EQ": (0.45, 0.65), "BOND": (0.20, 0.40), "GOLD": (0.0, 0.12), "CASH": (0.05, 0.15),
    },
    Profile.GROWTH: {
        "EQ": (0.65, 0.85), "BOND": (0.05, 0.25), "GOLD": (0.0, 0.10), "CASH": (0.03, 0.12),
    },
    Profile.AGGRESSIVE: {
        "EQ": (0.80, 0.95), "BOND": (0.0, 0.15), "GOLD": (0.0, 0.10), "CASH": (0.03, 0.10),
    },
}
_TOL = 1e-9


def structural_breaches(alloc: Allocation, profile: InvestorProfile) -> list[Breach]:
    """KG 구조 검증(docs/12 §3): 단일 ETF 집중 하드캡 + 자산군 밴드(근거경로 포함).

    var(차단)과 **독립**으로 배분 구조를 검증한다 — compliance가 집중도·밴드를 실제로
    확인(docs/10 §3.5). 최적화·룰 배분은 캡·밴드 준수라 정상 시 빈 리스트(골든 동일성).
    """
    out: list[Breach] = []
    for t, w in alloc.weights.items():
        cap = ETF_CLASS_CAP[ASSET_CLASS[t]]
        if w > cap + _TOL:
            out.append(Breach(metric=f"concentration:{t}", limit=cap, actual=round(w, 6),
                              because=[t]))
    roots = graph.root_class_exposure(alloc.weights)  # 가중·룩스루(§8)
    for code, (lo, hi) in CLASS_BANDS[profile.profile].items():
        kr = CLASS_LABEL[code]
        v = roots.get(kr, 0.0)
        if v < lo - _TOL or v > hi + _TOL:
            out.append(Breach(metric=f"band:{code}", limit=(lo if v < lo else hi),
                              actual=round(v, 6), because=graph.because(kr, alloc.weights)))
    return out


def check(risk: RiskReport, profile: InvestorProfile) -> ComplianceDecision:
    """단일 판정. 위반 시 강등(revised_profile) 또는 hold. 루프 소유는 pipeline(08 §7).

    차단 지표(§3.5): ``expected_loss_1y_forward``가 있으면 **forward 기대손실**로,
    없으면 기존 실현 ``var95_annual``로(하위호환). forward는 강세장 표본 착시를 배제해
    out-of-sample에서도 정직하게 리스크를 적립한다.
    """
    limit = VAR_LIMIT[profile.profile]
    binding = min(limit, abs(profile.max_annual_loss))  # Q6 교차, 더 보수적
    forward = risk.expected_loss_1y_forward
    actual = forward if forward is not None else risk.var95_annual
    metric = "expected_loss_1y_forward" if forward is not None else "var95_annual"

    if actual <= binding + _TOL:
        return ComplianceDecision(decision="ok")

    breach = Breach(metric=metric, limit=-binding, actual=-actual)
    revised = profile.downgraded()
    if revised is None:
        # 초안정형까지 소진 → 배정 보류(포트 미발행, R5)
        return ComplianceDecision(
            decision="hold",
            downgrade_reason=(
                f"{profile.profile.value}(예상 연손실 {actual:.1%})이 감내 한도 "
                f"{binding:.1%}를 초과 — 강등 사다리 소진(초안정형까지 미달), 배정 보류"
            ),
            breaches=[breach],
        )
    return ComplianceDecision(
        decision="downgrade",
        revised_profile=revised,
        downgrade_reason=(
            f"요청 {profile.profile.value}의 예상 연손실 {actual:.1%}이 감내 한도 "
            f"{binding:.1%}를 초과 → {revised.profile.value}으로 조정"
        ),
        breaches=[breach],
    )
