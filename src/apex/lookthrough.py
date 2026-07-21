"""Tier 0 종목 룩스루 분석 (v3-A Step 1 · docs/13 §3).

예시 ETF 포트를 개별종목으로 **분해**해 집중도·테마·통화 노출과 단일종목 집중 경고를 낸다.
종목은 분해·근거로만 등장하고 **배분·numeric_hash에는 들어가지 않는다**(Tier 0 규제 경계).
holdings top-N·해외종목 미매핑으로 커버리지<100% — 정직하게 각인.

데이터: `data.holdings`(ETF 보유종목 핀)·`data.membership`(종목→테마). loadsOn 팩터 분해는
팩터 데이터 필요 → v3-A Step 2(종목 CMA)에서.
"""
from __future__ import annotations

from apex import graph
from apex.schemas.lookthrough import LookthroughReport, StockConcentration
from apex.schemas.risk import Breach

# 단일종목 실효 집중 상한(disclosed 경고). UCITS 10% 관행 준용.
DEFAULT_SINGLE_STOCK_CAP = 0.10
_TOL = 1e-9


def analyze(
    weights: dict[str, float],
    holdings: dict[str, dict[str, float]],
    membership: dict[str, dict],
    single_stock_cap: float = DEFAULT_SINGLE_STOCK_CAP,
    top_n: int = 15,
) -> LookthroughReport:
    """포트 → Tier 0 룩스루 리포트(집중도·테마·통화·단일종목 경고). 결정론·재현가능."""
    universe = set(membership)
    eff, coverage = graph.stock_exposure_lookthrough(weights, holdings, universe)
    items = sorted(eff.items(), key=lambda kv: (-kv[1], kv[0]))  # 비중 내림, 티커 정규화

    top_stock, top_weight = (items[0][0], items[0][1]) if items else (None, 0.0)
    conc = StockConcentration(
        top_stock=top_stock, top_weight=round(top_weight, 6),
        top5_sum=round(sum(w for _, w in items[:5]), 6),
        herfindahl=round(sum(w * w for w in eff.values()), 6),
        n_stocks=len(eff),
    )
    themes = graph.theme_exposure_lookthrough(weights, membership, holdings, level="theme_group")
    breaches = [
        Breach(metric=f"stock_concentration:{s}", limit=single_stock_cap,
               actual=round(w, 6), because=[s])
        for s, w in items if w > single_stock_cap + _TOL
    ]
    return LookthroughReport(
        coverage=coverage, single_stock_cap=single_stock_cap, concentration=conc,
        stock_exposure=dict(items[:top_n]),
        theme_exposure=dict(sorted(themes.items(), key=lambda kv: -kv[1])),
        currency_exposure=graph.currency_exposure(weights), breaches=breaches,
    )


def analyze_pinned(weights: dict[str, float], **kw) -> LookthroughReport:
    """피닝된 holdings·membership로 분석(오프라인 안전, 부재 시 빈 데이터)."""
    from apex.data.holdings import load_holdings
    from apex.data.membership import load_membership

    return analyze(weights, load_holdings(), load_membership(), **kw)


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    # 예시 포트(성장형 근사) 룩스루
    port = {"SPY": 0.45, "QQQ": 0.20, "EFA": 0.10, "EEM": 0.05, "IEF": 0.15, "GLD": 0.05}
    rep = analyze_pinned(port)
    print(f"예시 포트 {port}")
    print(f"룩스루 커버리지: {rep.coverage:.1%} (top-N holdings — 나머지 미분해)")
    c = rep.concentration
    print(f"단일종목 집중: 최대 {c.top_stock} {c.top_weight:.2%} · top5 {c.top5_sum:.2%} "
          f"· HHI {c.herfindahl:.4f} · 종목수 {c.n_stocks}")
    print("실효 종목 노출 top8:")
    for s, w in list(rep.stock_exposure.items())[:8]:
        print(f"    {s}: {w:.2%}")
    print(f"테마 노출: { {k: round(v,3) for k,v in rep.theme_exposure.items()} }")
    print(f"통화 노출: { {k: round(v,3) for k,v in rep.currency_exposure.items()} }")
    print(f"단일종목 집중 경고(>{rep.single_stock_cap:.0%}): {len(rep.breaches)}건")
