"""Model Registry 스키마 (v2 §3.2·§4) — 사전연산 그리드 + 리니지.

5성향 × min_cash 그리드를 data_version×model_version당 1회 사전연산해 봉인.
사용자 런(Step 3)은 이 레지스트리를 O(1) 조회 → 20년 백테스트 반복 없음.
리니지((data_version, cma_version, model_version, env_hash))를 각인해 재현·감사.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .allocation import Allocation
from .enums import Profile
from .risk import RiskReport


class ForwardRisk(BaseModel):
    """CMA 기반 forward 리스크(compliance 차단 지표). 실현치 아님."""

    expected_return: float = Field(description="연 forward 기대수익 μ_p")
    vol: float = Field(description="연 forward 변동성")
    expected_loss_1y: float = Field(description="forward 1년 5% 꼬리 기대손실(양수)")


class ValidationResult(BaseModel):
    """검증 게이트 결과 (v2 §3.2). 통계적 방어(과최적화·꼬리·OOS)."""

    psr: float = Field(description="Deflated PSR = P(참 Sharpe > 다중검정 SR*)")
    kupiec_p: float = Field(description="Kupiec POF p값(VaR 커버리지)")
    kupiec_pass: bool
    oos_stable: bool = Field(description="IS/OOS Sharpe 부호 안정")
    passed: bool = Field(description="종합 통과(PSR·Kupiec·OOS)")


class PrecomputedEntry(BaseModel):
    """(성향 × min_cash) 1칸 = 배분 + forward(차단) + 실현(disclosed) + 검증 게이트."""

    model_config = ConfigDict(protected_namespaces=())

    profile: Profile
    min_cash: float
    allocation: Allocation
    forward: ForwardRisk
    realized: RiskReport | None = None  # 실현 평시 RiskReport(백테스트, disclosed)
    validation: ValidationResult | None = None  # 검증 게이트(PSR·Kupiec·OOS)


class Registry(BaseModel):
    """사전연산 레지스트리(버전드·리니지 각인). Step 3 서빙이 조회."""

    cma_version: str
    data_version: str
    model_version: str  # optimizer 방법 버전
    env_hash: str
    as_of: str
    min_cash_grid: list[float]
    entries: list[PrecomputedEntry] = Field(default_factory=list)

    def lookup(self, profile: Profile, min_cash: float) -> PrecomputedEntry:
        """성향 + min_cash → 엔트리. min_cash는 그리드 중 ≤ 요청의 최대(보수)로 스냅."""
        levels = sorted({e.min_cash for e in self.entries if e.profile == profile})
        chosen = max((lv for lv in levels if lv <= min_cash + 1e-9), default=levels[0])
        for e in self.entries:
            if e.profile == profile and abs(e.min_cash - chosen) < 1e-9:
                return e
        raise KeyError(f"레지스트리에 ({profile}, {min_cash}) 없음")
