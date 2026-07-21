"""이벤트 구동 종목 백테스트 (v3-A Step 2) — 가변 유니버스·상폐 현금화.

기존 `loader`는 `join="inner"`(공통창 강제)+고정 유니버스라 종목 백테스트 불가(패널 [High]).
여기선 **분기 리밸런싱마다 as-of 유니버스**(PIT membership)로 종목이 편입·편출되고, 보유
종목이 **상폐/편출되면 종료수익(delisting_returns)으로 현금화** 후 제거한다. 결정론.

표본(대량 주가 벽) 기준. 상폐 현금화 경로는 합성 데이터로 검증(표본 현행종목엔 미발생).
검증 게이트: PSR·DSR(5바스켓 다중검정 보정, validation.py)·walk-forward.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from apex import metrics as M
from apex import validation


def rebalance_dates(index: pd.DatetimeIndex) -> list:
    """각 분기 첫 거래일(리밸런싱 시점)."""
    df = pd.DataFrame(index=index)
    return [g.index[0] for _, g in df.groupby([index.year, index.quarter])]


def backtest(prices: pd.DataFrame, weight_fn, members_asof=None,
             terminal_returns: dict | None = None) -> pd.Series:
    """분기 리밸 이벤트 백테스트 → 일별 포트 수익률 시계열.

    weight_fn(universe, asof)→{ticker:weight}. members_asof(asof)→set(가변 유니버스).
    terminal_returns[ticker]=상폐 종료수익(보유 중 편출 시 현금화). 결정론.
    """
    rets = prices.pct_change()
    rdates = rebalance_dates(prices.index)
    bounds = list(zip(rdates, rdates[1:] + [prices.index[-1]], strict=True))
    parts: list[pd.Series] = []
    for t0, t1 in bounds:
        universe = [t for t in prices.columns if pd.notna(prices.at[t0, t])]
        if members_asof is not None:
            asof = t0.date().isoformat()
            members = members_asof(asof)
            universe = [t for t in universe if t in members]
        if not universe:
            continue
        weights = weight_fn(universe, t0)
        if not weights:
            continue
        win = rets.loc[t0:t1].iloc[1:]  # t0 이후 일별 수익률
        sub = win[list(weights)].copy()
        for t in list(weights):  # 상폐/편출 현금화: 보유 중 NaN 발생
            col = sub[t]
            if col.isna().any():
                lv = col.last_valid_index()
                nans = col.index[col.isna()]
                after = nans[nans > lv] if lv is not None else nans
                if len(after):  # 첫 결측일에 종료수익 적용, 이후 현금(0)
                    sub.loc[after[0], t] = (terminal_returns or {}).get(t, 0.0)
            sub[t] = sub[t].fillna(0.0)
        w = pd.Series(weights)
        parts.append((sub * w).sum(axis=1))
    if not parts:
        return pd.Series(dtype=float)
    return pd.concat(parts).sort_index()


def metrics(series: pd.Series) -> dict:
    """백테스트 지표: 누적·CAGR·연변동성·Sharpe·MDD·PSR."""
    r = series.to_numpy()
    if len(r) < 10:
        return {"n_days": len(r)}
    yrs = len(r) / M.TRADING_DAYS
    total = float(np.prod(1.0 + r) - 1.0)
    cagr = (1.0 + total) ** (1.0 / yrs) - 1.0 if yrs > 0 else 0.0
    return {
        "n_days": len(r), "total_return": round(total, 6), "cagr": round(cagr, 6),
        "vol_annual": round(M.vol_annual(r), 6), "mdd": round(M.mdd(r), 6),
        "sharpe": round(M.sharpe(r), 6),
        "psr_vs_zero": round(validation.probabilistic_sharpe(r, 0.0), 6),
        "walk_forward_stable": validation.walk_forward_stable(r),
    }


def validate_baskets(profile_series: dict[str, pd.Series]) -> dict:
    """5성향 바스켓 백테스트 → DSR 다중검정 보정 게이트(validation.py).

    각 바스켓 일별 Sharpe로 SR*(deflated) 산출 → 각 바스켓 PSR을 SR* 기준으로 재평가.
    PSR(vs SR*) > 0.95면 다중검정 하에서도 유의(백테스트 방어).
    """
    daily_sr, mets = {}, {}
    for pv, s in profile_series.items():
        r = s.to_numpy()
        mets[pv] = metrics(s)
        daily_sr[pv] = float(r.mean() / r.std(ddof=1)) if len(r) > 10 and r.std(ddof=1) > 0 else 0.0
    sr_star = validation.deflated_sr_benchmark(list(daily_sr.values()))
    out = {}
    for pv, s in profile_series.items():
        dsr = validation.probabilistic_sharpe(s.to_numpy(), sr_star)
        out[pv] = {**mets[pv], "daily_sharpe": round(daily_sr[pv], 6),
                   "dsr_vs_srstar": round(dsr, 6), "dsr_pass": dsr > 0.95}
    return {"sr_star_daily": round(sr_star, 6), "per_profile": out}
