"""Compliance Guardrail — RiskReport + InvestorProfile → 차단/강등/보류 (03 §4, 05 §3).

바인딩(차단) 지표 = `var95_annual`(R5, MDD 아님). binding = min(성향 평시 상한, |Q6|)
(둘 중 더 보수적, 05 §3). 위반 시 한 등급 강등(revised_profile 재발행), 사다리 소진 시 hold.
MDD는 disclosed(차단 아님, R3).
"""
from __future__ import annotations

from apex.schemas import ComplianceDecision, InvestorProfile, RiskReport
from apex.schemas.enums import Profile
from apex.schemas.risk import Breach

# 05 §3 평시 상한 — var95_annual(양수 손실률). R5: 초안정형 행 추가.
VAR_LIMIT: dict[Profile, float] = {
    Profile.ULTRA_CONSERVATIVE: 0.05,
    Profile.CONSERVATIVE: 0.08,
    Profile.NEUTRAL: 0.15,
    Profile.GROWTH: 0.22,
    Profile.AGGRESSIVE: 0.32,
}
_TOL = 1e-9


def check(risk: RiskReport, profile: InvestorProfile) -> ComplianceDecision:
    """단일 판정. 위반 시 강등(revised_profile) 또는 hold. 루프 소유는 pipeline(08 §7)."""
    limit = VAR_LIMIT[profile.profile]
    binding = min(limit, abs(profile.max_annual_loss))  # Q6 교차, 더 보수적
    actual = risk.var95_annual

    if actual <= binding + _TOL:
        return ComplianceDecision(decision="ok")

    breach = Breach(metric="var95_annual", limit=-binding, actual=-actual)
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
