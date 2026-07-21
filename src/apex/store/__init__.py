"""Run Ledger — append-only 해시체인 원장 (v2 §3.6, 06 §5).

매 advice 런을 입력·데이터·모델·환경 버전과 함께 봉인한다. 각 레코드가 직전
레코드 해시(``prev_hash``)를 포함 → 변조 탐지(WORM 지향). MVP=JSONL 온디스크(후 SQLite/DB).

주의: 원장 쓰기는 **서빙 계층(cli/service)에서만** 한다. ``pipeline.run``은 순수(디스크
무접촉) — property 테스트가 150회 돌아도 원장을 오염시키지 않는다.
``apex replay --run-id``가 원장에서 입력·버전을 복원해 재실행 → numeric_hash 대조.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, Field

LEDGER_DIR = Path("artifacts/ledger")
LEDGER = LEDGER_DIR / "runs.jsonl"
_GENESIS = "0" * 64


class RunRecord(BaseModel):
    """원장 레코드 — 재현 입력 + 프로버넌스 + 해시체인 링크."""

    run_id: str  # numeric_hash 앞 16자(멱등키)
    created_at: str  # 서빙 계층 주입(ISO8601)
    source: str  # 'synthetic' | 'real'
    display_currency: str
    answers: dict  # 재현 입력 스냅샷(SurveyAnswers 직렬화)
    decision: str
    final_profile: str
    downgrade_path: list[str] = Field(default_factory=list)
    schema_version: str
    data_version: str
    env_hash: str
    numeric_hash: str
    narrative_hash: str
    prev_hash: str
    record_hash: str = ""


def _record_hash(rec: RunRecord) -> str:
    payload = rec.model_dump(exclude={"record_hash"})
    canon = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _last_hash(path: Path = LEDGER) -> str:
    recs = read_all(path)
    return recs[-1].record_hash if recs else _GENESIS


def append(fields: dict, path: Path = LEDGER) -> RunRecord:
    """레코드를 원장 끝에 봉인(직전 해시 체인). 반환: 봉인된 RunRecord."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = RunRecord(prev_hash=_last_hash(path), **fields)
    rec.record_hash = _record_hash(rec)
    with path.open("a", encoding="utf-8") as f:
        f.write(rec.model_dump_json() + "\n")
    return rec


def append_run(
    result, answers, source: str, display_currency: str, created_at: str, path: Path = LEDGER
) -> RunRecord:
    """PipelineResult → 원장 레코드 봉인(서빙 계층 헬퍼)."""
    return append(
        {
            "run_id": result.numeric_hash[:16],
            "created_at": created_at,
            "source": source,
            "display_currency": display_currency,
            "answers": answers.model_dump(mode="json"),
            "decision": result.decision,
            "final_profile": result.final_profile,
            "downgrade_path": list(result.downgrade_path),
            "schema_version": result.numeric.schema_version,
            "data_version": result.data_version,
            "env_hash": result.numeric.env_hash,
            "numeric_hash": result.numeric_hash,
            "narrative_hash": result.narrative_hash,
        },
        path=path,
    )


def read_all(path: Path = LEDGER) -> list[RunRecord]:
    if not path.exists():
        return []
    out: list[RunRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(RunRecord(**json.loads(line)))
    return out


def find(run_id: str, path: Path = LEDGER) -> RunRecord | None:
    """run_id 또는 numeric_hash 접두로 최신 매칭 레코드 조회."""
    for rec in reversed(read_all(path)):
        if rec.run_id == run_id or rec.numeric_hash.startswith(run_id):
            return rec
    return None


def verify_chain(path: Path = LEDGER) -> bool:
    """해시체인 무결성 검증(각 레코드가 직전 해시를 정확히 링크 + 자기해시 일치)."""
    prev = _GENESIS
    for rec in read_all(path):
        if rec.prev_hash != prev or rec.record_hash != _record_hash(rec):
            return False
        prev = rec.record_hash
    return True
