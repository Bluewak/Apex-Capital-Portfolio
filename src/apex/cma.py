"""CMA 엔진 (v2 §3.2) — 기대수익 빌딩블록 + Ledoit-Wolf shrinkage 공분산.

**왜 표본 평균을 안 쓰나.** 20년(2010~) 강세장 표본의 평균수익을 그대로 μ로 쓰면
기대수익이 과대·forward 리스크가 과소로 잡힌다(강세장 착시). 그래서:
- **μ(기대수익) = forward 빌딩블록.** 주식=Grinold-Kroner(배당+실질이익성장+인플레
  −밸류에이션 회귀), 채권=시작 YTM+롤다운−기대신용손실, 금=인플레+실질. 표본 무관.
- **Σ(공분산) = 데이터 추정.** 변동성·상관 구조는 표본에서 비교적 안정적이라 데이터에서
  뽑되, 소표본 잡음을 Ledoit-Wolf(2004) shrinkage-to-identity로 눌러 PSD·안정 보장.

결정론: 동일 (returns matrix, 가정, 방법) → 동일 CMASet. cma_version이 리니지를 각인.
가정 상수는 문서화(아래 표) — Step 2에서 조정 가능한 단일 소스.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from apex.metrics import TRADING_DAYS
from apex.schemas import CMASet
from apex.universe import ASSET_CLASS

CMA_METHOD_VERSION = "gk-lw-v1"  # Grinold-Kroner μ + Ledoit-Wolf Σ

# ── forward 기대수익 가정(연율, as-of 2026). 조정 가능한 단일 소스 ──
# 공통 거시 가정
_INFLATION = 0.023  # 장기 기대 인플레
# 주식: Grinold-Kroner E[r] = 배당수익률 + 실질이익성장 + 인플레 − 밸류에이션 드래그
_EQUITY: dict[str, dict[str, float]] = {
    #        div    real_growth  val_drag   (인플레는 공통 가산)
    "SPY": {"div": 0.014, "growth": 0.020, "val": 0.008},  # 미 대형
    "QQQ": {"div": 0.006, "growth": 0.035, "val": 0.015},  # 미 성장(고성장·고밸류 드래그)
    "EFA": {"div": 0.030, "growth": 0.012, "val": 0.000},  # 선진 외(저밸류)
    "EEM": {"div": 0.028, "growth": 0.030, "val": 0.000},  # 신흥(고성장·저밸류)
}
# 채권: E[r] = 시작 YTM + 롤다운 − 기대신용손실 (as-of YTM 근사)
_BOND: dict[str, dict[str, float]] = {
    "SHY": {"ytm": 0.043, "roll": 0.000, "credit": 0.000},  # 1-3y 국채(근사 무위험)
    "IEF": {"ytm": 0.042, "roll": 0.002, "credit": 0.000},  # 7-10y 국채
    "TLT": {"ytm": 0.045, "roll": 0.003, "credit": 0.000},  # 20y+ 국채
    "AGG": {"ytm": 0.048, "roll": 0.001, "credit": 0.003},  # 종합(신용 스프레드·손실)
}
# 금: 실질 보유가치(인플레 헤지 + 소폭 실질)
_GOLD_REAL = 0.005


def _expected_return(ticker: str) -> float:
    """티커별 forward 연 기대수익(빌딩블록). 자산군별 다른 모델."""
    cls = ASSET_CLASS[ticker]
    if cls in ("EQ",):
        b = _EQUITY[ticker]
        return b["div"] + b["growth"] + _INFLATION - b["val"]  # Grinold-Kroner
    if cls in ("BOND", "CASH"):
        b = _BOND[ticker]
        return b["ytm"] + b["roll"] - b["credit"]
    if cls == "GOLD":
        return _INFLATION + _GOLD_REAL
    raise KeyError(f"미분류 자산군: {ticker} ({cls})")


def ledoit_wolf(returns: np.ndarray) -> tuple[np.ndarray, float]:
    """Ledoit-Wolf(2004) shrinkage-to-identity 공분산 추정 (일별 스케일).

    Σ̂ = δ·m·I + (1−δ)·S. S=표본공분산, m=평균분산, δ=데이터로 추정한 최적 수축.
    소표본 잡음을 눌러 PSD·조건수 안정 보장(순수 numpy, 결정론).
    반환: (Σ̂_daily, δ).
    """
    x = np.asarray(returns, dtype=float)
    t, n = x.shape
    x = x - x.mean(axis=0, keepdims=True)  # demean
    s = (x.T @ x) / t  # 표본공분산(MLE, 1/T)
    m = np.trace(s) / n  # 평균분산 → 타깃 m·I
    d2 = np.sum((s - m * np.eye(n)) ** 2) / n  # ||S − mI||²_F / n
    # b̄² = 평균 (x_t x_tᵀ − S)의 분산
    b_bar2 = 0.0
    for i in range(t):
        xi = x[i][:, None]
        b_bar2 += np.sum((xi @ xi.T - s) ** 2)
    b_bar2 = b_bar2 / (t**2 * n)
    b2 = min(b_bar2, d2)  # b² ≤ d²
    delta = 0.0 if d2 <= 0 else b2 / d2  # 수축 강도 δ ∈ [0,1]
    sigma = delta * m * np.eye(n) + (1.0 - delta) * s
    return sigma, float(delta)


def build(mat: pd.DataFrame, *, data_version: str, as_of: str = "2026-07-17") -> CMASet:
    """일별 수익률 행렬 → CMASet(μ 빌딩블록 + LW shrinkage Σ, 연율).

    ``mat``: 컬럼=티커, 행=일별 수익률(loader.load_returns_matrix 또는 픽스처).
    결정론: 동일 입력 → 동일 CMASet. cma_version = (data_version·가정·방법) 해시.
    """
    tickers = list(mat.columns)
    mu = {t: round(_expected_return(t), 6) for t in tickers}

    sigma_daily, delta = ledoit_wolf(mat.to_numpy())
    sigma_annual = sigma_daily * TRADING_DAYS
    vol = {t: round(float(np.sqrt(sigma_annual[i, i])), 6) for i, t in enumerate(tickers)}
    cov = [[round(float(sigma_annual[i, j]), 8) for j in range(len(tickers))]
           for i in range(len(tickers))]

    # 리니지 해시: 가정·방법·데이터버전·티커집합을 봉인
    lineage = {
        "method": CMA_METHOD_VERSION,
        "data_version": data_version,
        "tickers": tickers,
        "inflation": _INFLATION,
        "equity": _EQUITY,
        "bond": _BOND,
        "gold_real": _GOLD_REAL,
    }
    cma_version = "cma-" + hashlib.sha256(
        json.dumps(lineage, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]

    return CMASet(
        tickers=tickers,
        mu=mu,
        vol=vol,
        cov=cov,
        shrinkage=round(delta, 6),
        as_of=as_of,
        data_version=data_version,
        cma_version=cma_version,
    )


def build_from_pinned(start: str = "2005-01-01") -> CMASet:
    """피닝 스냅샷(핀 우선)에서 CMASet 구성. 라이브 재수집 없음(v2 §3.1)."""
    from apex.allocation import MODEL_PORTFOLIOS
    from apex.data import loader, snapshot

    universe = tuple(sorted({t for w in MODEL_PORTFOLIOS.values() for t in w}))
    mat = loader.load_returns_matrix(universe, start)
    return build(mat, data_version="real-" + snapshot.pinned_data_version())
