"""Step 3 DoD — Advisory Plane 격리·게이트 (v2 §3.4).

자문 게이트: 수치충실도(서술 숫자 ⊆ FactLedger)·금칙어·면책존재. 실패 → 룰 폴백.
"""
from __future__ import annotations

from apex import advisory
from apex.factledger import FactLedger


def _ledger(**kw) -> FactLedger:
    base = dict(profile_label="중립형", decision="ok",
                facts={"기대수익": "5%"}, numbers=["5%", "10%"])
    base.update(kw)
    return FactLedger(**base)


def test_gate_accepts_grounded_disclaimed_text():
    assert advisory.advisory_gate("기대 수익 약 5% 수준입니다. 교육용 정보입니다.", _ledger())


def test_gate_rejects_number_not_in_ledger():
    """서술이 원장에 없는 숫자를 쓰면 폐기(창작 방지)."""
    assert not advisory.advisory_gate("기대 수익 99% 입니다. 교육용.", _ledger())


def test_gate_rejects_forbidden_words():
    """단정·보장·개인지시 금칙."""
    assert not advisory.advisory_gate("수익 보장 5% 교육용.", _ledger())


def test_gate_requires_disclaimer():
    assert not advisory.advisory_gate("5% 배분입니다.", _ledger())


def test_rule_narrator_passes_own_gate():
    """룰 Narrator 산출은 항상 게이트 통과(무손실 폴백 근거)."""
    led = _ledger(facts={"기대수익": "5%", "평시변동성": "10%", "forward기대손실": "13%"},
                  numbers=["5%", "10%", "13%"])
    text = advisory.RuleNarrator().narrate(led)
    assert advisory.advisory_gate(text, led)


def test_narrate_caches_and_falls_back():
    """narrate는 캐시 결정론 + 게이트 실패 시 룰 폴백."""
    led = _ledger()

    class _BadNarrator:
        DETERMINISM_REQUIRED = False

        def narrate(self, ledger):
            return "수익 보장 100%!"  # 금칙어+창작 → 게이트 실패

    out = advisory.narrate(led, narrator=_BadNarrator())
    assert "보장" not in out  # 룰 폴백으로 대체
    assert advisory.narrate(led) == advisory.narrate(led)  # 캐시 결정론
