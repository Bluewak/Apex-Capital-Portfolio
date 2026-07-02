"""오케스트레이터 (06 §6). 단방향 파이프라인 + 컴플라이언스 재계산 루프.

M4~M6에서 각 컴포넌트를 연결해 구현한다. 현재는 계약(schemas)만 확정된 스캐폴딩 단계.
"""
from __future__ import annotations

from apex.schemas import SurveyAnswers


def run(answers: SurveyAnswers, currency: str = "KRW") -> None:
    """설문 → 리포트 E2E. (미구현: M4~M6)"""
    raise NotImplementedError("pipeline.run: M4~M6에서 구현 (docs/08-dev-plan.md §3·§7)")
