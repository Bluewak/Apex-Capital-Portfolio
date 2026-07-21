"""Allocation 스키마 (06 §3.3) — Allocation Engine 출력."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import Profile


class Allocation(BaseModel):
    """성향 → 모델포트폴리오 배분(티커·비중). weights 합=1.0, 음수 불가 (06 §3.3)."""

    model_config = ConfigDict(protected_namespaces=())  # model_portfolio/model_version 허용

    profile: Profile  # str→enum(Step 1 타입 안전). StrEnum이라 JSON 직렬화는 값 문자열 동일
    model_portfolio: str
    weights: dict[str, float]
    rebalance_band_pp: float = Field(default=5, description="리밸런싱 밴드(±%p)")
    as_of: date
    model_version: str = "alloc-v1"

    @model_validator(mode="after")
    def _validate_weights(self) -> Allocation:
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"weights 합이 1.0이 아님: {total:.6f}")
        if any(w < 0 for w in self.weights.values()):
            raise ValueError("weights에 음수 비중 불가")
        return self
