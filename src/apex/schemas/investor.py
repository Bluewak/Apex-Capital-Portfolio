"""InvestorProfile 스키마 (03 §5 정본) — Investor Agent → IPS/Allocation."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import FxPreference, Liquidity, Profile


class InvestorProfile(BaseModel):
    """위험점수·성향과 제약을 담은 투자자 프로파일 (03 §5)."""

    risk_score: int = Field(ge=0, le=100)
    profile: Profile
    horizon_years: int = Field(ge=0)
    max_annual_loss: float = Field(le=0, description="연간 최대 손실 감내, 음수")
    liquidity_need: Liquidity
    fx_preference: FxPreference
    constraints: list[str] = Field(default_factory=list)
