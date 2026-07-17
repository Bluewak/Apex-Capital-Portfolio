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
    """리스크 지표 (05 §4 R3).

    바인딩(차단) 지표는 ``var95_annual`` — MDD가 아니다(R5, MDD -5%는 20년·무splice로 불가).
    MVP는 ``calc_currency``(USD) 1세트 + KRW 표시 환산(이중 재계산·저장은 v2).
    """

    calc_currency: str = Field(default="USD", description="계산 기준 통화(현지, 05 §0)")
    display_currency: str = Field(default="KRW")
    vol_annual: float
    mdd: float = Field(le=0, description="평시 최대낙폭, [-1,0]")
    mdd_recovery_days: int | None = None
    var95_1d: float = Field(description="양수 손실률 표기")
    cvar95_1d: float = Field(description="양수 손실률 표기")
    var95_annual: float = Field(description="연율 VaR95(평시)·양수손실률 — 실현 지표(disclosed)")
    expected_loss_1y_forward: float | None = Field(
        default=None,
        description="forward 1년 기대손실(CMA 기반, 양수) — 있으면 compliance 차단 지표(v2 §3.5)",
    )
    sharpe: float
    calmar: float
    currency_exposure: dict[str, float] = Field(
        default_factory=dict, description="통화별 노출 비중(예: {'USD':0.92})"
    )
    concentration: Concentration
    stress: list[StressResult] = Field(
        default_factory=list, description="disclosed 스트레스(차단 아님, R3)"
    )
    breaches: list[Breach] = Field(default_factory=list)

    @model_validator(mode="after")
    def _cvar_ge_var(self) -> RiskReport:
        # 05 §5: 동일 α·보유기간에서 CVaR ≥ VaR
        if self.cvar95_1d < self.var95_1d:
            raise ValueError(f"CVaR({self.cvar95_1d}) < VaR({self.var95_1d}) — 05 §5 위반")
        return self
