"""EDGAR PIT(point-in-time) 재무 추출 (v3-A Step 0 · docs/13 §3.1 pit_fundamentals 바).

SEC EDGAR XBRL API(data.sec.gov)에서 as-reported 재무를 **공시일자(filed)와 함께** 뽑는다.
백테스트 시점 T에는 `filed ≤ T`만 사용 → look-ahead 제거. 같은 기간말(end)에 여러 filed면
**최초 공시(min filed)=as-first-reported**, 이후 filed=restatement. 종목 CMA(Grinold-Kroner:
배당·자사주·이익성장) 입력의 무결성 토대(docs/13 §3.2).

커버리지: XBRL 의무화로 **~2009+**만 신뢰(그 이전 백테스트 절단, docs/13 §3.1·§6).
UA: SEC 공정접근 정책상 **이메일 형식 User-Agent 필수** → env `SEC_EDGAR_UA`(미설정 시 제너릭).
CIK는 위키 membership(`membership_pit`)에서 확보.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path

FUND_DIR = Path("artifacts/fundamentals")
API = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# 표준 개념 → (XBRL 태그 변이, 단위). 회사마다 태깅이 달라 순서대로 첫 존재 태그 사용.
CONCEPTS: dict[str, tuple[list[str], str]] = {
    "net_income": (["NetIncomeLoss", "ProfitLoss"], "USD"),
    "revenue": (["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                 "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"], "USD"),
    "equity": (["StockholdersEquity",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], "USD"),
    "dividends_paid": (["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"], "USD"),
    "buybacks": (["PaymentsForRepurchaseOfCommonStock"], "USD"),
    "diluted_shares": (["WeightedAverageNumberOfDilutedSharesOutstanding"], "shares"),
    "eps_diluted": (["EarningsPerShareDiluted"], "USD/shares"),
}
# 종목 CMA 무결성 최소 핵심(커버리지 게이트 기준)
CORE = ("net_income", "revenue", "equity")


def _ua() -> dict:
    return {"User-Agent": os.environ.get(
        "SEC_EDGAR_UA", "ApexCapitalPortfolio research contact@example.com")}


def pull_company_facts(cik: str, session=None) -> dict:
    """회사 전체 XBRL 팩트(companyfacts). cik는 10자리 zero-pad. 실패 시 {}."""
    import requests

    s = session or requests
    r = s.get(API.format(cik=str(cik).zfill(10)), headers=_ua(), timeout=30)
    if r.status_code != 200:
        return {}
    return r.json()


def _all_points(facts: dict, tags: list[str], unit: str) -> list[tuple[str, dict]]:
    """개념의 **모든 존재 태그**의 데이터포인트 병합 [(tag, point)].

    태그가 시기별로 바뀌는 개념(예: SalesRevenueNet→RevenueFromContract...)의 연도 누락을
    막는다. 같은 기간말은 annual_first_reported의 min-filed dedup가 처리.
    """
    us = facts.get("facts", {}).get("us-gaap", {})
    out: list[tuple[str, dict]] = []
    for tag in tags:
        node = us.get(tag)
        if node and unit in node.get("units", {}):
            out.extend((tag, p) for p in node["units"][unit])
    return out


def annual_first_reported(facts: dict, concept_key: str) -> dict:
    """연간(10-K·FY) as-first-reported 시계열: {end: {val, filed, form, tag, restated_n}}.

    flow(수익·이익 등, start~end ~1년)와 instant(자기자본 등, end만)를 모두 처리.
    같은 end의 최초 filed를 채택(=발표 당시 값), 재작성 횟수는 restated_n으로 병기.
    """
    tags, unit = CONCEPTS[concept_key]
    byend: dict[str, dict] = {}
    for tag, p in _all_points(facts, tags, unit):
        if p.get("fp") != "FY" or not str(p.get("form", "")).startswith("10-K"):
            continue
        start, end, filed = p.get("start"), p.get("end"), p.get("filed")
        if not (end and filed):
            continue
        if start:  # flow → 연간 스팬(~350-380일)만
            span = (date.fromisoformat(end) - date.fromisoformat(start)).days
            if not (350 <= span <= 380):
                continue
        cur = byend.get(end)
        if cur is None:
            byend[end] = {"val": p["val"], "filed": filed, "form": p["form"],
                          "tag": tag, "restated_n": 0}
        else:
            cur["restated_n"] += 1
            if filed < cur["filed"]:  # 더 이른 공시 발견 → as-first-reported 갱신
                cur.update(val=p["val"], filed=filed, form=p["form"], tag=tag)
    return byend


def value_asof(series: dict, asof: str) -> dict | None:
    """as-of 시점에 공시된(filed ≤ asof) 가장 최근 기간말 값. look-ahead 안전."""
    seen = [(end, d) for end, d in series.items() if d["filed"] <= asof]
    if not seen:
        return None
    end, d = max(seen, key=lambda x: x[0])  # 가장 최근 기간말
    return {"end": end, **d}


def company_core_years(facts: dict) -> dict:
    """핵심개념별 as-first-reported 보유 연도 집합 {concept: {year,...}}."""
    return {c: {int(e[:4]) for e in annual_first_reported(facts, c)} for c in CORE}


def pull_sample_coverage(ciks: dict[str, str], years: range | None = None,
                         pin: bool = True, delay: float = 0.12) -> dict:
    """샘플 종목(ticker→cik)의 EDGAR PIT 커버리지 측정. SEC 10 req/s 준수(delay).

    **span-adjusted**: 각 종목의 상장(보고) 기간 ∩ 요청연도에서만 커버리지 측정 —
    IPO 이전 '존재 안 함'을 커버리지 실패로 오계상하지 않는다(정직한 분모).
    """
    import requests

    yrs = list(years if years is not None else range(2010, 2024))
    s = requests.Session()
    per_ticker, covered, total = {}, 0, 0
    for tk, cik in ciks.items():
        facts = pull_company_facts(cik, session=s)
        time.sleep(delay)
        if not facts:
            per_ticker[tk] = {"ok": False}
            continue
        present = company_core_years(facts)
        allyrs = set().union(*present.values()) if any(present.values()) else set()
        span = [y for y in yrs if allyrs and min(allyrs) <= y <= max(allyrs)]
        yhit = sum(1 for y in span if all(y in present[c] for c in CORE))
        per_ticker[tk] = {"ok": True, "cik": cik, "entity": facts.get("entityName", ""),
                          "years_core_complete": yhit, "years_in_span": len(span),
                          "first_year": min(allyrs) if allyrs else None,
                          "last_year": max(allyrs) if allyrs else None}
        covered += yhit
        total += len(span)
    frac = round(covered / total, 4) if total else 0.0
    out = {"n_tickers": len(ciks), "years": [min(yrs), max(yrs)],
           "core_concepts": list(CORE), "core_coverage_frac_span_adjusted": frac,
           "per_ticker": per_ticker}
    if pin:
        FUND_DIR.mkdir(parents=True, exist_ok=True)
        (FUND_DIR / "coverage_sample.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":  # 샘플 커버리지 측정(위키 CIK에서 표본 추출)
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    from apex.data.membership_pit import load_membership_pit

    stocks = load_membership_pit().get("stocks", {})
    sample = {tk: r["cik"] for tk, r in sorted(stocks.items())
              if r["status"] == "current" and r.get("cik")}
    sample = dict(list(sample.items())[:40])  # 앞 40종 표본
    print(f"표본 {len(sample)}종 EDGAR PIT 재무 커버리지 측정(2010~2023, span-adjusted)…")
    res = pull_sample_coverage(sample)
    print(f"핵심({'·'.join(CORE)}) span-adjusted 커버리지: "
          f"{res['core_coverage_frac_span_adjusted']:.1%}")
    ok = [v for v in res["per_ticker"].values() if v.get("ok")]
    print(f"  응답 {len(ok)}/{len(sample)}종")
    for tk, v in list(res["per_ticker"].items())[:8]:
        if v.get("ok"):
            print(f"  {tk} ({v['entity'][:22]}): 핵심완전 {v['years_core_complete']}/"
                  f"{v['years_in_span']}년 (상장 {v['first_year']}~{v['last_year']})")
