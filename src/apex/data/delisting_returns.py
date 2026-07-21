"""편출 종목 종료수익 근사 (v3-A Step 0 · docs/13 §3.1 delisting_return_coverage 바).

편출 시점 종료수익(합병=인수가 청산, 파산=대손, 리밸런싱=계속 거래)을 **사유 기반으로 근사**
한다. "마지막 가격 −100% 드롭" 일괄 근사는 방향부터 틀리므로(패널 지적, 대부분 M&A),
`membership_pit`의 편출사유 분류(ma/bankruptcy/rebalance/other)를 종료수익 규칙에 매핑.

**교체가능성(북극성 "뼈대 교체").** 모든 값에 `is_approximation=True`·`method`·`source`·
`confidence`를 각인 → 나중에 실 종료수익(CRSP/Norgate/뉴스 인수가)을 `(ticker, out_date)`
키로 **개별 교체** 가능. 교체 시 `is_approximation=False`·`source="vendor_..."`로 전환.

종료수익은 백테스트(v3-A Step 2)에서 편출 시점에 적용된다: 최종 보유가 대비 청산 손익.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

DELISTING_DIR = Path("artifacts/delisting")
RETURNS_PATH = DELISTING_DIR / "returns.json"
RULES_VERSION = "reason-heuristic-v1"

# 사유 → (종료수익, 신뢰도). 마지막 거래가 대비 편출 이벤트에서 realize되는 초과손익.
DELISTING_RULES: dict[str, tuple[float, str]] = {
    "ma": (0.0, "medium"),          # 인수가 ≈ 시장가로 현금청산(프리미엄은 이미 가격 반영)
    "rebalance": (0.0, "high"),     # 계속 거래 — 종료이벤트 없음, 시장가로 리밸 청산
    "bankruptcy": (-1.0, "medium"),  # 대손(보수적 총손실). 실 회수율로 교체 여지
    "other": (0.0, "low"),          # 미상 — 시장가 청산 가정(저신뢰, 교체 우선순위)
}


def build_delisting_returns(pit_stocks: dict) -> dict:
    """편출 인터벌(out!=None)마다 종료수익 근사 + 교체가능 provenance. 키=`ticker@out_date`."""
    out: dict[str, dict] = {}
    for tk, rec in pit_stocks.items():
        for iv in rec["intervals"]:
            od = iv.get("out")
            if not od:
                continue  # 현재까지 보유(종료 없음)
            reason = iv.get("out_reason") or "other"
            tr, conf = DELISTING_RULES.get(reason, DELISTING_RULES["other"])
            out[f"{tk}@{od}"] = {
                "ticker": tk, "out_date": od, "reason": reason,
                "terminal_return": tr, "confidence": conf,
                "is_approximation": True, "method": f"approx_{reason}",
                "source": "reason_heuristic", "replaceable": True,
            }
    return out


def coverage_report(returns: dict) -> dict:
    """종료수익 커버리지 + 신뢰도 분포. 모든 편출에 값 배정(사유는 항상 존재) → 근사 품질이 관건."""
    conf = defaultdict(int)
    approx = 0
    for e in returns.values():
        conf[e["confidence"]] += 1
        approx += int(e["is_approximation"])
    n = len(returns)
    return {
        "n_exits": n,
        "coverage_frac": 1.0 if n else 0.0,   # 사유 분류가 100%라 배정 커버리지=100%
        "is_approximation": approx == n and n > 0,
        "approximation_frac": round(approx / n, 4) if n else 0.0,
        "confidence_breakdown": dict(conf),
    }


def build_and_pin(pit_stocks: dict, pin: bool = True) -> dict:
    """종료수익 근사 산출·피닝. version = hash(returns, rules_version)."""
    returns = build_delisting_returns(pit_stocks)
    cov = coverage_report(returns)
    ver = hashlib.sha256(
        json.dumps({"r": returns, "rules": RULES_VERSION}, sort_keys=True,
                   ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
    out = {"returns_version": ver, "rules_version": RULES_VERSION,
           "coverage": cov, "returns": returns}
    if pin:
        DELISTING_DIR.mkdir(parents=True, exist_ok=True)
        RETURNS_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def load_delisting_returns() -> dict:
    """피닝된 종료수익. 부재 시 빈 dict(오프라인 안전)."""
    if not RETURNS_PATH.exists():
        return {}
    return json.loads(RETURNS_PATH.read_text(encoding="utf-8"))


def terminal_return(returns: dict, ticker: str, out_date: str) -> dict | None:
    """(ticker, out_date) 종료수익 조회. 근사 여부·신뢰도 포함(백테스트에서 사용)."""
    return returns.get(f"{ticker}@{out_date}")


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    from apex.data.membership_pit import load_membership_pit

    stocks = load_membership_pit().get("stocks", {})
    res = build_and_pin(stocks)
    cov = res["coverage"]
    print(f"종료수익 근사: {cov['n_exits']}건 (version {res['returns_version']})")
    print(f"  커버리지 {cov['coverage_frac']:.0%} · 전부 근사={cov['is_approximation']} "
          f"(is_approximation=True → 실데이터 교체가능)")
    print(f"  신뢰도 분포: {cov['confidence_breakdown']}")
    # 예시 몇 건
    for k, e in list(res["returns"].items())[:5]:
        print(f"  {k}: reason={e['reason']} term_ret={e['terminal_return']:+.0%} "
              f"conf={e['confidence']} method={e['method']}")
