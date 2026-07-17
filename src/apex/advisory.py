"""Advisory Plane (v2 §3.4) — 서술(Narrator) 격리 계층. **LLM은 여기에만.**

현재 기본 = 룰 템플릿(RuleNarrator, 결정론). LLM Narrator는 계약 불변 교체(미래).
- 자문 게이트(발행 전): ① 수치충실도(서술의 숫자 ⊆ FactLedger) ② 금칙어(단정·보장·개인지시)
  ③ 면책·프레이밍 존재. 하나라도 실패 → 룰 템플릿 무손실 폴백.
- 캐시 결정론: (fact_ledger_hash × prompt_version × model_id) → 동일 입력=동일 서술.
- narrative_hash는 감사용, numeric_result_hash에 **미포함**(§7).

경계(§5): 이 모듈만 LLM(anthropic)을 import할 수 있고, 결정론 코어는 이 모듈을
import하지 않는다(serving 오케스트레이터만 bridge). CI가 강제(test_determinism_boundary).
"""
from __future__ import annotations

import hashlib
import json
import re

from apex.factledger import FactLedger

PROMPT_VERSION = "rule-v1"
MODEL_ID = "rule-template"  # LLM 교체 시 실제 모델 id로. 캐시 키 구성요소.

# 금칙어: 단정 예측·수익 보장·원금 보장·개인 지시형(규제 경계, 자문 게이트)
_FORBIDDEN = ("보장", "확실히", "무조건", "반드시 오", "원금보장", "손실 없")
_NUM = re.compile(r"\d+%")
_CACHE: dict[str, str] = {}


class RuleNarrator:
    """기본 Narrator = 룰 템플릿(결정론). FactLedger 사실만 슬롯에 채운다."""

    DETERMINISM_REQUIRED = False

    def narrate(self, ledger: FactLedger) -> str:
        if ledger.decision != "ok":
            return (
                "감내 한도에 맞는 예시 배분이 없어 배정을 보류합니다. 원금보전형(예금·MMF)을 "
                "참고하시고 감내 한도를 다시 확인해 주세요. 교육·분석용 정보이며 투자권유가 아닙니다."
            )
        f = ledger.facts
        return (
            f"{ledger.profile_label} 유형의 예시 배분입니다. 기대 수익 약 {f.get('기대수익', '—')}, "
            f"평시 변동성 약 {f.get('평시변동성', '—')}, forward 기대손실 약 "
            f"{f.get('forward기대손실', '—')} 수준입니다. 교육·분석용 정보이며 개별 투자권유가 아닙니다."
        )


def advisory_gate(text: str, ledger: FactLedger) -> bool:
    """발행 전 게이트. 실패 → 룰 폴백. (수치충실도·금칙어·면책존재)"""
    if not set(_NUM.findall(text)) <= set(ledger.numbers):
        return False  # 원장에 없는 숫자 창작
    if any(bad in text for bad in _FORBIDDEN):
        return False  # 단정·보장·개인지시
    if "교육" not in text and "권유가 아" not in text:
        return False  # 면책·프레이밍 부재
    return True


def _ledger_hash(ledger: FactLedger) -> str:
    payload = json.dumps(ledger.model_dump(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def narrate(ledger: FactLedger, narrator: object | None = None) -> str:
    """FactLedger → 서술. 게이트 통과분만 발행, 실패 시 룰 폴백. 캐시 결정론."""
    nrt = narrator or RuleNarrator()
    key = f"{_ledger_hash(ledger)}:{PROMPT_VERSION}:{MODEL_ID}"
    if key in _CACHE:
        return _CACHE[key]
    text = nrt.narrate(ledger)
    if not advisory_gate(text, ledger):
        text = RuleNarrator().narrate(ledger)  # 룰 템플릿은 게이트 통과 보장(무손실 폴백)
    _CACHE[key] = text
    return text
