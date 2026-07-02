"""06 §3 계약(schemas) 검증 테스트."""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from apex.schemas import (
    Allocation,
    Concentration,
    InvestorProfile,
    Profile,
    RiskReport,
    SurveyAnswers,
)

GROWTH_WEIGHTS = {
    "SPY": 0.45, "QQQ": 0.15, "EFA": 0.10, "EEM": 0.05,
    "IEF": 0.10, "TLT": 0.05, "GLD": 0.05, "SHY": 0.05,
}


def test_survey_answers_valid():
    s = SurveyAnswers(
        q1_age=41, q2_horizon=4, q3_objective="증식", q4_capital=50_000_000,
        q5_monthly=800_000, q6_max_loss=-0.20, q7_experience="보통",
        q8_liquidity="낮음", q9_fx="일부허용", q10_behavior="유지",
        input_snapshot_id="uuid-1",
    )
    assert s.survey_version == "v1"


def test_survey_rejects_positive_max_loss():
    with pytest.raises(ValidationError):
        SurveyAnswers(
            q1_age=41, q2_horizon=4, q3_objective="증식", q4_capital=1, q5_monthly=0,
            q6_max_loss=0.10, q7_experience="보통", q8_liquidity="낮음",
            q9_fx="허용", q10_behavior="유지", input_snapshot_id="x",
        )


def test_investor_profile_and_model_portfolio():
    p = InvestorProfile(
        risk_score=62, profile="성장형", horizon_years=8, max_annual_loss=-0.20,
        liquidity_need="낮음", fx_preference="일부허용", constraints=["현금 최소 5%"],
    )
    assert p.profile is Profile.GROWTH
    assert p.profile.model_portfolio == "MP-Growth"


def test_investor_profile_score_out_of_range():
    with pytest.raises(ValidationError):
        InvestorProfile(
            risk_score=150, profile="성장형", horizon_years=8, max_annual_loss=-0.2,
            liquidity_need="낮음", fx_preference="허용",
        )


def test_allocation_weights_sum_ok():
    a = Allocation(
        profile="성장형", model_portfolio="MP-Growth",
        weights=GROWTH_WEIGHTS, as_of=date(2026, 7, 3),
    )
    assert abs(sum(a.weights.values()) - 1.0) < 1e-9


def test_allocation_weights_sum_bad():
    with pytest.raises(ValidationError):
        Allocation(
            profile="성장형", model_portfolio="MP-Growth",
            weights={"SPY": 0.5, "QQQ": 0.4}, as_of=date(2026, 7, 3),
        )


def test_allocation_rejects_negative_weight():
    with pytest.raises(ValidationError):
        Allocation(
            profile="공격형", model_portfolio="MP-Aggressive",
            weights={"SPY": 1.2, "TLT": -0.2}, as_of=date(2026, 7, 3),
        )


def test_risk_report_cvar_ge_var():
    with pytest.raises(ValidationError):
        RiskReport(
            currency="KRW", vol_annual=0.11, mdd=-0.17, var95_1d=0.03, cvar95_1d=0.02,
            sharpe=0.6, calmar=0.4, concentration=Concentration(max_asset_class=0.3, max_etf=0.3),
        )


def test_risk_report_valid():
    r = RiskReport(
        currency="KRW", vol_annual=0.11, mdd=-0.17, mdd_recovery_days=210,
        var95_1d=0.018, cvar95_1d=0.026, sharpe=0.68, calmar=0.41,
        concentration=Concentration(max_asset_class=0.30, max_etf=0.30),
    )
    assert r.cvar95_1d >= r.var95_1d
