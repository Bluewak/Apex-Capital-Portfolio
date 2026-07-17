"""Advisory Plane (v2 §3.4) — 서술(Narrator) 격리 계층. **LLM은 여기에만.**

기본 = 룰 템플릿(RuleNarrator, 결정론). LLM Narrator(QwenNarrator, 로컬 Ollama)는
**계약 불변 교체** — SPI 뒤에 꽂고 게이트·캐시·폴백이 안전망(§3.4, 리서치 결론: 이 작업엔
로컬 소형 모델 충분·프라이버시 우위, 재현성은 캐시로).
- 자문 게이트(발행 전): ① 수치충실도(서술의 숫자 ⊆ FactLedger) ② 금칙어(단정·보장·개인지시)
  ③ 면책·프레이밍 존재 ④ **한국어 조사 받침 정합**(작은 모델의 대표 오류 결정론 차단).
  하나라도 실패 → 룰 템플릿 무손실 폴백. Narrator 예외(모델 미실행 등)도 폴백.
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
MODEL_ID = "rule-template"  # 기본 model_id. Narrator가 model_id 속성으로 재정의.

# 금칙어: 단정 예측·수익 보장·원금 보장·개인 지시형(규제 경계, 자문 게이트)
_FORBIDDEN = ("보장", "확실히", "무조건", "반드시 오", "원금보장", "손실 없")
_NUM = re.compile(r"\d+%")
_CACHE: dict[str, str] = {}

# 한국어 조사 받침 정합. **을/를·과/와만** 검사 — 은/는·이/가는 동사 관형형·서술격
# 어미(맞는·있는·하는·이다·가다)와 충돌해 오탐이 크다. 을/를·과/와는 조사로 거의 확정.
_JOSA_BATCHIM = {"을", "과"}  # 받침 있는 음절 뒤 형태
_JOSA_VOWEL = {"를", "와"}  # 받침 없는 음절 뒤 형태
_JOSA_BOUNDARY = set(" .,!?\n·)")


def _has_batchim(syllable: str) -> bool | None:
    """한글 음절의 받침(종성) 유무. 한글 아니면 None."""
    code = ord(syllable)
    if 0xAC00 <= code <= 0xD7A3:
        return (code - 0xAC00) % 28 != 0
    return None


def josa_ok(text: str) -> bool:
    """조사 받침 정합 검증(을/를·과/와). (한글 음절 + 조사 + 경계) 위치만 판정 → 오탐 최소화.

    받침 있는 음절 뒤엔 을/과, 없는 음절 뒤엔 를/와. 명백한 위반만 False. 은/는·이/가는
    동사 어미 충돌로 제외(맞는·있는을 오탐하지 않게).
    """
    for i, ch in enumerate(text):
        if ch not in _JOSA_BATCHIM and ch not in _JOSA_VOWEL:
            continue
        if i == 0:
            continue
        b = _has_batchim(text[i - 1])
        if b is None:
            continue  # 앞이 한글 음절 아님 → 조사로 보지 않음
        nxt = text[i + 1] if i + 1 < len(text) else " "
        if nxt not in _JOSA_BOUNDARY:
            continue  # 조사 경계 아님(단어 일부)
        if b and ch in _JOSA_VOWEL:
            return False  # 받침 있는데 모음형
        if (not b) and ch in _JOSA_BATCHIM:
            return False  # 받침 없는데 받침형
    return True


class RuleNarrator:
    """기본 Narrator = 룰 템플릿(결정론). FactLedger 사실만 슬롯에 채운다."""

    DETERMINISM_REQUIRED = False
    model_id = "rule-template"

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


_SYSTEM_PROMPT = (
    "너는 한국어 금융 분석 리포트의 서술 도우미다. 제공된 '사실'만 사용해 1~2문장으로 "
    "간결하고 정중하게 설명하라. 사실에 없는 숫자, 단정적 예측, 수익 보장, 개인 지시형 "
    "표현은 절대 쓰지 마라. 반드시 '교육·분석용 정보이며 투자권유가 아닙니다.'로 끝맺어라."
)


def _build_prompt(ledger: FactLedger) -> str:
    facts = "\n".join(f"- {k}: {v}" for k, v in ledger.facts.items())
    return f"성향: {ledger.profile_label}\n결정: {ledger.decision}\n사실:\n{facts}\n\n위 사실만으로 서술:"


class QwenNarrator:
    """Ollama(로컬 Qwen2.5 등) Narrator 어댑터(G). DETERMINISM_REQUIRED=False.

    OpenAI 호환 엔드포인트(기본 localhost:11434)를 stdlib urllib로 호출(의존성 0).
    Ollama 미실행/실패 시 예외 → narrate가 룰 폴백. 게이트+캐시가 안전망이라 작은
    로컬 모델로 충분(§3.4). LLM은 배분·판정이 아니라 서술 슬롯 채우기만.
    """

    DETERMINISM_REQUIRED = False

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        base_url: str = "http://localhost:11434/v1",
        timeout: float = 30.0,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.model_id = f"ollama:{model}"

    def narrate(self, ledger: FactLedger) -> str:
        import urllib.request

        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(ledger)},
            ],
            "temperature": 0,
            "stream": False,
        }).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/chat/completions", data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read())
        return str(data["choices"][0]["message"]["content"]).strip()


def advisory_gate(text: str, ledger: FactLedger) -> bool:
    """발행 전 게이트. 실패 → 룰 폴백. (수치충실도·금칙어·면책존재·조사정합)"""
    if not set(_NUM.findall(text)) <= set(ledger.numbers):
        return False  # 원장에 없는 숫자 창작
    if any(bad in text for bad in _FORBIDDEN):
        return False  # 단정·보장·개인지시
    if "교육" not in text and "권유가 아" not in text:
        return False  # 면책·프레이밍 부재
    if not josa_ok(text):
        return False  # 한국어 조사 받침 불일치(작은 모델 대표 오류)
    return True


def _ledger_hash(ledger: FactLedger) -> str:
    payload = json.dumps(ledger.model_dump(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def narrate(ledger: FactLedger, narrator: object | None = None) -> str:
    """FactLedger → 서술. 게이트 통과분만 발행, 실패/예외 시 룰 폴백. 캐시 결정론."""
    nrt = narrator or RuleNarrator()
    model_id = getattr(nrt, "model_id", MODEL_ID)
    key = f"{_ledger_hash(ledger)}:{PROMPT_VERSION}:{model_id}"
    if key in _CACHE:
        return _CACHE[key]
    try:
        text = nrt.narrate(ledger)
    except Exception:  # noqa: BLE001 — Narrator 실패(모델 미실행 등)는 룰 폴백(무손실)
        text = RuleNarrator().narrate(ledger)
    if not advisory_gate(text, ledger):
        text = RuleNarrator().narrate(ledger)  # 룰 템플릿은 게이트 통과 보장
    _CACHE[key] = text
    return text
