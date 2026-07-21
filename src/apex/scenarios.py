"""실측 스트레스 구간 정의 + 구간 낙폭 (05 §2, R3 평시/스트레스 분리).

평시(normal) 판정에서 제외하고 disclosed로 고지하는 위기 3구간의 단일 소스.
loader·risk·gate가 공유한다(중복 정의 방지).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 실측 스트레스 구간 (05 §2). 평시 판정에서 제외(R3: 스트레스는 공시, 차단은 평시).
STRESS_WINDOWS: dict[str, tuple[str, str]] = {
    "2008": ("2007-10-01", "2009-03-31"),
    "2020": ("2020-02-19", "2020-03-23"),
    "2022": ("2022-01-01", "2022-10-31"),
}


def window_drawdown(returns: np.ndarray | pd.Series) -> float:
    """구간 내 최대낙폭(peak-to-trough), 음수. 스트레스 공시용."""
    arr = returns.to_numpy() if isinstance(returns, pd.Series) else np.asarray(returns, dtype=float)
    if arr.size == 0:
        return 0.0
    cum = np.cumprod(1.0 + arr)
    peak = np.maximum.accumulate(cum)
    return float((cum / peak - 1.0).min())


def normal_mask(index: pd.DatetimeIndex) -> np.ndarray:
    """위기 3구간을 제외한 평시 마스크(bool). index는 tz 유무 무관."""
    idx = index.tz_localize(None) if index.tz is not None else index
    mask = np.ones(len(idx), dtype=bool)
    for lo, hi in STRESS_WINDOWS.values():
        in_win = (idx >= pd.Timestamp(lo)) & (idx <= pd.Timestamp(hi))
        mask &= ~np.asarray(in_win)
    return mask
