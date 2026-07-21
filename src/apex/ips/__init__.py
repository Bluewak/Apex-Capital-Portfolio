"""IPS Agent — InvestorProfile + Allocation → IPSDocument (04, M6).

04 §2 문장 템플릿 + R4/R5 정직 고지: 유형 귀속형 프레이밍·환/통화 고지·응답 반영·
disclosed 스트레스 안심·트레이드오프. 개별 지시형 문구 금지(규제, 08 §4-5).
"""
from __future__ import annotations

from apex.schemas import Allocation, InvestorProfile, IPSDocument, RiskReport, SurveyAnswers
from apex.schemas.enums import Profile

# 07 §3 성향별 자산군 밴드(허용 범위)
_BANDS: dict[Profile, dict[str, str]] = {
    Profile.ULTRA_CONSERVATIVE: {
        "주식": "0–10%", "채권": "15–30%", "금": "0–10%", "현금성": "55–75%",
    },
    Profile.CONSERVATIVE: {"주식": "20–35%", "채권": "50–70%", "금": "5–15%", "현금성": "≥5%"},
    Profile.NEUTRAL: {"주식": "45–60%", "채권": "30–45%", "금": "5–12%", "현금성": "≥3%"},
    Profile.GROWTH: {"주식": "65–80%", "채권": "12–25%", "금": "3–10%", "현금성": "≥3%"},
    Profile.AGGRESSIVE: {"주식": "85–95%", "채권": "3–10%", "금": "0–10%", "현금성": "≥3%"},
}
_TARGET: dict[Profile, str] = {
    Profile.ULTRA_CONSERVATIVE: "연 2~4% (원금 보전 우선, 인플레 미달 가능)",
    Profile.CONSERVATIVE: "연 4~6%",
    Profile.NEUTRAL: "연 6~8%",
    Profile.GROWTH: "연 7~10%",
    Profile.AGGRESSIVE: "연 9~12%",
}


def _saa_line(weights: dict[str, float]) -> str:
    top = sorted(weights.items(), key=lambda kv: -kv[1])
    return " / ".join(f"{t} {w:.0%}" for t, w in top)


def render(
    profile: InvestorProfile,
    alloc: Allocation,
    answers: SurveyAnswers,
    risk: RiskReport,
    expected_cagr: float,
) -> IPSDocument:
    """유형 귀속형 IPS 렌더(교육·분석용, 개별 자문 아님)."""
    p = profile.profile
    usd = risk.currency_exposure.get("USD", 1.0)
    stress_line = " · ".join(f"{s.scenario} {s.loss:.0%}" for s in risk.stress) or "산출 예정"
    fx = answers.q9_fx
    fx_reflection = (
        "원화 벤치 비교 강조 + 헤지형 v2 로드맵(현재 미지원)" if fx == "회피" else "통화노출 % 고지"
    )
    reflected = f"손실 감내 {answers.q6_max_loss:.0%} → {p.value} · 환노출 '{fx}'"

    saa = _saa_line(alloc.weights)
    text = (
        f"본 문서는 '{p.value}' **유형**에 대응하는 예시 배분이며 개별 투자권유·자문이 "
        f"아니다(교육·분석용). 해당 유형은 {profile.horizon_years}년 이상을 전제로 "
        f"{saa} 기준 배분을 사용한다.\n\n"
        f"평시 기준 예상 연손실이 {profile.max_annual_loss:.0%}(성향 상한과 Q6 감내 중 보수값)를 "
        f"초과하는 조합은 예시에서 제외한다. 목표 참고수익 {_TARGET[p]}, 기대 CAGR "
        f"{expected_cagr:.1%}(과거 실측 근사, 미래 보장 아님).\n\n"
        f"[환·통화] 해외자산 비중이 높아 USD 노출 약 {usd:.0%}이며 원화강세 시 손실이 확대될 수 "
        f"있다. MVP는 환헤지를 제공하지 않는다(헤지형 슬롯 v2). 환노출 선호({fx}) 응답은 "
        f"{fx_reflection}로 반영했다.\n\n"
        f"[응답 반영] {reflected}가 위 배분·고지에 반영되었다.\n\n"
        f"[극단 시장 참고 공시] 아래 손실은 20년에 몇 번 오는 극단 구간의 실측 참고치이며(평시와 "
        f"다름), 역사적으로 회복해 왔다(미래 수익 보장 아님): {stress_line}.\n\n"
        f"[시장 혼란기 행동] 밴드 이탈 전 임의 매도 금지. "
        f"손실 시 행동 응답('{answers.q10_behavior}')을 하락기 사전서약으로 삼는다."
    )

    return IPSDocument(
        objective={"보전": "자산 보전", "균형": "균형 성장", "증식": "장기 자산증식"}[
            answers.q3_objective
        ],
        horizon_years=profile.horizon_years,
        target_return_note=_TARGET[p],
        max_loss=profile.max_annual_loss,
        asset_bands=_BANDS[p],
        saa=dict(alloc.weights),
        hedge_policy="MVP 환헤지 미지원 (헤지형 슬롯 v2)",
        benchmark="S&P500 TR / 60·40 / KOSPI200 대비 위험조정성과",
        rendered_text=text,
    )
