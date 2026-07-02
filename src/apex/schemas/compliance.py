"""ComplianceDecision 스키마 (06 §3.6) — Compliance Guardrail 출력."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .risk import Breach


class ComplianceDecision(BaseModel):
    """차단/강등/통과 결정 (03 §4, 05 §3)."""

    decision: Literal["pass", "downgrade", "block"]
    final_profile: str
    downgrade_reason: str | None = None
    breaches: list[Breach] = Field(default_factory=list)
