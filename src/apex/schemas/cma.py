"""CMASet 스키마 (v2 §3.2·§4) — Capital Market Assumptions.

기대수익(μ)은 **forward 빌딩블록**(주식 Grinold-Kroner, 채권 YTM+롤다운−신용손실,
금 인플레), 공분산(Σ)은 데이터에서 **Ledoit-Wolf shrinkage**로 추정. 강세장 표본
평균을 그대로 쓰면 기대수익 과대·forward 리스크 과소(착시)라 μ를 표본에서 떼어낸다.
"""
from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict, Field


class CMASet(BaseModel):
    """자본시장 가정 집합. Optimizer·forward risk의 단일 입력(결정론·버전드)."""

    model_config = ConfigDict(protected_namespaces=())

    tickers: list[str]
    mu: dict[str, float] = Field(description="연 기대수익(빌딩블록)")
    vol: dict[str, float] = Field(description="연 변동성(LW shrinkage 대각)")
    cov: list[list[float]] = Field(description="연 공분산 행렬(tickers 순서, LW shrinkage)")
    shrinkage: float = Field(ge=0, le=1, description="Ledoit-Wolf 수축 계수 δ")
    as_of: str
    data_version: str
    cma_version: str = Field(description="(data_version, 가정, 방법)의 해시 — 리니지")

    def mu_vec(self) -> np.ndarray:
        return np.array([self.mu[t] for t in self.tickers], dtype=float)

    def cov_mat(self) -> np.ndarray:
        return np.array(self.cov, dtype=float)
