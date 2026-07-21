"""Step 0 DoD — Run Ledger 해시체인 + apex replay 재현 (v2 §3.6).

원장은 append-only 해시체인(변조 탐지). replay는 원장에서 입력·버전을 복원해
재실행하고 numeric_hash를 대조 → '재현성'이 주장이 아니라 실행이 된다.
"""
from __future__ import annotations

import json

from apex import pipeline, store
from apex.schemas import SurveyAnswers


def _survey(**kw) -> SurveyAnswers:
    base = dict(
        q1_age=45, q2_horizon=3, q3_objective="균형", q4_capital=1, q5_monthly=0,
        q6_max_loss=-0.15, q7_experience="보통", q8_liquidity="보통",
        q9_fx="일부허용", q10_behavior="유지", input_snapshot_id="t",
    )
    base.update(kw)
    return SurveyAnswers(**base)


def _append(res, ans, path):
    return store.append_run(res, ans, "synthetic", "KRW", "2026-07-17T00:00:00+00:00", path=path)


def test_chain_links_and_verifies(tmp_path):
    """연속 봉인 → prev_hash 링크 형성 + verify_chain True."""
    path = tmp_path / "runs.jsonl"
    a1, a2 = _survey(q6_max_loss=-0.15), _survey(q6_max_loss=-0.05, q3_objective="보전", q1_age=62)
    r1, r2 = pipeline.run(a1), pipeline.run(a2)
    rec1 = _append(r1, a1, path)
    rec2 = _append(r2, a2, path)

    assert rec1.prev_hash == "0" * 64  # genesis
    assert rec2.prev_hash == rec1.record_hash  # 체인 링크
    assert store.verify_chain(path)
    assert len(store.read_all(path)) == 2


def test_tamper_breaks_chain(tmp_path):
    """레코드 필드를 변조하면 verify_chain이 거짓을 반환한다(WORM 탐지)."""
    path = tmp_path / "runs.jsonl"
    a = _survey()
    _append(pipeline.run(a), a, path)
    _append(pipeline.run(_survey(q1_age=30)), _survey(q1_age=30), path)

    lines = path.read_text(encoding="utf-8").splitlines()
    rec0 = json.loads(lines[0])
    rec0["final_profile"] = "공격형"  # 사후 변조(record_hash는 그대로)
    lines[0] = json.dumps(rec0, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert not store.verify_chain(path)


def test_replay_reproduces_numeric_hash(tmp_path):
    """원장에서 입력 복원 → 재실행 → numeric_hash 동일(replay 왕복)."""
    path = tmp_path / "runs.jsonl"
    a = _survey(q6_max_loss=-0.20, q1_age=50)
    r = pipeline.run(a)
    rec = _append(r, a, path)

    # replay: 저장된 answers로 재구성·재실행
    replay_ans = SurveyAnswers(**rec.answers)
    replayed = pipeline.run(replay_ans, currency=rec.display_currency, source=rec.source)
    assert replayed.numeric_hash == rec.numeric_hash


def test_find_by_run_id_and_hash_prefix(tmp_path):
    path = tmp_path / "runs.jsonl"
    a = _survey()
    rec = _append(pipeline.run(a), a, path)
    assert store.find(rec.run_id, path).numeric_hash == rec.numeric_hash
    assert store.find(rec.numeric_hash[:8], path).run_id == rec.run_id
    assert store.find("nonexistent-id", path) is None
