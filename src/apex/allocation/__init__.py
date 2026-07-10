"""Allocation Engine — 성향 → 고정비중 모델포트폴리오 5종 (02·03·07 §3, R5).

profile → Allocation. 비중은 07 §3 밴드·집중도(단일ETF≤30%) 준수 예시(M5 실측 튜닝 전).
초안정형(R5) = near-cash(SHY 중심).
"""
from __future__ import annotations

from datetime import date

from apex.schemas import Allocation
from apex.schemas.enums import Profile

# 성향별 고정비중(합=1.0). 08 §10·07 §3 예시.
MODEL_PORTFOLIOS: dict[Profile, dict[str, float]] = {
    Profile.ULTRA_CONSERVATIVE: {  # near-cash: 주식 8 / 채권 19 / 금 8 / 현금 65
        "SHY": 0.65, "IEF": 0.12, "AGG": 0.07, "SPY": 0.08, "GLD": 0.08,
    },
    Profile.CONSERVATIVE: {  # 주식 30 / 채권 55 / 금 10 / 현금 5
        "SPY": 0.15, "QQQ": 0.08, "EFA": 0.05, "EEM": 0.02,
        "IEF": 0.25, "AGG": 0.20, "TLT": 0.10, "GLD": 0.10, "SHY": 0.05,
    },
    Profile.NEUTRAL: {  # 주식 55 / 채권 30 / 금 8 / 현금 7
        "SPY": 0.25, "QQQ": 0.12, "EFA": 0.12, "EEM": 0.06,
        "IEF": 0.18, "AGG": 0.12, "GLD": 0.08, "SHY": 0.07,
    },
    Profile.GROWTH: {  # 주식 75 / 채권 15 / 금 5 / 현금 5
        "SPY": 0.30, "QQQ": 0.22, "EFA": 0.15, "EEM": 0.08,
        "IEF": 0.10, "AGG": 0.05, "GLD": 0.05, "SHY": 0.05,
    },
    Profile.AGGRESSIVE: {  # 주식 90 / 채권 3 / 금 4 / 현금 3
        "SPY": 0.30, "QQQ": 0.28, "EFA": 0.20, "EEM": 0.12,
        "IEF": 0.03, "GLD": 0.04, "SHY": 0.03,
    },
}


def build(profile: Profile, min_cash: float = 0.0, as_of: date | None = None) -> Allocation:
    """성향 → Allocation(티커·비중). 몰개성 유형 예시(R5, 개인화 아님).

    ``min_cash``: 현금성(SHY) 최소 비중(03 §4 Q8='높음' → ≥10%). 부족 시 SHY를
    끌어올리고 나머지를 비례 축소(합=1 유지). 하드 가드레일 실반영.
    """
    w = dict(MODEL_PORTFOLIOS[profile])
    w.setdefault("SHY", 0.0)
    if w["SHY"] < min_cash - 1e-9:
        others_sum = sum(v for k, v in w.items() if k != "SHY")
        scale = (1.0 - min_cash) / others_sum if others_sum > 0 else 0.0
        w = {k: (min_cash if k == "SHY" else v * scale) for k, v in w.items()}
    return Allocation(
        profile=profile.value,
        model_portfolio=profile.model_portfolio,
        weights=w,
        as_of=as_of or date(2026, 7, 7),
    )
