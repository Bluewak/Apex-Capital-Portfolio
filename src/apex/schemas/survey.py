"""설문 응답 스키마 (06 §3.1) — Investor Agent 입력."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import Behavior, Experience, FxPreference, Liquidity, Objective


class SurveyAnswers(BaseModel):
    """투자자 설문 응답 (03 §1)."""

    q1_age: int = Field(ge=0, le=120)
    q2_horizon: int = Field(ge=1, le=5, description="1(<3년)~5(10년+)")
    q3_objective: Objective
    q4_capital: int = Field(ge=0, description="투자금 규모(원)")
    q5_monthly: int = Field(ge=0, description="월 적립 가능액(원)")
    q6_max_loss: float = Field(le=0, description="최대 손실 감내(1년), 음수 예: -0.20")
    q7_experience: Experience
    q8_liquidity: Liquidity
    q9_fx: FxPreference
    q10_behavior: Behavior
    input_snapshot_id: str
    survey_version: str = "v1"
