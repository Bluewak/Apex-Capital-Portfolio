"""InvestorProfile 스키마 (03 §5 정본) — Investor Agent → IPS/Allocation."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import FxPreference, Liquidity, Profile


class Constraints(BaseModel):
    """구조화 제약 (03 §5 R2). allocation·compliance가 결정론적으로 소비.

    자유텍스트 list[str] 금지 — allocation은 값을 키로 읽는다.
    """

    min_cash: float = Field(default=0.05, ge=0, le=1, description="현금성 최소 비중")
    hedge_preferred: bool = Field(default=False, description="환헤지 우선 여부(Q9=회피)")
    cap_profile: Profile | None = Field(
        default=None, description="하드 가드레일이 성향 상한을 캡했을 때의 상한 등급(03 §4)"
    )


class InvestorProfile(BaseModel):
    """위험점수·성향과 제약을 담은 투자자 프로파일 (03 §5).

    배분 키(R3): allocation은 ``profile``(및 ``constraints.cap_profile``)을 키로 소비하고
    ``risk_score``는 표시·설명용이다. ``downgrade()``는 ``profile``을 낮춰야 실효한다.
    """

    risk_score: int = Field(ge=0, le=100)
    profile: Profile
    horizon_years: int = Field(ge=0)
    max_annual_loss: float = Field(le=0, description="연간 최대 손실 감내(Q6), 음수")
    liquidity_need: Liquidity
    fx_preference: FxPreference
    constraints: Constraints = Field(default_factory=Constraints)

    def downgraded(self) -> InvestorProfile | None:
        """한 등급 강등한 RevisedProfile 재발행 (constraints 보존, 08 §7).

        초안정형보다 아래는 없으므로 None(→ compliance가 hold로 종료).
        """
        lower = self.profile.downgraded()
        if lower is None:
            return None
        return self.model_copy(update={"profile": lower})
