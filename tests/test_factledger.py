"""Step 3 DoD — FactLedger 화이트리스트·밴드·PII 없음 (v2 §3.4)."""
from __future__ import annotations

from datetime import date

from apex import factledger
from apex.schemas import Allocation, Concentration, NumericResult, RiskReport
from apex.schemas.enums import Profile


def _numeric_ok() -> NumericResult:
    alloc = Allocation(
        profile=Profile.NEUTRAL, model_portfolio="MP-Neutral",
        weights={"SPY": 0.40, "AGG": 0.35, "SHY": 0.25}, as_of=date(2026, 7, 17),
    )
    rr = RiskReport(
        calc_currency="USD", display_currency="KRW", vol_annual=0.10, mdd=-0.15,
        var95_1d=0.02, cvar95_1d=0.03, var95_annual=0.02, expected_loss_1y_forward=0.138,
        sharpe=0.5, calmar=0.4, concentration=Concentration(max_asset_class=0.4, max_etf=0.4),
    )
    return NumericResult(
        decision="ok", final_profile="중립형", risk_score=50, allocation=alloc, risk=rr,
        expected_cagr=0.053, data_version="dv",
    )


def test_ledger_bands_only_no_raw_amounts():
    led = factledger.extract(_numeric_ok())
    assert led.profile_label == "중립형" and led.decision == "ok"
    assert all(n.endswith("%") for n in led.numbers)  # 밴드 %만(개별 금액·PII 없음)
    assert led.facts["forward기대손실"] == "14%"  # 0.138 → 14% 밴드
    assert any(k.startswith("비중:") for k in led.facts)  # 상위 비중 밴드


def test_ledger_hold_minimal():
    n = NumericResult(decision="hold", final_profile="초안정형", risk_score=8, data_version="dv")
    led = factledger.extract(n)
    assert led.decision == "hold" and led.numbers == []  # 발행 없음 → 숫자 없음
