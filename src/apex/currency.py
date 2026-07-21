"""통화 토글 (D4). 계산은 항상 현지통화(USD), 표시 단계에서 KRW/USD 선택.

KRW 표시 = 현지통화 수익률에 해당 구간 USD/KRW 환율 적용(환효과 포함).
구현은 M6(리포트)에서. 현재는 인터페이스만 고정.
"""
from __future__ import annotations

from typing import Literal

Currency = Literal["KRW", "USD"]


def normalize(currency: str) -> Currency:
    """입력 통화 문자열을 표준 코드로 정규화."""
    c = currency.strip().upper()
    if c not in ("KRW", "USD"):
        raise ValueError(f"지원하지 않는 통화: {currency} (KRW|USD)")
    return c  # type: ignore[return-value]
