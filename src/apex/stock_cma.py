"""종목 CMA (v3-A Step 2) — Grinold-Kroner μ(EDGAR 재무+주가) + 팩터구조 Σ.

자산군 CMA([cma.py])의 종목 확장. **μ는 표본평균이 아니라 빌딩블록**(강세장 착시 제거):
  E[r] = 배당수익률 + 자사주수익률 + 이익성장(강한 shrink) − 밸류에이션(현재 0·후속)
배당·자사주·순이익·주식수는 **EDGAR as-first-reported**([fundamentals_pit]), 시가총액은
주가×희석주식수. **종목 이익성장은 자산군보다 훨씬 잡음** → 시장 prior로 강하게 축소(패널).

Σ는 **constant-correlation Ledoit-Wolf**(identity 타깃 금지 — 종목의 시장·섹터 팩터 구조를
무시하면 MVO가 error-max가 됨, 패널 [Med]). 타깃 F = 평균상관 기반. 결정론·PSD.

표본(대량 주가 벽) 기준. 전 유니버스는 후속. loadsOn 명시 팩터모델은 확장 여지.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from apex.metrics import TRADING_DAYS
from apex.schemas import CMASet

STOCK_CMA_METHOD = "stock-gk-cclw-v1"
GK_INPUTS_PATH = Path("artifacts/stock_prices") / "gk_inputs.json"

# GK 가정(조정 가능 단일 소스). 종목 이익성장 강한 shrink → 시장 prior.
_GROWTH_PRIOR = 0.06     # 명목 이익성장 시장 prior(인플레 포함)
_GROWTH_SHRINK = 0.35    # 종목 성장 가중(낮을수록 강한 축소; 종목 μ 잡음 큼)
_GROWTH_CLIP = (-0.05, 0.20)   # 종목 성장 클립(극단 제거)
_MU_CLIP = (0.0, 0.20)         # 최종 μ 클립


def _latest(series: dict) -> float | None:
    """as-first-reported 시계열 {end:{val,...}}에서 최신 기간말 값."""
    if not series:
        return None
    end = max(series)
    return float(series[end]["val"])


def _cagr(series: dict) -> float | None:
    """순이익 시계열 CAGR(명목 이익성장). 부호변화·비양수는 None(폴백 prior)."""
    if len(series) < 3:
        return None
    ends = sorted(series)
    v0, v1 = series[ends[0]]["val"], series[ends[-1]]["val"]
    yrs = int(ends[-1][:4]) - int(ends[0][:4])
    if v0 is None or v1 is None or v0 <= 0 or v1 <= 0 or yrs <= 0:
        return None
    return (v1 / v0) ** (1.0 / yrs) - 1.0


def gk_expected_return(fund: dict, last_price: float) -> dict:
    """Grinold-Kroner 종목 μ + 구성요소(감사용). fund=개념별 as-first-reported 시계열."""
    from apex.data import fundamentals_pit as fp

    shares = _latest(fund.get("diluted_shares", {}))
    mktcap = (last_price * shares) if (shares and shares > 0) else None
    div = _latest(fund.get("dividends_paid", {})) or 0.0
    bb = _latest(fund.get("buybacks", {})) or 0.0
    div_y = (div / mktcap) if mktcap else 0.0
    bb_y = (bb / mktcap) if mktcap else 0.0
    g_raw = _cagr(fund.get("net_income", {}))
    g = _GROWTH_PRIOR if g_raw is None else float(np.clip(g_raw, *_GROWTH_CLIP))
    g_shrunk = _GROWTH_SHRINK * g + (1.0 - _GROWTH_SHRINK) * _GROWTH_PRIOR  # 강한 축소
    mu = float(np.clip(div_y + bb_y + g_shrunk, *_MU_CLIP))
    return {"mu": round(mu, 6), "div_yield": round(div_y, 6), "buyback_yield": round(bb_y, 6),
            "growth_raw": None if g_raw is None else round(g_raw, 6),
            "growth_shrunk": round(g_shrunk, 6), "mktcap": mktcap, "_fp": fp.CORE}


def ledoit_wolf_cc(returns: np.ndarray) -> tuple[np.ndarray, float]:
    """Constant-correlation Ledoit-Wolf(2004) 공분산(일별). identity 아닌 **평균상관 타깃**.

    F_ii=S_ii, F_ij=r̄·√(S_ii S_jj). Σ̂=δF+(1−δ)S, δ=min(b̄²,d²)/d². 종목 팩터구조 보존.
    """
    x = np.asarray(returns, dtype=float)
    t, n = x.shape
    x = x - x.mean(axis=0, keepdims=True)
    s = (x.T @ x) / t
    var = np.diag(s)
    std = np.sqrt(np.clip(var, 1e-18, None))
    corr = s / np.outer(std, std)
    off = corr[~np.eye(n, dtype=bool)]
    r_bar = float(off.mean()) if n > 1 else 0.0
    f = r_bar * np.outer(std, std)  # 타깃 F
    np.fill_diagonal(f, var)
    d2 = np.sum((s - f) ** 2) / n
    b_bar2 = 0.0
    for i in range(t):
        xi = x[i][:, None]
        b_bar2 += np.sum((xi @ xi.T - s) ** 2)
    b_bar2 = b_bar2 / (t**2 * n)
    b2 = min(b_bar2, d2)
    delta = 0.0 if d2 <= 0 else b2 / d2
    sigma = delta * f + (1.0 - delta) * s
    return sigma, float(delta)


def build(returns_matrix, gk_inputs: dict, *, data_version: str, as_of: str) -> CMASet:
    """일별 수익률 행렬 + GK μ 입력 → 종목 CMASet(연율). tickers = 양쪽 교집합·정렬."""
    tickers = sorted(set(returns_matrix.columns) & set(gk_inputs))
    mat = returns_matrix[tickers]
    mu = {t: gk_inputs[t]["mu"] for t in tickers}
    sig_d, delta = ledoit_wolf_cc(mat.to_numpy())
    sig_a = sig_d * TRADING_DAYS
    vol = {t: round(float(np.sqrt(sig_a[i, i])), 6) for i, t in enumerate(tickers)}
    cov = [[round(float(sig_a[i, j]), 8) for j in range(len(tickers))] for i in range(len(tickers))]
    lineage = {"method": STOCK_CMA_METHOD, "data_version": data_version, "tickers": tickers,
               "growth_prior": _GROWTH_PRIOR, "growth_shrink": _GROWTH_SHRINK,
               "mu": mu}
    cma_version = "scma-" + hashlib.sha256(
        json.dumps(lineage, sort_keys=True).encode()).hexdigest()[:12]
    return CMASet(tickers=tickers, mu=mu, vol=vol, cov=cov, shrinkage=round(delta, 6),
                  as_of=as_of, data_version=data_version, cma_version=cma_version)


def pull_gk_inputs(pin: bool = True) -> dict:
    """표본 종목의 GK μ 입력 수집(EDGAR 재무 + 핀 주가). CIK는 membership_pit에서."""
    import os

    from apex.data import fundamentals_pit as fp
    from apex.data.membership_pit import load_membership_pit
    from apex.data.stock_prices import SAMPLE_TICKERS, close_frame, load_prices

    stocks = load_membership_pit().get("stocks", {})
    px = close_frame(load_prices())
    last = px.ffill().iloc[-1] if len(px) else {}
    import requests

    sess = requests.Session()
    inputs: dict[str, dict] = {}
    for t in SAMPLE_TICKERS:
        cik = stocks.get(t, {}).get("cik")
        if not cik or t not in last:
            continue
        facts = fp.pull_company_facts(cik, session=sess)
        if not facts:
            continue
        fund = {c: fp.annual_first_reported(facts, c)
                for c in ("net_income", "dividends_paid", "buybacks", "diluted_shares")}
        gk = gk_expected_return(fund, float(last[t]))
        gk.pop("_fp", None)
        gk["cik"] = cik
        inputs[t] = gk
    _ = os  # UA는 fundamentals_pit._ua()가 env에서
    out = {"n": len(inputs), "inputs": inputs}
    if pin:
        GK_INPUTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        GK_INPUTS_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def load_gk_inputs() -> dict:
    if not GK_INPUTS_PATH.exists():
        return {}
    return json.loads(GK_INPUTS_PATH.read_text(encoding="utf-8")).get("inputs", {})
