"""KG compliance 구조 검증 (docs/12 §3, docs/10 §3.5) — 집중도·밴드·근거경로.

var(차단)과 독립으로 배분 구조를 검증. **골든 동일성**: 최적화·룰 배분은 위반 0
(행동 변화 0)이되, 실제 위반은 근거경로와 함께 검출.
"""
from __future__ import annotations

from datetime import date

from apex import allocation, compliance
from apex.schemas import Allocation, Constraints, InvestorProfile
from apex.schemas.enums import Profile


def _prof(p: Profile) -> InvestorProfile:
    return InvestorProfile(
        risk_score=50, profile=p, horizon_years=6, max_annual_loss=-0.15,
        liquidity_need="보통", fx_preference="일부허용", constraints=Constraints(),
    )


def test_rule_allocations_pass_golden():
    """모든 성향의 룰 배분은 구조 위반 0(행동 변화 0). docs/12 §9."""
    for p in Profile:
        alloc = allocation.build(p)
        assert compliance.structural_breaches(alloc, _prof(p)) == []


def test_concentration_hardcap_detected_with_path():
    """단일 ETF 집중 하드캡(주식 30%) 초과 → breach + 근거경로."""
    bad = Allocation(profile=Profile.CONSERVATIVE, model_portfolio="MP-Conservative",
                     weights={"SPY": 0.40, "AGG": 0.60}, as_of=date(2026, 7, 17))
    breaches = compliance.structural_breaches(bad, _prof(Profile.CONSERVATIVE))
    conc = [b for b in breaches if b.metric == "concentration:SPY"]
    assert conc and conc[0].actual == 0.40 and conc[0].limit == 0.30
    assert conc[0].because == ["SPY"]


def test_band_violation_detected_with_path():
    """자산군 밴드 위반 → breach + 근거경로(기여 자산)."""
    # CONS인데 현금 0% → CASH 밴드(0.03,0.15) 하한 위반
    bad = Allocation(profile=Profile.CONSERVATIVE, model_portfolio="MP-Conservative",
                     weights={"SPY": 0.40, "AGG": 0.60}, as_of=date(2026, 7, 17))
    breaches = compliance.structural_breaches(bad, _prof(Profile.CONSERVATIVE))
    band = [b for b in breaches if b.metric == "band:CASH"]
    assert band and band[0].actual == 0.0  # 현금 0 < 하한 0.03


def test_currency_band_uses_lookthrough():
    """근거경로가 KG 이행 클로저 기반(EFA도 '주식' 기여)."""
    bad = Allocation(profile=Profile.AGGRESSIVE, model_portfolio="MP-Aggressive",
                     weights={"IEF": 0.60, "AGG": 0.40}, as_of=date(2026, 7, 17))
    breaches = compliance.structural_breaches(bad, _prof(Profile.AGGRESSIVE))
    # 공격형인데 주식 0 → EQ 밴드(0.80,0.95) 하한 위반, 근거경로는 비어있음(주식 자산 없음)
    eq = [b for b in breaches if b.metric == "band:EQ"]
    assert eq and eq[0].actual == 0.0 and eq[0].because == []
