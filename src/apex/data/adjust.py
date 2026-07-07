"""로컬 결정론 총수익(TR) 조정 엔진 + 대사 오라클 (08 §3 M4.5).

yfinance 조정종가는 신규 배당마다 과거가 소급 변형되므로 저장·의존하지 않는다.
대신 raw(unadjusted Close + Dividends + Splits + Capital Gains)에서 총수익을
**결정론적으로 자체 계산**하고, 착수 1회 독립 레퍼런스(yfinance Adj Close)와
대사(reconcile)해 정확성을 검증한다("재현 가능하게 틀림" 방지, R3 데이터).

엔진은 순수함수(numpy) — 네트워크·전역상태 없음. 픽스처로 손검증 가능.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def local_tr_returns(
    close: np.ndarray,
    dividends: np.ndarray,
    splits: np.ndarray,
    capital_gains: np.ndarray | None = None,
    close_is_split_adjusted: bool = True,
) -> np.ndarray:
    """raw 시계열 → 일별 단순 총수익률 (길이 n-1). 배당·자본이득 재투자, 분할 반영.

    주식-누적 모델(shares model): 1주 시작. 분할일 주수 ×ratio, 분배금은 당일 종가에
    재투자(주수 증가). value_t = shares_t × close_t. r_t = value_t / value_{t-1} − 1.

    ``close_is_split_adjusted=True``(기본): 소스(yfinance auto_adjust=False)의 Close가
    **이미 분할조정**돼 있으므로 분할을 재적용하지 않는다(이중적용 시 분할일 유령수익).
    raw unadjusted Close를 직접 쓸 때만 False로.
    """
    close = np.asarray(close, dtype=float)
    div = np.asarray(dividends, dtype=float)
    n = len(close)
    capg = np.zeros(n) if capital_gains is None else np.asarray(capital_gains, dtype=float)
    if close_is_split_adjusted:
        sp = np.ones(n)
    else:
        sp = np.asarray(splits, dtype=float)
        sp = np.where(sp <= 0.0, 1.0, sp)  # 0(무분할) → 1.0

    shares = np.empty(n)
    value = np.empty(n)
    shares[0] = 1.0
    value[0] = close[0]
    for t in range(1, n):
        s = shares[t - 1] * sp[t]  # 분할 반영
        dist = div[t] + capg[t]  # 주당 분배금
        reinvest = s * (dist / close[t]) if close[t] > 0 else 0.0
        shares[t] = s + reinvest
        value[t] = shares[t] * close[t]
    return value[1:] / value[:-1] - 1.0


def returns_from_adjclose(adj_close: np.ndarray) -> np.ndarray:
    """레퍼런스: 조정종가 → 일별 수익률 (대사 오라클용, 길이 n-1)."""
    adj = np.asarray(adj_close, dtype=float)
    return adj[1:] / adj[:-1] - 1.0


@dataclass(frozen=True)
class ReconResult:
    """대사 결과. `passed` = 연율 편차가 허용오차 이내."""

    n: int
    ann_dev: float       # 연율 기하 편차(로컬 vs 레퍼런스)
    max_daily_abs: float  # 최대 일별 절대 편차
    tol_annual: float
    passed: bool


def reconcile(
    local_returns: np.ndarray,
    reference_returns: np.ndarray,
    tol_annual: float = 0.0020,  # 20bps/년
    ppy: int = 252,
) -> ReconResult:
    """로컬 TR ↔ 레퍼런스 수익률 대사. 연율 기하 편차 ≤ tol_annual 이면 통과."""
    n = min(len(local_returns), len(reference_returns))
    loc = np.asarray(local_returns[:n], dtype=float)
    ref = np.asarray(reference_returns[:n], dtype=float)
    cum_loc = float(np.prod(1.0 + loc))
    cum_ref = float(np.prod(1.0 + ref))
    years = n / ppy
    if years <= 0 or cum_ref <= 0:
        ann_dev = float("inf")
    else:
        ann_dev = (cum_loc / cum_ref) ** (1.0 / years) - 1.0
    max_daily = float(np.max(np.abs(loc - ref))) if n else float("inf")
    return ReconResult(
        n=n,
        ann_dev=ann_dev,
        max_daily_abs=max_daily,
        tol_annual=tol_annual,
        passed=abs(ann_dev) <= tol_annual,
    )
