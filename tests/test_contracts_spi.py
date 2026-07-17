"""Step 1 DoD — 계약 하드닝 + SPI DI (v2 §4·§5).

(a) ComplianceDecision 상관 validator가 불가능 조합을 원천 차단.
(b) Allocation.profile enum화 — 타입 안전 + JSON 직렬화는 값 문자열(해시 안정).
(c) SPI Protocol 준수 + 결정론 플래그.
(d) pipeline이 구현이 아니라 인터페이스에 의존(DI 스왑이 실제로 반영).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from apex import allocation, investor, pipeline, spi
from apex.schemas import ComplianceDecision, SurveyAnswers
from apex.schemas.enums import Profile


def _survey(**kw) -> SurveyAnswers:
    base = dict(
        q1_age=45, q2_horizon=3, q3_objective="균형", q4_capital=1, q5_monthly=0,
        q6_max_loss=-0.15, q7_experience="보통", q8_liquidity="보통",
        q9_fx="일부허용", q10_behavior="유지", input_snapshot_id="t",
    )
    base.update(kw)
    return SurveyAnswers(**base)


# ── (a) ComplianceDecision validator ──
def test_compliance_ok_hold_reject_revised_profile():
    """ok/hold에 revised_profile이 있으면 계약 위반."""
    prof = investor.score(_survey())
    with pytest.raises(ValidationError):
        ComplianceDecision(decision="ok", revised_profile=prof)
    with pytest.raises(ValidationError):
        ComplianceDecision(decision="hold", revised_profile=prof)


def test_compliance_downgrade_requires_revised_profile():
    """downgrade인데 revised_profile이 None이면 계약 위반(pipeline 크래시 원천 차단)."""
    with pytest.raises(ValidationError):
        ComplianceDecision(decision="downgrade", revised_profile=None)


def test_compliance_valid_combos_pass():
    prof = investor.score(_survey())
    assert ComplianceDecision(decision="ok").decision == "ok"
    assert ComplianceDecision(decision="hold").decision == "hold"
    assert ComplianceDecision(decision="downgrade", revised_profile=prof).decision == "downgrade"


# ── (b) Allocation.profile enum ──
def test_allocation_profile_is_enum_but_serializes_to_value():
    a = allocation.build(Profile.NEUTRAL)
    assert a.profile is Profile.NEUTRAL  # 타입 안전(str 아님)
    # StrEnum → JSON 직렬화는 값 문자열 → 기존 numeric_hash 불변(회귀 안전)
    assert a.model_dump(mode="json")["profile"] == "중립형"


# ── (c) SPI Protocol 준수 + 결정론 플래그 ──
def test_default_services_conform_to_protocols():
    svc = spi.default_services()
    assert isinstance(svc.investor, spi.InvestorAgent)
    assert isinstance(svc.allocation, spi.AllocationEngine)
    assert isinstance(svc.risk, spi.RiskEngine)
    assert isinstance(svc.compliance, spi.ComplianceGuardrail)


def test_core_services_are_determinism_required():
    svc = spi.default_services()
    for s in (svc.investor, svc.allocation, svc.risk, svc.compliance):
        assert s.DETERMINISM_REQUIRED is True


# ── (d) DI 스왑이 실제 반영 ──
class _StubUltraInvestor:
    """주입된 InvestorAgent가 강제로 초안정형을 반환 → pipeline이 이를 사용함을 증명."""

    DETERMINISM_REQUIRED = True

    def score(self, answers):
        return investor.score(answers).model_copy(
            update={"profile": Profile.ULTRA_CONSERVATIVE}
        )


def test_pipeline_uses_injected_investor_agent():
    ans = _survey(q1_age=29, q2_horizon=5, q3_objective="증식", q6_max_loss=-0.25,
                  q7_experience="많음", q10_behavior="추가매수")
    default_res = pipeline.run(ans)
    custom = spi.Services(
        investor=_StubUltraInvestor(),
        allocation=spi.RuleAllocationEngine(),
        risk=spi.RuleRiskEngine(),
        compliance=spi.RuleComplianceGuardrail(),
    )
    injected_res = pipeline.run(ans, services=custom)

    assert injected_res.final_profile == "초안정형"  # 주입된 에이전트 경로
    assert default_res.final_profile != "초안정형"  # 기본 경로와 다름 → DI가 실제 작동


# ── (e) 버전 전파 ──
def test_model_and_schema_version_propagated():
    res = pipeline.run(_survey())
    assert res.numeric.model_version == "rule-mp-v1"
    assert res.numeric.schema_version == "2"
    payload = res.numeric.model_dump(mode="json")
    assert payload["model_version"] and payload["schema_version"]
