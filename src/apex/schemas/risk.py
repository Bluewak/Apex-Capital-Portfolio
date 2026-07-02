"""RiskReport 스키마 (05 §4 정본) — Risk Engine → Report/Compliance."""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class Concentration(BaseModel):
    max_asset_class: float
    max_etf: float


class StressResult(BaseModel):
    scenario: str
    loss: float
    top_contributor: str | None = None


class Breach(BaseModel):
    """성향별 상한 위반 (05 §3)."""

    metric: str
    limit: float
    actual: float


class RiskReport(BaseModel):
    """리스크 지표. 통화별(현지·KRW) 2종을 각각 저장 (05 §0)."""

    currency: str
    vol_annual: float
    mdd: float = Field(le=0, description="최대낙폭, [-1,0]")
    mdd_recovery_days: int | None = None
    var95_1d: float = Field(description="양수 손실률 표기")
    cvar95_1d: float = Field(description="양수 손실률 표기")
    sharpe: float
    calmar: float
    fx_sensitivity_krw10: float | None = None
    rate_sensitivity_100bp: float | None = None
    concentration: Concentration
    stress: list[StressResult] = Field(default_factory=list)
    breaches: list[Breach] = Field(default_factory=list)

    @model_validator(mode="after")
    def _cvar_ge_var(self) -> RiskReport:
        # 05 §5: 동일 α·보유기간에서 CVaR ≥ VaR
        if self.cvar95_1d < self.var95_1d:
            raise ValueError(
                f"CVaR({self.cvar95_1d}) < VaR({self.var95_1d}) — 05 §5 위반"
            )
        return self
