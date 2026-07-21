"""신호 캘리브레이션 테이블 (v3-B Step 3 · docs/13 §4.1) — 이산 신호 → (Q, Ω).

**패널 5인 만장 수정**: LLM이 연속 숫자(Q·Ω)를 창작하면 v2 환각 게이트(Q∈FactLedger)가
무력화된다. → LLM은 **이산 분류 신호만** 출력(강한음..강한양 + 인용), 이 **핀된 결정론
테이블**이 signal→(Q 뷰크기, Ω 불확실성)으로 변환. 숫자가 LLM 밖 → fidelity 게이트 복원.

퀀트 코어 소유·`DETERMINISM_REQUIRED=True`(LLM 아님). Ω는 절대 LLM 자유형 금지 —
약한 신호일수록 Ω 큼(과틸트 방지), Ω 하한은 불변식(과확신 차단). Q는 표에 상한.
"""
from __future__ import annotations

import hashlib
import json

DETERMINISM_REQUIRED = True
CALIB_VERSION = "signal-calib-v1"

# 순서형 이산 신호(LLM 허용 출력 어휘). 이 밖의 값은 거부.
SIGNAL_CLASSES: tuple[str, ...] = ("strong_neg", "neg", "neutral", "pos", "strong_pos")

# signal → (Q: 연 초과수익 뷰, Ω: 뷰 분산=불확실성). 결정론·조정 가능한 단일 소스.
# Q 상한 ±6%(과틸트 방지), Ω 하한 floor(과확신 차단). 약신호 Ω↑.
_TABLE: dict[str, tuple[float, float]] = {
    "strong_pos": (0.06, 0.0100),
    "pos": (0.03, 0.0080),
    "neutral": (0.00, 0.0060),
    "neg": (-0.03, 0.0080),
    "strong_neg": (-0.06, 0.0100),
}
OMEGA_FLOOR = 0.0050  # 불확실성 하한(불변식) — 과확신 뷰 차단


def view_qomega(signal_class: str) -> tuple[float, float]:
    """이산 신호 → (Q, Ω). 미지 신호는 하드 실패(LLM 어휘 강제)."""
    if signal_class not in _TABLE:
        raise ValueError(f"미지 신호 '{signal_class}' — 허용: {SIGNAL_CLASSES}")
    q, omega = _TABLE[signal_class]
    return q, max(omega, OMEGA_FLOOR)  # Ω 하한 불변식


def is_valid_signal(signal_class: str) -> bool:
    return signal_class in _TABLE


def calib_version() -> str:
    """캘리브레이션 리니지 해시(테이블·floor·버전)."""
    payload = json.dumps({"table": _TABLE, "floor": OMEGA_FLOOR, "v": CALIB_VERSION},
                         sort_keys=True)
    return CALIB_VERSION + "-" + hashlib.sha256(payload.encode()).hexdigest()[:12]
