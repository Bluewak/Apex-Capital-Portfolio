"""공유 열거/리터럴 (03 설문·성향)."""
from __future__ import annotations

from enum import StrEnum
from typing import Literal

# 설문 응답 값 도메인 (03 §1)
Objective = Literal["보전", "균형", "증식"]
Experience = Literal["없음", "보통", "많음"]
Liquidity = Literal["낮음", "보통", "높음"]
FxPreference = Literal["회피", "일부허용", "허용"]
Behavior = Literal["매도", "유지", "추가매수"]


class Profile(StrEnum):
    """위험성향 등급 (03 §3)."""

    CONSERVATIVE = "안정형"
    NEUTRAL = "중립형"
    GROWTH = "성장형"
    AGGRESSIVE = "공격형"

    @property
    def model_portfolio(self) -> str:
        """성향 → 모델포트폴리오 코드 (03 §3)."""
        return {
            "안정형": "MP-Conservative",
            "중립형": "MP-Neutral",
            "성장형": "MP-Growth",
            "공격형": "MP-Aggressive",
        }[self.value]
