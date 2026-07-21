"""v3-A 종목 엔진 오케스트레이터 — 핀 데이터 → CMA → 바스켓 → 백테스트 → numeric_hash.

결정론 코어 조립(AI 없음). **재현성**: 동일 핀 입력 → 동일 `numeric_hash`([11] §5.8 재현성
2체크포인트). 핀 우선(라이브 fetch 없음) — 부재 시 하드 실패. Step 0~2 산출물을 한 진입점으로.
"""
from __future__ import annotations

import hashlib
import json

from apex import stock_backtest, stock_cma, stock_optimizer
from apex.data.stock_prices import close_frame, load_prices, returns_matrix
from apex.schemas.enums import Profile


def _round(o, nd: int = 8):
    """재현성용 정규화: float 반올림(rtol≤1e-6 안정), 컨테이너 재귀."""
    if isinstance(o, float):
        return round(o, nd)
    if isinstance(o, dict):
        return {k: _round(v, nd) for k, v in o.items()}
    if isinstance(o, list):
        return [_round(v, nd) for v in o]
    return o


def numeric_hash(result: dict) -> str:
    """수치 산출물의 canonical 해시(numeric_hash 자신 제외). 서술 미포함(§5.2)."""
    payload = _round({k: v for k, v in result.items() if k != "numeric_hash"})
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]


def run(data_version: str = "sample-v1", as_of: str = "2026-07-20",
        backtest: bool = True) -> dict:
    """핀 → 종목 CMA → 5성향 예시 바스켓 → (선택)이벤트 백테스트 → numeric_hash. 결정론."""
    prices_doc = load_prices()
    gk = stock_cma.load_gk_inputs()
    if not prices_doc or not gk:
        raise RuntimeError("핀 부재 — stock_prices.pull_prices + stock_cma.pull_gk_inputs 필요")

    cma = stock_cma.build(returns_matrix(prices_doc), gk,
                          data_version=data_version, as_of=as_of)
    baskets = stock_optimizer.optimize_all_profiles(cma)
    result: dict = {"cma_version": cma.cma_version, "tickers": cma.tickers,
                    "mu": cma.mu, "shrinkage": cma.shrinkage, "baskets": baskets}

    if backtest:
        px = close_frame(prices_doc)
        series = {}
        for p in Profile:
            weights = baskets[p.value]["weights"]

            def _wf(universe, asof, w=weights):
                sub = {t: x for t, x in w.items() if t in universe}
                s = sum(sub.values())
                return {k: v / s for k, v in sub.items()} if s > 0 else {}

            series[p.value] = stock_backtest.backtest(px, _wf)
        result["backtest"] = stock_backtest.validate_baskets(series)

    result["numeric_hash"] = numeric_hash(result)
    return result


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    r = run()
    print(f"v3-A numeric_hash = {r['numeric_hash']}  (cma {r['cma_version']})")
    print(f"  종목수 {len(r['tickers'])}, shrinkage δ={r['shrinkage']}")
    for pv, b in r["baskets"].items():
        m, bt = b["metrics"], r["backtest"]["per_profile"][pv]
        print(f"  {pv}: E[r]={m['expected_return']:.1%} vol={m['vol']:.1%} | "
              f"백테스트 CAGR={bt['cagr']:.1%} Sharpe={bt['sharpe']:.2f} DSR통과={bt['dsr_pass']}")
