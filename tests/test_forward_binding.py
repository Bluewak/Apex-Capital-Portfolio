"""Step 2d DoD — compliance 차단 지표 forward 교체 (v2 §3.5).

expected_loss_1y_forward가 있으면 forward 기대손실로 차단, 없으면 실현 VaR로(하위호환).
forward는 강세장 착시를 배제 → out-of-sample에서도 정직하게 리스크 적립.
"""
from __future__ import annotations

from apex import compliance
from apex.schemas import Concentration, Constraints, InvestorProfile, RiskReport
from apex.schemas.enums import Profile


def _rr(var_annual: float, forward: float | None = None) -> RiskReport:
    return RiskReport(
        calc_currency="USD", display_currency="KRW",
        vol_annual=0.1, mdd=-0.1, var95_1d=0.02, cvar95_1d=0.03,
        var95_annual=var_annual, expected_loss_1y_forward=forward,
        sharpe=0.5, calmar=0.5,
        concentration=Concentration(max_asset_class=0.5, max_etf=0.3),
    )


def _prof(p: Profile, q6: float = -0.20) -> InvestorProfile:
    return InvestorProfile(
        risk_score=50, profile=p, horizon_years=6, max_annual_loss=q6,
        liquidity_need="보통", fx_preference="일부허용", constraints=Constraints(),
    )


def test_forward_binding_used_when_present():
    """forward 손실 ≤ binding → ok, 지표는 forward."""
    dec = compliance.check(_rr(var_annual=0.0, forward=0.10), _prof(Profile.NEUTRAL, q6=-0.20))
    assert dec.decision == "ok"  # forward 0.10 ≤ min(0.15, 0.20)


def test_forward_binding_downgrades_on_excess():
    """forward 손실 > binding → 강등(실현 VaR이 0이라도). §3.5 핵심."""
    # 공격형인데 실현 VaR=0(강세장) but forward 0.30 > min(0.32,|−0.15|)=0.15
    dec = compliance.check(_rr(var_annual=0.0, forward=0.30), _prof(Profile.AGGRESSIVE, q6=-0.15))
    assert dec.decision == "downgrade"
    assert dec.revised_profile.profile == Profile.GROWTH
    assert dec.breaches[-1].metric == "expected_loss_1y_forward"


def test_realized_fallback_when_forward_absent():
    """forward 없으면 실현 var95_annual로 차단(하위호환)."""
    dec = compliance.check(_rr(var_annual=0.20, forward=None), _prof(Profile.NEUTRAL, q6=-0.10))
    assert dec.decision == "downgrade"  # 0.20 > min(0.15, 0.10)=0.10
    assert dec.breaches[-1].metric == "var95_annual"


def test_forward_ultra_preserved():
    """R5: 초안정형 forward 3.1% ≤ 5% → 발행 유지(hold 아님)."""
    dec = compliance.check(
        _rr(var_annual=0.0, forward=0.031), _prof(Profile.ULTRA_CONSERVATIVE, q6=-0.05)
    )
    assert dec.decision == "ok"
