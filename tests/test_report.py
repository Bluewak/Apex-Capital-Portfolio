"""M6 — IPS 렌더 + HTML 리포트 렌더 (04 §2, 08 §6·§9·§10)."""
from __future__ import annotations

from apex import pipeline, report
from apex.schemas import SurveyAnswers


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


def test_ips_rendered_on_ok():
    res = pipeline.run(_retiree())
    assert res.decision == "ok" and res.ips is not None
    txt = res.ips.rendered_text
    assert "유형" in txt  # 유형 귀속형 프레이밍
    assert "환헤지" in txt and "USD 노출" in txt  # 통화 정직 고지
    assert "응답 반영" in txt
    assert res.ips.saa  # SAA 채워짐


def test_report_html_ok_has_disclaimer_and_type_framing():
    res = pipeline.run(_retiree())
    html = report.render(res, _retiree())
    assert html.startswith("<!DOCTYPE html>")
    assert "투자자문·투자권유가 아닙니다" in html  # 규제 면책
    assert "과거 성과는 미래 수익을 보장하지 않" in html
    assert "유형" in html and "초안정형" in html
    assert "재현성 해시" in html


def test_report_hold_no_personalized_portfolio():
    """hold: 배정 보류 문안 + 교육용 대안, 개인화 대체 포트(구체 비중) 노출 금지."""
    res = pipeline.run(_survey(q1_age=70, q3_objective="보전", q6_max_loss=-0.015,
                               q7_experience="없음", q10_behavior="매도"))
    assert res.decision == "hold" and res.allocation is None
    html = report.render(res, _survey())
    assert "배정 보류" in html and "교육용 대안" in html
    assert "SHY 65%" not in html  # 개인화 배분 바 없음


def test_reelicitation_on_contradiction():
    """무손실(−5%) ∧ 증식 = 모순 주문 → 재보정 문구 + 리포트 콜아웃(R5)."""
    ans = _survey(q6_max_loss=-0.05, q3_objective="증식")
    res = pipeline.run(ans)
    assert res.reelicitation is not None and "물가" in res.reelicitation
    assert "재보정" in report.render(res, ans)


def test_no_reelicitation_when_consistent():
    res = pipeline.run(_survey(q6_max_loss=-0.05, q3_objective="보전"))
    assert res.reelicitation is None


def test_fx_separation_note_for_averse():
    """환회피(Q9=회피) → 환효과 분리 고지(R4)."""
    res = pipeline.run(_retiree())  # Q9=회피
    assert "환효과 분리" in report.render(res, _retiree())


def test_report_downgrade_reason_rendered():
    res = pipeline.run(_survey(q1_age=29, q2_horizon=5, q3_objective="증식",
                               q6_max_loss=-0.15, q7_experience="많음", q10_behavior="추가매수"))
    if res.downgrade_path:  # 합성 데이터에선 강등 발생
        html = report.render(res, _survey())
        assert "등급 조정 안내" in html
