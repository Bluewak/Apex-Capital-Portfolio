"""Step 3 DoD — Serving run_advice (v2 §3.3). 레지스트리 O(1)·forward binding 활성화.

합성 레지스트리(conftest 세션 픽스처) 주입으로 CI 오프라인. 반환은 pipeline.run과
동일 PipelineResult(계약 불변).
"""
from __future__ import annotations

from apex import report, serving
from apex.schemas import SurveyAnswers
from apex.schemas.enums import Profile
from apex.serving import AdviceCommand


def _survey(**kw) -> SurveyAnswers:
    base = dict(
        q1_age=45, q2_horizon=3, q3_objective="균형", q4_capital=1, q5_monthly=0,
        q6_max_loss=-0.15, q7_experience="보통", q8_liquidity="보통",
        q9_fx="일부허용", q10_behavior="유지", input_snapshot_id="t",
    )
    base.update(kw)
    return SurveyAnswers(**base)


def _retiree() -> SurveyAnswers:
    return _survey(q1_age=62, q2_horizon=3, q3_objective="보전", q6_max_loss=-0.05,
                   q7_experience="없음", q9_fx="회피", q10_behavior="매도")


def test_run_advice_ok_uses_forward_binding(synth_registry):
    """은퇴자 → 초안정형 발행, forward 차단 지표 채워짐(실현 아님)."""
    res = serving.run_advice(AdviceCommand(answers=_retiree()), reg=synth_registry)
    assert res.decision == "ok"
    assert res.final_profile == "초안정형"
    assert res.risk.expected_loss_1y_forward is not None  # forward binding 활성
    assert res.allocation.weights  # CMA 최적화 배분


def test_run_advice_forward_binding_downgrades_honestly(synth_registry):
    """공격 요청 + Q6=-15% → forward 손실>binding이라 강등(실현 VaR≈0이라도). §3.5."""
    ans = _survey(q1_age=29, q2_horizon=5, q3_objective="증식", q6_max_loss=-0.15,
                  q7_experience="많음", q10_behavior="추가매수")
    res = serving.run_advice(AdviceCommand(answers=ans), reg=synth_registry)
    assert res.decision == "ok"
    assert res.downgrade_path  # 강등 발생
    assert Profile(res.final_profile).rank < Profile.AGGRESSIVE.rank  # 공격형보다 낮게


def test_run_advice_returns_pipeline_result_contract(synth_registry):
    """serving 산출 = pipeline.run과 동일 계약 → report·해시 재사용."""
    res = serving.run_advice(AdviceCommand(answers=_retiree()), reg=synth_registry)
    assert len(res.numeric_hash) == 64
    assert res.numeric.model_version.startswith("opt-")  # 레지스트리 리니지
    html = report.render(res, _retiree())
    assert html.startswith("<!DOCTYPE html>") and "초안정형" in html


def test_run_advice_narrative_grounded_and_hash_excludes_it(synth_registry):
    """서술은 FactLedger 근거 + 면책. numeric_hash는 서술 미포함(§7)."""
    from apex.pipeline import _canonical_hash

    res = serving.run_advice(AdviceCommand(answers=_retiree()), reg=synth_registry)
    assert "교육" in res.explanation or "권유가 아" in res.explanation
    assert _canonical_hash(res.numeric) == res.numeric_hash  # 서술 무관


def test_run_advice_deterministic(synth_registry):
    r1 = serving.run_advice(AdviceCommand(answers=_retiree()), reg=synth_registry)
    r2 = serving.run_advice(AdviceCommand(answers=_retiree()), reg=synth_registry)
    assert r1.numeric_hash == r2.numeric_hash
