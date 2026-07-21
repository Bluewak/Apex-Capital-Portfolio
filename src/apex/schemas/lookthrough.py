"""LookthroughReport 스키마 (v3-A Step 1 · docs/13 §3, Tier 0 분석).

ETF 포트를 개별종목으로 **분해**한 disclosed 분석 — 종목은 여기서 노출·집중도·근거로만
등장하고 **numeric_hash·배분 비중에는 들어가지 않는다**(Tier 0 규제 경계, docs/13 §2·§3).
holdings top-N 기반이라 `coverage<1`(부분 룩스루)임을 각인.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from apex.schemas.risk import Breach


class StockConcentration(BaseModel):
    """실효 개별종목 집중도(룩스루)."""

    top_stock: str | None = None
    top_weight: float = 0.0
    top5_sum: float = 0.0
    herfindahl: float = Field(0.0, description="실효 종목비중 제곱합(집중도)")
    n_stocks: int = 0


class LookthroughReport(BaseModel):
    """Tier 0 종목 룩스루 분석(disclosed). 배분 판정과 분리 — 규제 안전."""

    coverage: float = Field(description="특정 종목으로 추적된 포트 비중(top-N이라 <1)")
    single_stock_cap: float = Field(description="단일종목 실효 집중 상한(disclosed 경고 기준)")
    concentration: StockConcentration
    stock_exposure: dict[str, float] = Field(
        default_factory=dict, description="실효 종목 노출(top 표시)"
    )
    theme_exposure: dict[str, float] = Field(
        default_factory=dict, description="테마군 노출(룩스루)"
    )
    currency_exposure: dict[str, float] = Field(default_factory=dict)
    breaches: list[Breach] = Field(
        default_factory=list, description="단일종목 집중 초과(disclosed 경고, 차단 아님)"
    )
