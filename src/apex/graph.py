"""KG 소속 그래프 (docs/12 자리1) — 자산·자산군·통화·테마 관계의 단일 소스.

compliance의 "무엇이 무엇인가"와 노출을 **관계에서 결정론적으로 유도**한다. 규칙을
코드에 흩지 않고 그래프로 옮겨, 판정·근거경로를 이행 클로저 + 가중 집계로 계산한다.
**AI-free** — [11] §5.1(판정에 AI 금지)을 오히려 더 튼튼히 한다(GNN 거부).

핵심 관계(§2.2): `belongsTo{w}`(자산→하위클래스)·`subClassOf`(클래스 계층, 07 §2 4단)·
`exposedTo{w}`(자산→통화, 룩스루). **급소(§8)**: 집계는 **분수 노출의 가중합**이어야
이중계상을 피한다(단순 집합합 금지). 단일소속 티커는 w=1.

개별종목 확장: 종목은 `belongsTo`로 세부테마(07 §6)에 붙고 세부테마→테마군으로
집계된다. 본 모듈은 그 골격 + 코어 9 ETF의 통화·자산군 룩스루를 세운다(종목 시세·
ETF 보유종목 룩스루는 후속 데이터 단계, docs/12 §9·§10).
"""
from __future__ import annotations

import hashlib
import json

GRAPH_VERSION = "kg-v1"

# ── subClassOf: 클래스 계층 (07 §2 4단). 자식 → 부모. 루트=주식/채권/현금성/금 ──
_SUBCLASS: dict[str, str] = {
    "미국대형주": "미국주식", "미국성장주": "미국주식",
    "미국주식": "주식", "선진외주식": "주식", "신흥주식": "주식",
    "미국국채": "채권", "장기국채": "채권", "종합채권": "채권",
    "단기국채": "현금성",
    # 루트(주식·채권·현금성·금)는 부모 없음
}

# ── belongsTo{w}: 자산 → (하위 클래스, 비중). 단일소속 w=1 ──
_BELONGS: dict[str, list[tuple[str, float]]] = {
    "SPY": [("미국대형주", 1.0)], "QQQ": [("미국성장주", 1.0)],
    "EFA": [("선진외주식", 1.0)], "EEM": [("신흥주식", 1.0)],
    "IEF": [("미국국채", 1.0)], "TLT": [("장기국채", 1.0)], "AGG": [("종합채권", 1.0)],
    "SHY": [("단기국채", 1.0)], "GLD": [("금", 1.0)],
}

# ── exposedTo{w}: 자산 → (통화, 비중) 룩스루. 하드코딩 USD 100% 대체 ──
# EFA(선진 외)·EEM(신흥)은 USD 표시지만 **기초통화 노출은 외화**. 아래는 지수 국가비중
# 근사(02·07 문서화 가정) — 실 basket 소싱은 후속(docs/12 §10). 합=1.
_CURRENCY: dict[str, list[tuple[str, float]]] = {
    "SPY": [("USD", 1.0)], "QQQ": [("USD", 1.0)],
    "EFA": [("EUR", 0.33), ("JPY", 0.22), ("GBP", 0.15), ("CHF", 0.10),
            ("AUD", 0.08), ("USD", 0.12)],
    "EEM": [("CNY", 0.30), ("TWD", 0.18), ("INR", 0.16), ("KRW", 0.12),
            ("BRL", 0.05), ("USD", 0.19)],
    "IEF": [("USD", 1.0)], "TLT": [("USD", 1.0)], "AGG": [("USD", 1.0)],
    "SHY": [("USD", 1.0)], "GLD": [("USD", 1.0)],  # 금은 USD 표시(원자재)
}

# ── 테마 택소노미 (07 §6): 세부테마 → 테마군. 개별종목이 붙을 상위 골격 ──
_THEME_GROUPS = ("AI_HW", "SW_CLD", "FIN", "HLTH", "CONS", "COMM", "INDU", "REAL")


def theme_parent(subtheme: str) -> str:
    """세부테마(예 'AI_HW.SEMI') → 테마군('AI_HW'). 07 §6 계층."""
    return subtheme.split(".", 1)[0]


def _norm_ticker(t: str) -> str:
    return t.upper().replace(".", "-")


def theme_exposure(
    holdings: dict[str, float], membership: dict[str, dict], level: str = "theme_group"
) -> dict[str, float]:
    """포트(개별종목 포함) → 테마 노출(가중 룩스루, §8). 종목은 membership으로 테마 매핑.

    ``level``='theme_group'(테마군 8) | 'subtheme'(세부테마). ETF는 보유종목 룩스루
    데이터 부재 시 제외(E3, docs/12 §10) — 개별종목 편입분만 집계. 단일소속 종목은 w=배정비중.
    """
    agg: dict[str, float] = {}
    for tk, w in holdings.items():
        info = membership.get(_norm_ticker(tk))
        if info:
            agg[info[level]] = agg.get(info[level], 0.0) + w
    return {k: round(v, 6) for k, v in agg.items()}


