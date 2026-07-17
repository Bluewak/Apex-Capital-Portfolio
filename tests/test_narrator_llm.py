"""G — LLM Narrator 어댑터(Ollama) + 한국어 조사 결정론 후검증 (v2 §3.4).

로컬 모델은 게이트+캐시+폴백 안전망 위에서. 조사 받침 정합이 작은 모델 대표 오류를 차단.
Ollama 미실행 시 룰 폴백(무손실). 모델 실행 없이 검증(연결거부→폴백).
"""
from __future__ import annotations

from apex import advisory
from apex.factledger import FactLedger


def _ledger(decision="ok") -> FactLedger:
    if decision == "ok":
        return FactLedger(
            profile_label="중립형", decision="ok",
            facts={"기대수익": "5%", "평시변동성": "10%", "forward기대손실": "13%"},
            numbers=["5%", "10%", "13%"],
        )
    return FactLedger(profile_label="초안정형", decision="hold", facts={}, numbers=[])


# ── 조사 받침 정합 ──
def test_josa_agreement_detects_errors():
    assert advisory.josa_ok("자산을 배분합니다.")  # 산(받침)+을 OK
    assert advisory.josa_ok("주식과 채권을 담습니다.")  # 식(받침)+과 OK
    assert not advisory.josa_ok("수익를 봅니다.")  # 익(받침)+를 오류
    assert not advisory.josa_ok("주식와 채권.")  # 식(받침)+와 오류
    assert advisory.josa_ok("맞는 예시이고 있는 자료입니다.")  # 동사어미 는 미검사(오탐 방지)
    assert advisory.josa_ok("no korean josa here 5%")  # 한글 없음 → OK


def test_rule_narrator_passes_josa_gate():
    """룰 Narrator 산출은 조사 게이트 통과(무손실 폴백 성립 필수)."""
    for dec in ("ok", "hold"):
        led = _ledger(dec)
        text = advisory.RuleNarrator().narrate(led)
        assert advisory.josa_ok(text)
        assert advisory.advisory_gate(text, led)


def test_gate_rejects_josa_error():
    led = _ledger()
    assert not advisory.advisory_gate("자산를 5% 담습니다. 교육용.", led)  # 산(받침)+를 오류로 폐기


# ── QwenNarrator(Ollama) 어댑터 ──
def test_qwen_narrator_metadata():
    q = advisory.QwenNarrator(model="qwen2.5:7b")
    assert q.DETERMINISM_REQUIRED is False
    assert q.model_id == "ollama:qwen2.5:7b"
    assert isinstance(advisory._build_prompt(_ledger()), str)


def test_qwen_falls_back_when_ollama_absent():
    """Ollama 미실행(연결 거부) → 예외 → 룰 폴백(게이트 통과). 모델 없이 검증."""
    led = _ledger()
    q = advisory.QwenNarrator(base_url="http://127.0.0.1:1/v1", timeout=0.5)
    out = advisory.narrate(led, narrator=q)
    assert "보장" not in out and advisory.advisory_gate(out, led)  # 룰 폴백 산출
