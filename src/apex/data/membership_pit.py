"""S&P500 PIT(point-in-time) 구성원 리컨스트럭터 (v3-A Step 0, docs/13 §3.1).

시기별 백테스트는 "그 시점 실제 지수 구성"을 알아야 하므로 **편입/편출 일자**가 필수다.
기존 `membership.py`(현행 503 스냅샷)·`tools/sp500`(union 생성기)의 3대 결함을 고친다:

  1. **편입일자 파싱** — 위키 변경표의 Added/Removed **양쪽**을 Effective Date와 함께 읽는다
     (`tools/sp500.parse_removed`는 Removed만 읽고 Added를 버렸음).
  2. **재편입 보존** — 종목별 **다구간 인터벌** `[{in,out}]`을 세운다(편입→편출→재편입을
     "현재"로 붕괴시키지 않음, docs/13 §7).
  3. **소스 리비전 핀** — 위키 `oldid`를 `membership_version`에 편입(재현성, [11] §5.8·§5.4).

**안정 식별자**: 위키 현행표의 CIK를 1급 식별자로 병기(티커 재사용/변경 대비, docs/13 §3.1).
**편출사유 분류**: Reason 텍스트 → M&A/파산/리밸런싱(사유별 종료수익 규칙의 토대, docs/13 §3.1).
**정직한 한계**: 변경표는 *Selected*(비망라)라 커버리지 시작 이전 편입은 **좌측절단**(in=None)으로
표기 → kill-switch 게이트(docs/13 §3.1)가 좌측절단 비율을 재료로 삼는다.

라이브 fetch는 `pull_membership_pit`에서만(핀 우선). 인터넷·위키는 열려 있음(2026-07-21 확인).
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from io import StringIO
from pathlib import Path

MEMBERSHIP_DIR = Path("artifacts/membership")
PIT_PATH = MEMBERSHIP_DIR / "pit.json"

WIKI_TITLE = "List_of_S%26P_500_companies"
WIKI_URL = f"https://en.wikipedia.org/wiki/{WIKI_TITLE}"
API_URL = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ApexSP500PITBot/1.0)"}


def _norm(t: str) -> str:
    """티커 정규화(그래프·membership과 동일): 대문자 + '.'→'-'."""
    return str(t).strip().upper().replace(".", "-")


def classify_reason(reason: str) -> str:
    """편출 사유 → {ma, bankruptcy, rebalance, other}. 사유별 종료수익 규칙의 토대(docs/13 §3.1).

    M&A는 인수프리미엄(양의 종료), 파산은 대손(−), 리밸런싱은 계속 거래. '마지막 가격 −100%'
    일괄 근사는 방향부터 틀리므로(패널 지적) 사유를 보존한다.
    """
    r = (reason or "").lower()
    if any(k in r for k in ("acqui", "merg", "bought", "taken private", "purchased", "buyout")):
        return "ma"
    if any(k in r for k in ("bankrupt", "chapter 11", "liquidat", "financial distress", "delist")):
        return "bankruptcy"
    if any(k in r for k in ("market cap", "no longer", "rebalanc", "float", "criteria",
                            "make room", "index")):
        return "rebalance"
    return "other"


def _fetch():
    """위키 현행표 + 변경표 + 소스 oldid. requests(User-Agent 필수 — 없으면 403)."""
    import pandas as pd
    import requests

    page = requests.get(WIKI_URL, headers=HEADERS, timeout=30)
    page.raise_for_status()
    tables = pd.read_html(StringIO(page.text))
    # 소스 리비전(oldid) — 재현성 핀(패널 [High])
    rev = requests.get(
        API_URL, headers=HEADERS, timeout=30,
        params={"action": "query", "prop": "revisions", "titles": WIKI_TITLE.replace("%26", "&"),
                "rvprop": "ids|timestamp", "rvlimit": 1, "format": "json"},
    ).json()
    pages = rev["query"]["pages"]
    revinfo = next(iter(pages.values()))["revisions"][0]
    return tables, {"oldid": revinfo["revid"], "revision_timestamp": revinfo["timestamp"]}


def _parse_current(tables) -> dict:
    """현행 503종: {ticker: {cik, name, sector, sub, date_added}}."""
    import pandas as pd

    for t in tables:
        cols = {str(c).strip().lower(): c for c in t.columns}
        sym = next((cols[k] for k in cols if "symbol" in k), None)
        cik = next((cols[k] for k in cols if k == "cik"), None)
        if not (sym and cik):
            continue
        sec = next((cols[k] for k in cols if "sector" in k), None)
        sub = next((cols[k] for k in cols if "sub-industry" in k or "sub industry" in k), None)
        nam = next((cols[k] for k in cols if "security" in k), None)
        dadd = next((cols[k] for k in cols if "date added" in k or "date_added" in k), None)
        out = {}
        dates = pd.to_datetime(t[dadd], errors="coerce") if dadd else None
        for i, (_, row) in enumerate(t.iterrows()):
            tk = _norm(row[sym])
            if not tk or tk == "NAN":
                continue
            d = dates.iloc[i] if dates is not None else None
            out[tk] = {
                "cik": None if pd.isna(row[cik]) else str(int(row[cik])).zfill(10),
                "name": str(row[nam]).strip() if nam else "",
                "sector": str(row[sec]).strip() if sec else "",
                "sub": str(row[sub]).strip() if sub else "",
                "date_added": None if (d is None or pd.isna(d)) else d.date().isoformat(),
            }
        if out:
            return out
    raise RuntimeError("현행 구성종목 표를 찾지 못함(위키 구조 변경?).")


def _parse_changes(tables) -> list:
    """변경표: [{date, add, remove, reason}] (add/remove는 정규화 티커 또는 None)."""
    import pandas as pd

    for t in tables:
        tt = t.copy()
        tt.columns = ["_".join(dict.fromkeys(str(x) for x in c)) if isinstance(c, tuple)
                      else str(c) for c in tt.columns]
        low = {c.lower(): c for c in tt.columns}
        dcol = next((low[k] for k in low if "date" in k), None)
        acol = next((low[k] for k in low if "added" in k and "ticker" in k), None)
        rcol = next((low[k] for k in low if "removed" in k and "ticker" in k), None)
        rsn = next((low[k] for k in low if "reason" in k), None)
        if not (dcol and (acol or rcol)):
            continue
        dates = pd.to_datetime(tt[dcol], errors="coerce")
        rows = []
        for i, (_, row) in enumerate(tt.iterrows()):
            d = dates.iloc[i]
            if pd.isna(d):
                continue
            add = _norm(row[acol]) if acol and not pd.isna(row[acol]) else None
            rem = _norm(row[rcol]) if rcol and not pd.isna(row[rcol]) else None
            if add == "NAN":
                add = None
            if rem == "NAN":
                rem = None
            if not (add or rem):
                continue
            rows.append({"date": d.date().isoformat(), "add": add, "remove": rem,
                         "reason": str(row[rsn]).strip() if rsn else ""})
        if rows:
            return rows
    return []


def reconstruct(current: dict, changes: list) -> dict:
    """현행 + 변경 → 종목별 다구간 PIT 인터벌(역방향 걷기). 결정론·재현가능.

    역방향 걷기: '지금' 상태(현행 여부)에서 시작해 변경 이벤트를 최신→과거로 되감으며
    in-인터벌을 열고 닫는다. 최초 이벤트보다 이전까지 in이면 **좌측절단**(커버리지 밖 편입).
    현행 종목은 위키 'Date added'로 좌측절단을 보정(대부분 편입일자 확보).
    """
    events: dict[str, list] = defaultdict(list)
    for ch in changes:
        if ch["add"]:
            events[ch["add"]].append((ch["date"], "add", ch["reason"]))
        if ch["remove"]:
            events[ch["remove"]].append((ch["date"], "remove", ch["reason"]))

    out: dict[str, dict] = {}
    for tk in sorted(set(current) | set(events)):
        evs = sorted(events.get(tk, []), key=lambda e: e[0], reverse=True)  # 최신 먼저
        is_cur = tk in current
        intervals: list[dict] = []
        open_iv: dict | None = {"in": None, "out": None} if is_cur else None
        for d, kind, reason in evs:
            if kind == "add":
                if open_iv is not None:
                    open_iv["in"] = d
                    open_iv["left_censored"] = False  # in이 알려진 날짜 → 좌측절단 아님
                    intervals.append(open_iv)
                    open_iv = None
                else:  # 편입인데 열린 인터벌 없음 = 편출이 커버리지 밖/누락(고아)
                    intervals.append({"in": d, "out": d, "orphan": True, "left_censored": False})
            else:  # remove
                if open_iv is None:
                    open_iv = {"in": None, "out": d, "out_reason": classify_reason(reason)}
                else:  # 이미 열림(이중 편출) — best effort
                    open_iv["out"] = d
                    open_iv["out_reason"] = classify_reason(reason)
        if open_iv is not None:  # 최초 이벤트 이전까지 in
            # 위키 'Date added'는 *가장 최근* 편입일 → 현재까지 이어지는 스틴(out=None)에만 적용.
            # 과거 스틴(out!=None, 재편입 전 옛 구간)은 편입일 미상 = 좌측절단(커버리지 밖).
            da = current.get(tk, {}).get("date_added")
            if da and open_iv["out"] is None:
                open_iv["in"] = da
                open_iv["left_censored"] = False
            else:
                open_iv["left_censored"] = True
            intervals.append(open_iv)
        intervals.sort(key=lambda iv: iv.get("in") or "0000-00-00")
        meta = current.get(tk, {})
        out[tk] = {
            "cik": meta.get("cik"),
            "name": meta.get("name", ""),
            "sector": meta.get("sector", ""),
            "sub": meta.get("sub", ""),
            "status": "current" if is_cur else "removed",
            "intervals": intervals,
        }
    return out


def members_asof(pit: dict, date: str) -> set[str]:
    """as-of 구성원 집합(좌측절단은 out만 존재하면 포함). date='YYYY-MM-DD'."""
    out = set()
    for tk, rec in pit.items():
        for iv in rec["intervals"]:
            lo = iv.get("in")  # None=좌측절단(무한 과거부터)
            hi = iv.get("out")  # None=현재까지
            if (lo is None or lo <= date) and (hi is None or date < hi):
                out.add(tk)
                break
    return out


def coverage_report(pit: dict, changes: list) -> dict:
    """kill-switch 재료(docs/13 §3.1): 좌측절단 비율·구성원수 불변식·커버리지 창."""
    cur = [tk for tk, r in pit.items() if r["status"] == "current"]
    lc = [tk for tk, r in pit.items()
          if any(iv.get("left_censored") for iv in r["intervals"])]
    orphans = [tk for tk, r in pit.items()
               if any(iv.get("orphan") for iv in r["intervals"])]
    reasons: dict[str, int] = defaultdict(int)
    for r in pit.values():
        for iv in r["intervals"]:
            if iv.get("out_reason"):
                reasons[iv["out_reason"]] += 1
    anomalies = [tk for tk, r in pit.items()
                 for iv in r["intervals"]
                 if iv.get("in") and iv.get("out") and iv["out"] < iv["in"]]
    dts = sorted(ch["date"] for ch in changes)
    return {
        "n_total": len(pit),
        "n_current": len(cur),
        "n_removed": len(pit) - len(cur),
        "n_left_censored": len(lc),
        "left_censored_frac": round(len(lc) / max(len(pit), 1), 4),
        "n_orphan": len(orphans),
        "n_anomaly_out_before_in": len(anomalies),
        "changes_window": [dts[0], dts[-1]] if dts else None,
        "removal_reasons": dict(reasons),
    }


def _source_lineage_bar(crosscheck: dict | None) -> dict:
    """소스 2계보 바: 위키 oldid(1계보) + GitHub 교차검증(2계보) 모두 핀·최근 일치면 PASS."""
    if not crosscheck:
        return {"passed": False, "oldid_pinned": True, "github_crosscheck": False,
                "note": "위키 oldid 핀됨(1계보), GitHub 교차검증 미실행(2계보 필요)"}
    ok = bool(crosscheck.get("passed"))
    return {"passed": ok, "oldid_pinned": True, "github_crosscheck": True,
            "github_sha": crosscheck.get("github_sha"),
            "recent_min_jaccard": crosscheck.get("recent_min_jaccard"),
            "threshold": crosscheck.get("threshold"),
            "note": ("2계보(위키 oldid + GitHub SHA) 핀·최근 일치 통과" if ok else
                     "2계보 대조했으나 최근 일치가 임계 미달 — 데이터 불일치 조사 필요")}


def _fundamentals_bar(fund_cov: dict | None) -> dict:
    """PIT 재무 바: EDGAR as-first-reported 핵심(순이익·매출·자기자본) 커버리지 ≥ 임계면 PASS."""
    if not fund_cov:
        return {"passed": False, "status": "not_available",
                "note": "as-reported+보고일자 재무 미구축 → 종목 CMA look-ahead 리스크"}
    frac = fund_cov.get("core_coverage_frac_span_adjusted", 0.0)
    thr, n = 0.90, fund_cov.get("n_tickers")
    return {"passed": frac >= thr, "source": "edgar_xbrl", "core_coverage_frac": frac,
            "threshold": thr, "sample_n": n,
            "note": f"EDGAR as-first-reported 핵심 커버리지 {frac:.1%}(표본 {n}종 span-adjusted). "
                    "전 유니버스 풀·배당/자사주 확장은 후속."}


def _delisting_bar(dcov: dict | None) -> dict:
    """종료수익 바: 편출 종료수익 커버리지 ≥ 임계면 PASS. 근사면 is_approximation 각인(교체가능)."""
    if not dcov:
        return {"passed": False, "status": "not_available",
                "note": "편출 종료수익 미구축 → 백테스트 편향(−100% 일괄은 방향 오류)"}
    frac, thr = dcov.get("coverage_frac", 0.0), 0.90
    return {"passed": frac >= thr, "coverage_frac": frac, "threshold": thr,
            "is_approximation": dcov.get("is_approximation", True),
            "confidence_breakdown": dcov.get("confidence_breakdown"),
            "note": f"사유기반 근사(M&A=시장가청산·파산=총손실·리밸=계속거래) 커버리지 {frac:.0%}. "
                    "is_approximation=True → 실 종료수익으로 교체가능(저신뢰 우선)."}


def kill_switch_gate(pit: dict, changes: list, crosscheck: dict | None = None,
                     authoritative_counts: dict | None = None,
                     fundamentals_coverage: dict | None = None,
                     delisting_coverage: dict | None = None) -> dict:
    """docs/13 §3.1 kill-switch: 데이터 무결성 바를 평가해 '백테스트 가능' 여부 판정.

    통과 시 verdict='backtest_ok', 하나라도 미달이면 **'forward_only'로 격하**(백테스트 주장
    철회 = 게이트의 목적). 현재 바 2·3(상장폐지 종료수익·PIT 재무)은 데이터 미구축 → 정직하게
    미통과. 바 1(구성원수 불변식)·이상치·소스핀은 지금 평가.

    ``crosscheck``: 2계보 대조 결과. 주어지고 통과면 source_lineage 바 GREEN.
    ``authoritative_counts``: {date: 구성원수}. 주어지면(GitHub 권위 소스) 불변식을 **전 기간**
    으로 평가; 없으면 위키 재구성으로 최근(≥2015)만 평가.
    """
    grid = [f"{y}-12-31" for y in range(2006, 2026)]
    band = (485, 515)
    if authoritative_counts:  # GitHub 권위 소스 → 전 기간 불변식
        counts, count_src = authoritative_counts, "github_authoritative"
        check = counts
    else:  # 위키 재구성 → 최근만(과거 갭은 별도)
        counts, count_src = {d: len(members_asof(pit, d)) for d in grid}, "wiki_reconstruction"
        check = {d: c for d, c in counts.items() if d >= "2015-12-31"}
    bar1 = bool(check) and all(band[0] <= c <= band[1] for c in check.values())
    cov = coverage_report(pit, changes)
    bars = {
        "membership_count_invariant": {
            "passed": bar1, "band": band, "source": count_src,
            "note": ("GitHub 권위 소스 전 기간 ≈500" if authoritative_counts else
                     "위키 재구성 — 과거(<2015)는 커버리지 갭으로 미달 가능(GitHub 권위화로 해소)"),
            "all_counts": counts,
        },
        "interval_anomalies_out_before_in": {
            "passed": cov["n_anomaly_out_before_in"] == 0, "n": cov["n_anomaly_out_before_in"]},
        "left_censored": {  # 정보용(현행 0, 편출만) — 백테스트 배치 시 한계
            "frac": cov["left_censored_frac"], "n": cov["n_left_censored"],
            "note": "편출종목 편입일 미상 → 그 이전 배치 불가(생존편향 잔재)"},
        "delisting_return_coverage": _delisting_bar(delisting_coverage),
        "pit_fundamentals": _fundamentals_bar(fundamentals_coverage),
        "source_lineage": _source_lineage_bar(crosscheck),
    }
    hard = ("delisting_return_coverage", "pit_fundamentals", "source_lineage")
    all_pass = bars["membership_count_invariant"]["passed"] and \
        bars["interval_anomalies_out_before_in"]["passed"] and \
        all(bars[k]["passed"] for k in hard)
    # 통과 바 중 근사(교체가능)에 의존하면 provisional — 완전 backtest_ok와 구분(정직).
    approximated = bars["delisting_return_coverage"].get("is_approximation", False)
    if all_pass and approximated:
        verdict, reason = ("backtest_ok_provisional",
                           "전 바 통과·종료수익 근사(교체 시 backtest_ok)")
    elif all_pass:
        verdict, reason = "backtest_ok", "모든 바 통과(근사 없음)"
    else:
        verdict, reason = ("forward_only",
                           "미통과 바 존재 → 백테스트 주장 철회, forward-only 분석까지만 인정")
    return {"verdict": verdict, "reason": reason, "bars": bars}


def pull_membership_pit(pin: bool = True) -> dict:
    """위키 현행+변경 → PIT 리컨스트럭션·피닝. membership_version = hash(stocks, oldid)."""
    tables, source = _fetch()
    current = _parse_current(tables)
    changes = _parse_changes(tables)
    pit = reconstruct(current, changes)
    cov = coverage_report(pit, changes)
    gate = kill_switch_gate(pit, changes)
    # 재현성 핀: oldid 포함 해시(같은 위키 리비전 → 같은 version)
    ver = hashlib.sha256(
        json.dumps({"stocks": pit, "oldid": source["oldid"]}, sort_keys=True,
                   ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    out = {
        "membership_version": ver,
        "source": {"url": WIKI_URL, **source},
        "coverage": cov,
        "kill_switch": gate,
        "n": len(pit),
        "changes": changes,
        "stocks": pit,
    }
    if pin:
        MEMBERSHIP_DIR.mkdir(parents=True, exist_ok=True)
        PIT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def load_membership_pit() -> dict:
    """피닝된 PIT membership. 부재 시 빈 dict(오프라인 안전)."""
    if not PIT_PATH.exists():
        return {}
    return json.loads(PIT_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":  # 수동 검증: pull + 커버리지 리포트
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    res = pull_membership_pit(pin=True)
    print(f"membership_version = {res['membership_version']}  (oldid={res['source']['oldid']})")
    print("── 커버리지 ──")
    print(json.dumps(res["coverage"], ensure_ascii=False, indent=2))
    gate = res["kill_switch"]
    print(f"── kill-switch verdict: {gate['verdict']} — {gate['reason']} ──")
    print("  구성원수 불변식(연말 as-of):")
    for d, c in gate["bars"]["membership_count_invariant"]["all_counts"].items():
        flag = "" if 485 <= c <= 515 else "  ⚠️밴드밖"
        print(f"    {d}: {c}종{flag}")
    for k in ("delisting_return_coverage", "pit_fundamentals", "source_lineage"):
        b = gate["bars"][k]
        print(f"  [{'PASS' if b['passed'] else 'FAIL'}] {k}: {b['note']}")
