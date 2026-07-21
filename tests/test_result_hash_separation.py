"""Step 0 DoD — 결정론 코어/자문 서술 해시 분리 (v2 §3.3·§7).

numeric_hash는 **서술(Narrative)을 포함하지 않는다** → 룰 템플릿을 LLM 서술로
바꿔도 재현성 해시가 흔들리지 않는다. 이것이 Advisory Plane(LLM 격리)의 물리적 전제.
"""
from __future__ import annotations

from apex import pipeline
from apex.pipeline import _canonical_hash, _narrative_hash
from apex.schemas import Narrative, SurveyAnswers


def _survey(**kw) -> SurveyAnswers:
    base = dict(
        q1_age=45, q2_horizon=3, q3_objective="균형", q4_capital=1, q5_monthly=0,
        q6_max_loss=-0.15, q7_experience="보통", q8_liquidity="보통",
        q9_fx="일부허용", q10_behavior="유지", input_snapshot_id="t",
    )
    base.update(kw)
    return SurveyAnswers(**base)


def test_narrative_not_in_numeric_payload():
    """재현성 해시 대상(numeric)에 서술 필드가 존재하지 않는다."""
    res = pipeline.run(_survey())
    payload = res.numeric.model_dump(mode="json")
    assert "explanation" not in payload
    assert "reelicitation" not in payload
    # 프로버넌스는 각인되어야 한다
    assert payload["schema_version"] and payload["env_hash"] and payload["data_version"]


def test_narrative_change_does_not_move_numeric_hash():
    """서술을 통째로 다른 문장으로 바꿔도 numeric_hash 불변, narrative_hash만 변한다."""
    res = pipeline.run(_survey())
    other = Narrative(explanation="LLM이 쓴 완전히 다른 자문 서술입니다.", reelicitation=None)
    # 같은 numeric → 같은 numeric_hash (서술 무관)
    assert _canonical_hash(res.numeric) == res.numeric_hash
    # 서술이 바뀌면 narrative_hash는 달라진다(감사용, numeric_hash엔 무영향)
    assert _narrative_hash(other) != res.narrative_hash
    assert res.numeric_hash != res.narrative_hash


def test_result_hash_alias_is_numeric_hash():
    """하위호환 별칭 result_hash == numeric_hash (기존 소비자 무해)."""
    res = pipeline.run(_survey())
    assert res.result_hash == res.numeric_hash
    assert len(res.numeric_hash) == 64  # sha256
