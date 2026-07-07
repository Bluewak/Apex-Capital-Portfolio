"""ComplianceDecision 스키마 (06 §3.6) — Compliance Guardrail 출력.

R3 역간선 1급 계약: compliance→allocation 재배분을 문자열이 아니라
``revised_profile: InvestorProfile | None`` 객체로 전달한다(강등 시 constraints 보존).
decision ∈ {ok, downgrade, hold} (R4).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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
