"""Investor Agent — 설문 → 위험점수 → 성향 + 하드 가드레일 (03 §2·§4).

SurveyAnswers → InvestorProfile. 룰 기반 가중합(03 §2) + Q6 캡(03 §4 R5).
"""
from __future__ import annotations

from apex.schemas import Constraints, InvestorProfile, SurveyAnswers
from apex.schemas.enums import Profile

# 03 §2 가중치
_WEIGHTS = {"q6": 0.30, "q2": 0.20, "q10": 0.15, "q3": 0.15, "q7": 0.10, "q1": 0.10}


def _q6_points(q6: float) -> int:
    """손실 감내 → 0~4점(음수일수록 공격적, 03 §1 부호 규약)."""
    if q6 >= -0.05:
        return 0
    if q6 >= -0.10:
        return 1
    if q6 >= -0.15:
        return 2
    if q6 >= -0.25:
        return 3
    return 4


def _score(a: SurveyAnswers) -> int:
    q2 = a.q2_horizon - 1  # 1~5 → 0~4
    q10 = {"매도": 0, "유지": 2, "추가매수": 4}[a.q10_behavior]
    q3 = {"보전": 0, "균형": 2, "증식": 4}[a.q3_objective]
    q7 = {"없음": 0, "보통": 2, "많음": 4}[a.q7_experience]
    q1 = 0  # 나이 역가중(젊을수록 리스크↑)
    for thr, p in ((30, 4), (40, 3), (50, 2), (60, 1)):
        if a.q1_age <= thr:
            q1 = p
            break
    pts = (
        _WEIGHTS["q6"] * _q6_points(a.q6_max_loss)
        + _WEIGHTS["q2"] * q2
        + _WEIGHTS["q10"] * q10
        + _WEIGHTS["q3"] * q3
        + _WEIGHTS["q7"] * q7
        + _WEIGHTS["q1"] * q1
    )
    return round(pts * 25)  # 0~4 → 0~100


def _band(score: int) -> Profile:
    """위험점수 → 성향 (03 §3, 5구간)."""
    if score <= 12:
        return Profile.ULTRA_CONSERVATIVE
    if score <= 25:
        return Profile.CONSERVATIVE
    if score <= 50:
        return Profile.NEUTRAL
    if score <= 75:
        return Profile.GROWTH
    return Profile.AGGRESSIVE


def _q6_cap(q6: float) -> Profile | None:
    """Q6 하드 가드레일 캡 (03 §4 R5). 음수일수록 공격적."""
    if q6 >= -0.05:
        return Profile.ULTRA_CONSERVATIVE  # 최보수 → 초안정형
    if q6 >= -0.10:
        return Profile.NEUTRAL  # 보전 성향 → 중립형 캡
    return None


def reelicitation_note(answers: SurveyAnswers) -> str | None:
    """모순 주문(무손실 지향 ∧ 물가+α 증식) 감지 → 재보정 문구 (R5, 08 §10·03 §4).

    Q6=−5%(사실상 무손실)인데 목적이 증식/균형이면 '무손실 + 물가+α'는 동시 불가.
    hold/발행 이전에 결과 결합형 재질문 + 인플레이션을 '손실'로 재프레이밍한다.
    교육(트레이드오프)이지 개인 지시 아님.
    """
    if answers.q6_max_loss >= -0.05 and answers.q3_objective in {"증식", "균형"}:
        return (
            "'거의 무손실(−5%)'과 '물가+α'는 동시에 갖기 어렵습니다. 예금은 명목 손실이 "
            "거의 없지만 10년 물가를 반영하면 실질 구매력이 줄어듭니다(그것도 손실입니다). "
            "물가+α를 원하시면 6년에 한 번쯤 −10% 안팎의 변동을 받아들여야 합니다. "
            "어느 쪽이 더 중요하십니까? — 무손실 우선이면 예금·초안정형, 물가+α 우선이면 "
            "감내 한도를 다시 확인해 주세요(교육 정보, 개인 지시 아님)."
        )
    return None


def score(answers: SurveyAnswers) -> InvestorProfile:
    """설문 → InvestorProfile. 점수 산출 후 Q6 하드 캡을 적용(더 보수적으로만)."""
    rs = _score(answers)
    profile = _band(rs)
    cap = _q6_cap(answers.q6_max_loss)
    if cap is not None and cap.rank < profile.rank:
        profile = cap
    constraints = Constraints(
        min_cash=0.10 if answers.q8_liquidity == "높음" else 0.05,
        hedge_preferred=(answers.q9_fx == "회피"),
        cap_profile=cap,
    )
    return InvestorProfile(
        risk_score=rs,
        profile=profile,
        horizon_years={1: 2, 2: 4, 3: 6, 4: 8, 5: 12}[answers.q2_horizon],
        max_annual_loss=answers.q6_max_loss,
        liquidity_need=answers.q8_liquidity,
        fx_preference=answers.q9_fx,
        constraints=constraints,
    )
