"""IPSDocument 스키마 (04) — IPS Agent 출력."""
from __future__ import annotations

from pydantic import BaseModel, Field


class IPSDocument(BaseModel):
    """투자정책서 구조화 필드 + 렌더링 텍스트 (04 §1·§2)."""

    objective: str  # 투자 목적 (Q3)
    horizon_years: int  # 투자 기간 (Q2)
    target_return_note: str | None = None  # 목표 수익률(참고)
    max_loss: float = Field(le=0)  # 허용 손실 범위 (Q6)
    asset_bands: dict[str, str] = Field(default_factory=dict)  # 자산군 허용 범위(성향별 밴드)
    saa: dict[str, float] = Field(default_factory=dict)  # 기준 배분(SAA)
    rebalance_rule: str = "목표 대비 ±5%p 이탈 시 검토"
    hedge_policy: str | None = None  # 환헤지 정책 (Q9)
    prohibited: list[str] = Field(default_factory=lambda: ["레버리지·인버스 ETF"])
    benchmark: str = "60/40 대비 위험조정성과"
    change_condition: str = "성향/목적/기간 변동 시 재작성"
    market_turmoil_action: str = "밴드 이탈 전 임의 매도 금지"
    rendered_text: str | None = None
    version: int = 1
