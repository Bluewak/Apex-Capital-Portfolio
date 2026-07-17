"""ComplianceDecision 스키마 (06 §3.6) — Compliance Guardrail 출력.

R3 역간선 1급 계약: compliance→allocation 재배분을 문자열이 아니라
``revised_profile: InvestorProfile | None`` 객체로 전달한다(강등 시 constraints 보존).
decision ∈ {ok, downgrade, hold} (R4).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .investor import InvestorProfile
from .risk import Breach


class ComplianceDecision(BaseModel):
    """차단/강등/보류 결정 (03 §4, 05 §3).

    - ``ok``       : 상한 통과, 발행.
    - ``downgrade``: 위반 → ``revised_profile``로 한 등급 강등 재배분(pipeline 루프).
    - ``hold``     : 강등 사다리 소진(초안정형까지 미달) → 배정 보류(포트 미발행).
    """

    decision: Literal["ok", "downgrade", "hold"]
    revised_profile: InvestorProfile | None = None
    downgrade_reason: str | None = None
    breaches: list[Breach] = Field(default_factory=list)

    @model_validator(mode="after")
    def _decision_profile_consistency(self) -> ComplianceDecision:
        """역간선 상관 계약: downgrade ⟹ revised_profile 존재, ok/hold ⟹ None.

        pipeline 루프가 downgrade에서 ``profile = dec.revised_profile``을 하므로,
        downgrade인데 None이면 런타임 크래시. 타입이 이 조합을 원천 차단(§4).
        """
        if self.decision == "downgrade" and self.revised_profile is None:
            raise ValueError("downgrade는 revised_profile이 필요합니다(역간선 계약 위반)")
        if self.decision != "downgrade" and self.revised_profile is not None:
            raise ValueError(f"{self.decision}에는 revised_profile이 없어야 합니다")
        return self
