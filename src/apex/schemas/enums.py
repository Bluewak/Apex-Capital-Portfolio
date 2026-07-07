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
    """위험성향 등급 (03 §3). 2026-07-05 R5: 초안정형 5구간화."""

    ULTRA_CONSERVATIVE = "초안정형"
    CONSERVATIVE = "안정형"
    NEUTRAL = "중립형"
    GROWTH = "성장형"
    AGGRESSIVE = "공격형"

    @property
    def model_portfolio(self) -> str:
        """성향 → 모델포트폴리오 코드 (03 §3)."""
        return {
            "초안정형": "MP-UltraConservative",
            "안정형": "MP-Conservative",
            "중립형": "MP-Neutral",
            "성장형": "MP-Growth",
            "공격형": "MP-Aggressive",
        }[self.value]

    @property
    def rank(self) -> int:
        """보수→공격 순위. 0=초안정형 … 4=공격형 (낮을수록 보수적)."""
        return _LADDER.index(self)

    def downgraded(self) -> Profile | None:
        """한 등급 강등 (08 §7 강등 사다리). 초안정형보다 아래는 없음 → None(hold)."""
        i = _LADDER.index(self)
        return _LADDER[i - 1] if i > 0 else None


# 강등 사다리(R5): 공격형 → 성장형 → 중립형 → 안정형 → 초안정형 → (hold)
_LADDER: tuple[Profile, ...] = (
    Profile.ULTRA_CONSERVATIVE,
    Profile.CONSERVATIVE,
    Profile.NEUTRAL,
    Profile.GROWTH,
    Profile.AGGRESSIVE,
)
