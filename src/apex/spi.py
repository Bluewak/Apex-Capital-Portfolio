"""SPI — 교체 가능 서비스 인터페이스 (v2 §5, 10-v2-pipeline-design).

각 파이프라인 단계를 ``typing.Protocol``로 세우고, pipeline은 **구현이 아니라
인터페이스에 의존(DI)**한다. 룰 구현이 기본 어댑터, v2 최적화·LLM 구현이 계약
불변으로 교체된다(Optimizer=Step 2, Narrator=Step 3).

각 Protocol의 ``DETERMINISM_REQUIRED`` 플래그가 결정론 경계를 표식한다. True인 서비스의
import 그래프엔 LLM(anthropic)/Advisory Plane이 없어야 한다(CI §8-2, test_determinism_boundary).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import pandas as pd

from apex import allocation as _allocation
from apex import compliance as _compliance
from apex import investor as _investor
from apex import risk as _risk
from apex.schemas import (
    Allocation,
    ComplianceDecision,
    InvestorProfile,
    RiskReport,
    SurveyAnswers,
)
from apex.schemas.enums import Profile


# ───────────────────────── Protocols (계약) ─────────────────────────
@runtime_checkable
class InvestorAgent(Protocol):
    DETERMINISM_REQUIRED: bool

    def score(self, answers: SurveyAnswers) -> InvestorProfile: ...


@runtime_checkable
class AllocationEngine(Protocol):
    DETERMINISM_REQUIRED: bool

    def build(self, profile: Profile, min_cash: float) -> Allocation: ...


@runtime_checkable
class RiskEngine(Protocol):
    DETERMINISM_REQUIRED: bool

    def report(
        self, series: pd.Series, alloc: Allocation, display_currency: str, normal_only: bool
    ) -> RiskReport: ...


@runtime_checkable
class ComplianceGuardrail(Protocol):
    DETERMINISM_REQUIRED: bool

    def check(self, risk: RiskReport, profile: InvestorProfile) -> ComplianceDecision: ...


@runtime_checkable
class Optimizer(Protocol):
    """Step 2 Model Plane. CMA + 제약 → 유형 단위 결정론 배분(솔버 핀)."""

    DETERMINISM_REQUIRED: bool

    def solve(self, cma: object, constraints: object) -> dict[str, float]: ...


@runtime_checkable
class Narrator(Protocol):
    """Step 3 Advisory Plane. FactLedger grounding → 서술(LLM 허용 = 비결정론)."""

    DETERMINISM_REQUIRED: bool

    def narrate(self, facts: object) -> str: ...


# ───────────────────────── 기본 어댑터 (룰 구현) ─────────────────────────
class RuleInvestorAgent:
    DETERMINISM_REQUIRED = True

    def score(self, answers: SurveyAnswers) -> InvestorProfile:
        return _investor.score(answers)


class RuleAllocationEngine:
    DETERMINISM_REQUIRED = True

    def build(self, profile: Profile, min_cash: float) -> Allocation:
        return _allocation.build(profile, min_cash=min_cash)


class RuleRiskEngine:
    DETERMINISM_REQUIRED = True

    def report(
        self, series: pd.Series, alloc: Allocation, display_currency: str, normal_only: bool
    ) -> RiskReport:
        return _risk.report(
            series, alloc, display_currency=display_currency, normal_only=normal_only
        )


class RuleComplianceGuardrail:
    DETERMINISM_REQUIRED = True

    def check(self, risk: RiskReport, profile: InvestorProfile) -> ComplianceDecision:
        return _compliance.check(risk, profile)


# ───────────────────────── 서비스 번들 (DI 컨테이너) ─────────────────────────
@dataclass(frozen=True)
class Services:
    """결정론 코어 서비스 묶음. pipeline이 이 번들에 의존(구현 교체 지점)."""

    investor: InvestorAgent
    allocation: AllocationEngine
    risk: RiskEngine
    compliance: ComplianceGuardrail


def default_services() -> Services:
    """기본 = 룰 어댑터. Step 2/3에서 최적화·LLM 구현으로 계약 불변 교체."""
    return Services(
        investor=RuleInvestorAgent(),
        allocation=RuleAllocationEngine(),
        risk=RuleRiskEngine(),
        compliance=RuleComplianceGuardrail(),
    )
