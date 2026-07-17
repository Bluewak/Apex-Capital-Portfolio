"""Step 3 DoD — 웹 브리지 (v2 §7). stdlib http.server, 의존성 0. 순수 handle_advice 검증."""
from __future__ import annotations

from apex import web
from apex.schemas import SurveyAnswers


def _retiree() -> SurveyAnswers:
    return SurveyAnswers(
        q1_age=62, q2_horizon=3, q3_objective="보전", q4_capital=1, q5_monthly=0,
        q6_max_loss=-0.05, q7_experience="없음", q8_liquidity="보통",
        q9_fx="회피", q10_behavior="매도", input_snapshot_id="web",
    )


def test_form_served_has_all_questions():
    for field in ("q1_age", "q6_max_loss", "q9_fx", "q10_behavior"):
        assert field in web._FORM
    assert "투자권유" in web._FORM  # 면책 프레이밍


def test_handle_advice_bad_input_returns_400():
    status, html = web.handle_advice(b'{"q1_age": "not-a-number"}')
    assert status == 400 and "오류" in html


def test_handle_advice_ok_returns_report(monkeypatch, synth_registry):
    """정상 설문 → 200 + HTML 리포트(레지스트리 주입)."""
    monkeypatch.setattr("apex.registry.load_latest", lambda *a, **k: synth_registry)
    status, html = web.handle_advice(_retiree().model_dump_json().encode("utf-8"))
    assert status == 200
    assert html.startswith("<!DOCTYPE html>") and "초안정형" in html
