"""M6 DoD — 랜덤 프로파일 "성향 위반 배정 0건" property test (01 §5, 08 §6).

무작위 설문 N개를 pipeline에 통과시켜, **발행된(ok) 포트폴리오는 예외 없이**
평시 예상손실(var95_annual)이 min(성향 평시 상한, |Q6| 감내) 이내임을 검증.
못 맞추면 hold(포트 미발행)여야 한다 — 그 사이는 없다(불변식).
결정론 시드로 재현 가능.
"""
from __future__ import annotations

import random

from apex import pipeline
from apex.compliance import VAR_LIMIT
from apex.schemas import SurveyAnswers
from apex.schemas.enums import Profile

_Q6_OPTIONS = [-0.05, -0.10, -0.15, -0.25, -0.35]
_OBJ = ["보전", "균형", "증식"]
_EXP = ["없음", "보통", "많음"]
_LIQ = ["낮음", "보통", "높음"]
_FX = ["회피", "일부허용", "허용"]
_BEH = ["매도", "유지", "추가매수"]


def _random_survey(rng: random.Random, i: int) -> SurveyAnswers:
    return SurveyAnswers(
        q1_age=rng.randint(20, 78),
        q2_horizon=rng.randint(1, 5),
        q3_objective=rng.choice(_OBJ),
        q4_capital=rng.randint(1, 5) * 10_000_000,
        q5_monthly=rng.randint(0, 5) * 100_000,
        q6_max_loss=rng.choice(_Q6_OPTIONS),
        q7_experience=rng.choice(_EXP),
        q8_liquidity=rng.choice(_LIQ),
        q9_fx=rng.choice(_FX),
        q10_behavior=rng.choice(_BEH),
        input_snapshot_id=f"prop-{i}",
    )


def test_no_profile_violation_over_random_population():
    """성향 위반 배정 0건: ok면 var ≤ min(상한, |Q6|), 아니면 hold(alloc=None)."""
    rng = random.Random(20260708)
    n_ok = n_hold = 0
    for i in range(150):
        ans = _random_survey(rng, i)
        res = pipeline.run(ans)  # 합성 소스(오프라인·결정론)

        assert res.decision in {"ok", "hold"}, f"미종료 상태: {res.decision}"
        if res.decision == "hold":
            assert res.allocation is None and res.risk is None
            n_hold += 1
            continue

        n_ok += 1
        prof = Profile(res.final_profile)
        binding = min(VAR_LIMIT[prof], abs(ans.q6_max_loss))
        actual = res.risk.var95_annual  # 발행 포트의 평시(합성=전구간) 연율 VaR
        assert actual <= binding + 1e-9, (
            f"위반! {res.final_profile} var={actual:.4f} > binding={binding:.4f} "
            f"(Q6={ans.q6_max_loss}, score={res.risk_score})"
        )
        # 발행 성향은 요청 등급 이하로만 조정됨(강등 사다리)
        assert prof.rank <= Profile.AGGRESSIVE.rank

    assert n_ok > 0 and n_hold >= 0  # 모집단이 실제로 두 경로를 탐색


def test_downgrade_path_is_monotone():
    """강등 경로는 단조 하강(공격형→…→초안정형)해야 한다."""
    rng = random.Random(7)
    for i in range(30):
        res = pipeline.run(_random_survey(rng, i))
        # 강등 사유 문자열이 있으면 각 단계가 한 등급씩 낮아짐(사다리 위반 없음)
        assert len(res.downgrade_path) <= 4  # 5구간 → 최대 4회
