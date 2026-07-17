"""KG 소속 그래프 (docs/12 자리1) — 이행 클로저·가중 집계(§8)·통화 룩스루·근거경로.

핵심: 골든 동일성(루트 클래스 == 기존 단순 집계)으로 행동 변화 0을 보장하면서,
세부 클래스·통화 룩스루·근거경로를 관계에서 결정론적으로 유도.
"""
from __future__ import annotations

from apex import graph
from apex.universe import ASSET_CLASS, CLASS_LABEL, CORE_SLOTS


def _simple_class(weights: dict[str, float]) -> dict[str, float]:
    o: dict[str, float] = {}
    for t, v in weights.items():
        o[CLASS_LABEL[ASSET_CLASS[t]]] = o.get(CLASS_LABEL[ASSET_CLASS[t]], 0.0) + v
    return {k: round(v, 6) for k, v in o.items()}


_PORT = {"SPY": 0.30, "QQQ": 0.20, "EFA": 0.15, "EEM": 0.10,
         "IEF": 0.10, "AGG": 0.05, "GLD": 0.05, "SHY": 0.05}


def test_transitive_closure():
    assert graph.ancestors("미국대형주") == {"미국주식", "주식"}
    assert graph.ancestors("단기국채") == {"현금성"}
    assert graph.ancestors("주식") == set()  # 루트는 조상 없음


def test_root_class_golden_equivalence():
    """루트 자산군 == 기존 단순 ASSET_CLASS 집계(행동 변화 0). docs/12 §9."""
    assert graph.root_class_exposure(_PORT) == _simple_class(_PORT)


def test_weighted_aggregation_sums_and_no_double_count():
    """루트 클래스 합 = 1(가중·분수, 이중계상 없음). 중간 클래스는 부분합."""
    roots = graph.root_class_exposure(_PORT)
    assert abs(sum(roots.values()) - 1.0) < 1e-9
    cls = graph.class_exposure(_PORT)
    assert abs(cls["미국주식"] - 0.50) < 1e-9  # SPY0.30+QQQ0.20
    assert abs(cls["주식"] - 0.75) < 1e-9  # 미국0.50+선진외0.15+신흥0.10


def test_currency_lookthrough_decomposes_foreign():
    """EFA/EEM은 USD 100% 아님(기초통화 외화 분해). 국내 ETF는 USD 100%."""
    assert graph.currency_exposure({"SPY": 1.0}) == {"USD": 1.0}
    efa = graph.currency_exposure({"EFA": 1.0})
    assert efa.get("USD", 1.0) < 0.5 and "JPY" in efa and "EUR" in efa
    eem = graph.currency_exposure({"EEM": 1.0})
    assert "CNY" in eem and "KRW" in eem


def test_currency_sums_to_one():
    exp = graph.currency_exposure(_PORT)
    assert abs(sum(exp.values()) - 1.0) < 1e-6
    assert exp["USD"] < 1.0  # 룩스루로 외화 존재


def test_because_path_is_sorted_and_deterministic():
    assert graph.because("주식", _PORT) == ["EEM", "EFA", "QQQ", "SPY"]
    assert graph.because("채권", _PORT) == ["AGG", "IEF"]


def test_all_core_slots_have_membership():
    """코어 9슬롯 전부 belongsTo·exposedTo 정의(누락 방지)."""
    for t in CORE_SLOTS:
        assert graph.class_exposure({t: 1.0})  # 자산군 소속 존재
        assert abs(sum(graph.currency_exposure({t: 1.0}).values()) - 1.0) < 1e-6


def test_graph_version_stable():
    assert graph.graph_version() == graph.graph_version()
    assert graph.graph_version().startswith("kg-v1-")
