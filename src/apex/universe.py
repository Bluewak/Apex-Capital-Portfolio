"""자산 유니버스 단일 소스 (02 §1·07 §1). 티커 → 자산군·라벨·표시색.

data(합성 파라미터)·allocation(모델포트)·risk(집중도)·report(색)·snapshot(수집)이
공유하는 정본. 흩어진 티커→자산군 매핑을 여기로 단일화(DRY).
"""
from __future__ import annotations

# 코어 9슬롯 (07 §1 MVP). 순서 = 수집·정렬 기준.
CORE_SLOTS: tuple[str, ...] = ("SPY", "QQQ", "EFA", "EEM", "IEF", "TLT", "AGG", "SHY", "GLD")
BENCHMARKS: tuple[str, ...] = ("069500.KS",)  # KOSPI200 KRW TR 프록시(KODEX200)

# 티커 → 대분류 코드 (집중도·자산군 표기)
ASSET_CLASS: dict[str, str] = {
    "SPY": "EQ", "QQQ": "EQ", "EFA": "EQ", "EEM": "EQ",
    "IEF": "BOND", "TLT": "BOND", "AGG": "BOND",
    "SHY": "CASH", "GLD": "GOLD",
}
CLASS_LABEL: dict[str, str] = {"EQ": "주식", "BOND": "채권", "CASH": "현금성", "GOLD": "금"}
CLASS_COLOR: dict[str, str] = {
    "EQ": "#1f6f78", "BOND": "#5a8f7a", "GOLD": "#b5892f", "CASH": "#7f8a99",
}
