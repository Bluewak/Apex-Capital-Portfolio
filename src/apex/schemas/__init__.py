"""서비스 계약 스키마 (06 §3). 모든 컴포넌트 경계는 이 pydantic 모델로만 소통."""
from __future__ import annotations

from .allocation import Allocation
from .backtest import BacktestResult, Period, ScenarioResult
from .compliance import ComplianceDecision
from .enums import Behavior, Experience, FxPreference, Liquidity, Objective, Profile
from .investor import Constraints, InvestorProfile
from .ips import IPSDocument
from .risk import Breach, Concentration, RiskReport, StressResult
from .survey import SurveyAnswers

__all__ = [
    "Allocation",
    "BacktestResult",
    "Period",
    "ScenarioResult",
    "ComplianceDecision",
    "Behavior",
    "Experience",
    "FxPreference",
    "Liquidity",
    "Objective",
    "Profile",
    "Constraints",
    "InvestorProfile",
    "IPSDocument",
    "Breach",
    "Concentration",
    "RiskReport",
    "StressResult",
    "SurveyAnswers",
]