def because_theme(theme: str, holdings: dict[str, float], membership: dict[str, dict]) -> list[str]:
    """테마 노출 근거경로: theme(테마군/세부테마)에 기여한 종목 목록(정규화·재현가능)."""
    return sorted(
        tk for tk in holdings
        if (info := membership.get(_norm_ticker(tk))) is not None
        and theme in (info["theme_group"], info["subtheme"])
    )


def theme_exposure_lookthrough(
    portfolio: dict[str, float],
    membership: dict[str, dict],
    etf_holdings: dict[str, dict[str, float]],
    level: str = "theme_group",
) -> dict[str, float]:
    """포트(ETF+개별종목) → 테마 노출(가중 룩스루 §8, 이중계상 없음, E3).

    ETF는 보유종목으로 분해: 배정비중 × 보유비중 → 그 종목의 테마에 배정. 개별종목은 직접.
    top-N 보유·해외종목 미매핑으로 **커버리지<100%**(나머지는 미집계) — 부분 룩스루.
    """
    agg: dict[str, float] = {}
    for tk, w in portfolio.items():
        etf_h = etf_holdings.get(_norm_ticker(tk)) or etf_holdings.get(tk)
        if etf_h:  # ETF → 보유종목 룩스루
            for stock, wh in etf_h.items():
                info = membership.get(_norm_ticker(stock))
                if info:
                    agg[info[level]] = agg.get(info[level], 0.0) + w * wh
        else:  # 개별종목 직접
            info = membership.get(_norm_ticker(tk))
            if info:
                agg[info[level]] = agg.get(info[level], 0.0) + w
    return {k: round(v, 6) for k, v in agg.items()}


def ancestors(node: str) -> set[str]:
    """subClassOf 이행 클로저(결정론). node 자신은 제외."""
    out: set[str] = set()
    cur = node
    while cur in _SUBCLASS:
        cur = _SUBCLASS[cur]
        out.add(cur)
    return out


def _aggregate(weights: dict[str, float], edges: dict[str, list[tuple[str, float]]],
               closure: bool) -> dict[str, float]:
    """가중 집계(§8 분수 노출). closure=True면 subClassOf 조상까지 전파.

    노출 = Σ(배정비중 × belongs_w [× 조상 전파]). 단순 집합합 금지 — 각 엣지의 분수
    비중을 곱해 이중계상을 피한다.
    """
    agg: dict[str, float] = {}
    for tk, pw in weights.items():
        for node, w in edges.get(tk, [(tk, 1.0)]):
            targets = {node} | (ancestors(node) if closure else set())
            for t in targets:
                agg[t] = agg.get(t, 0.0) + pw * w
    return {k: round(v, 6) for k, v in agg.items()}


def class_exposure(weights: dict[str, float]) -> dict[str, float]:
    """자산군 노출(루트+중간 클래스 모두, 가중·이행). 근거경로는 ``because``."""
    return _aggregate(weights, _BELONGS, closure=True)


def root_class_exposure(weights: dict[str, float]) -> dict[str, float]:
    """루트 자산군(주식/채권/현금성/금)만. 기존 단순 집계와 골든 동일(단일소속)."""
    roots = {"주식", "채권", "현금성", "금"}
    return {k: v for k, v in class_exposure(weights).items() if k in roots}


def currency_exposure(weights: dict[str, float]) -> dict[str, float]:
    """통화 노출 룩스루(가중). 하드코딩 USD 100% 대체(EFA/EEM 외화 분해)."""
    return _aggregate(weights, _CURRENCY, closure=False)


def because(node: str, weights: dict[str, float]) -> list[str]:
    """노출 근거경로: node(자산군)에 기여한 자산 목록(정규화·재현가능)."""
    return sorted(t for t in weights if node in ({b for b, _ in _BELONGS.get(t, [])}
                                                  | {a for b, _ in _BELONGS.get(t, [])
                                                     for a in ancestors(b)}))


def graph_version() -> str:
    """그래프 아티팩트 리니지 해시((관계·택소노미)의 정규화 해시)."""
    payload = json.dumps(
        {"subclass": _SUBCLASS, "belongs": {k: v for k, v in _BELONGS.items()},
         "currency": {k: v for k, v in _CURRENCY.items()}, "themes": list(_THEME_GROUPS),
         "v": GRAPH_VERSION},
        sort_keys=True, ensure_ascii=False,
    )
    return GRAPH_VERSION + "-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
