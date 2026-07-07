"""07 §7 포트↔상한 사전검증 게이트 (M5, 08 §3).

5종 고정포트를 실 20년 스냅샷으로 백테스트해, 각 성향의 05 §3 **평시 상한**
(위기 3구간 제외) 통과 여부를 판정한다. 바인딩(차단)은 var95_annual(R5);
2008/2020/2022 실측 손실은 disclosed(차단 아님). 벤치마크 3종 비교 포함.

DoD: 5종이 각 성향 평시 상한 통과(특히 초안정형 VaR≤-5%) + 스트레스 공시.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from apex import metrics
from apex.allocation import MODEL_PORTFOLIOS
from apex.compliance import PROFILE_LIMITS
from apex.data import loader

_KOSPI = "069500.KS"
_TOL = 1e-9


@dataclass
class GateRow:
    profile: str
    vol: float          # 평시 연변동성
    mdd_normal: float   # 평시 최대낙폭
    var_annual: float   # 평시 연율 VaR95 (바인딩)
    lim: dict           # 성향 상한
    cagr_full: float    # 전구간 CAGR
    stress: dict        # {구간: 낙폭} — disclosed

    @property
    def passed(self) -> bool:
        """차단 판정 = var95_annual 평시 상한(R5). vol/mdd는 참고."""
        return self.var_annual <= self.lim["var"] + _TOL

    @property
    def vol_ok(self) -> bool:
        return self.vol <= self.lim["vol"] + _TOL

    @property
    def mdd_ok(self) -> bool:
        return self.mdd_normal >= self.lim["mdd"] - _TOL


def _universe() -> tuple[str, ...]:
    return tuple(sorted({t for w in MODEL_PORTFOLIOS.values() for t in w}))


def _bench_stats(ret: np.ndarray) -> dict[str, float]:
    return {
        "cagr": metrics.cagr(ret),
        "vol": metrics.vol_annual(ret),
        "sharpe": metrics.sharpe(ret),
        "mdd": metrics.mdd(ret),
    }


def run(start: str = "2005-01-01", end: str | None = None) -> dict:
    """게이트 실행. 반환: rows(5종)·benchmarks(3종)·기간."""
    mat = loader.load_returns_matrix(_universe(), start, end)

    rows: list[GateRow] = []
    for profile, weights in MODEL_PORTFOLIOS.items():
        port = loader.portfolio_returns_quarterly(mat, weights, cost_bps=loader.DEFAULT_COST_BPS)
        normal, windows = loader.split_normal_stress(port)
        rows.append(
            GateRow(
                profile=profile.value,
                vol=metrics.vol_annual(normal),
                mdd_normal=metrics.mdd(normal),
                var_annual=metrics.var95_annual(normal),
                lim=PROFILE_LIMITS[profile],
                cagr_full=metrics.cagr(port.to_numpy()),
                stress={n: loader.window_drawdown(w) for n, w in windows.items()},
            )
        )

    benchmarks: dict[str, dict] = {
        "S&P500 (SPY TR)": _bench_stats(mat["SPY"].to_numpy()),
        "60/40 (SPY60+IEF40)": _bench_stats(
            loader.portfolio_returns_quarterly(
                mat, {"SPY": 0.6, "IEF": 0.4}, cost_bps=loader.DEFAULT_COST_BPS
            ).to_numpy()
        ),
    }
    try:
        kospi = loader.load_ticker_returns(_KOSPI, start, end)
        benchmarks["KOSPI200 (KODEX200, KRW)"] = _bench_stats(kospi.to_numpy())
    except Exception as e:  # noqa: BLE001 — 벤치마크 소싱 실패는 게이트 중단 아님
        benchmarks["KOSPI200 (KODEX200, KRW)"] = {"error": str(e)[:50]}

    return {
        "rows": rows,
        "benchmarks": benchmarks,
        "n_days": len(mat),
        "period": (str(mat.index[0].date()), str(mat.index[-1].date())),
    }
