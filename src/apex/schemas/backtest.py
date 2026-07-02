"""BacktestResult 스키마 (06 §3.4) — Backtest Engine 출력."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Period(BaseModel):
    start: str
    end: str


class ScenarioResult(BaseModel):
    """스트레스 시나리오 결과 (05 §2)."""

    name: str
    loss: float
    top_contributor: str | None = None


class BacktestResult(BaseModel):
    """백테스트 결과. 벤치마크 3종(S&P500/60·40/KOSPI200) 필수 (01 §5)."""

    model_config = ConfigDict(protected_namespaces=())

    currency_calc: str = "USD"
    period: Period
    returns_daily_ref: str
    cagr: float
    cumulative: float
    benchmarks: dict[str, dict] = Field(default_factory=dict)
    scenarios: list[ScenarioResult] = Field(default_factory=list)
    model_version: str = "bt-v1"
