"""S&P500 membership 2계보 교차검증 (v3-A Step 0 · docs/13 §3.1 kill-switch source_lineage 바).

위키 재구성(`membership_pit`)을 **독립 소스**(fja05680/sp500 GitHub 히스토리, 1996~현재
날짜별 전체 구성종목)와 as-of 대조한다. 골든 대사([10] §3.1) 정신을 membership으로 확장 —
단일 소스 자기참조를 탈출(패널 [High]). **양 소스를 리비전 핀**(위키 oldid + GitHub 커밋 SHA).

두 소스는 궁극 출처가 일부 겹칠 수 있어 완전 독립은 아니나, 방법론·수집이 달라 **불일치가
나오면 데이터 결함 신호**다. GitHub는 1996~ 완전 커버 → 위키 재구성의 과거 갭도 정량화한다.
"""
from __future__ import annotations

import json
import urllib.parse
from io import StringIO
from pathlib import Path

from apex.data import membership_pit as mp

MEMBERSHIP_DIR = Path("artifacts/membership")
GH_PATH = MEMBERSHIP_DIR / "github_constituents.json"

GH_REPO = "fja05680/sp500"
GH_FILE = "S&P 500 Historical Components & Changes (Updated).csv"
API_COMMITS = f"https://api.github.com/repos/{GH_REPO}/commits?per_page=1"
HEADERS = {"User-Agent": "ApexSP500PITBot/1.0"}


def _norm(t: str) -> str:
    return str(t).strip().upper().replace(".", "-")


def _latest_sha() -> str:
    import requests

    r = requests.get(API_COMMITS, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()[0]["sha"]


def pull_github_constituents(pin: bool = True) -> dict:
    """GitHub 히스토리 CSV(date,tickers) → 커밋 SHA로 핀·파싱. 라이브 fetch(핀 우선)."""
    import requests

    sha = _latest_sha()
    url = f"https://raw.githubusercontent.com/{GH_REPO}/{sha}/" + urllib.parse.quote(GH_FILE)
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    import csv

    rows = []
    for row in csv.DictReader(StringIO(r.text)):
        date = (row.get("date") or "").strip()
        tickers = [_norm(t) for t in (row.get("tickers") or "").split(",") if t.strip()]
        if date and tickers:
            rows.append({"date": date, "tickers": sorted(set(tickers))})
    rows.sort(key=lambda x: x["date"])
    out = {"source": {"repo": GH_REPO, "file": GH_FILE, "sha": sha, "url": url},
           "n_dates": len(rows), "rows": rows}
    if pin:
        MEMBERSHIP_DIR.mkdir(parents=True, exist_ok=True)
        GH_PATH.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def load_github_constituents() -> dict:
    if not GH_PATH.exists():
        return {}
    return json.loads(GH_PATH.read_text(encoding="utf-8"))


def members_asof(gh_rows: list, date: str) -> set[str]:
    """GitHub 소스의 as-of 구성원: date 이하 최신 행의 티커집합(계단 함수)."""
    latest: list | None = None
    for row in gh_rows:  # 날짜 오름차순
        if row["date"] <= date:
            latest = row["tickers"]
        else:
            break
    return set(latest) if latest else set()


def crosscheck(pit_stocks: dict, gh_rows: list, grid: list[str] | None = None,
               threshold: float = 0.97) -> dict:
    """위키 재구성 vs GitHub as-of 대조. per-date Jaccard + 최근(≥2015) 통과 여부.

    최근 창에서 min Jaccard ≥ threshold면 source_lineage 바 PASS. 과거 갭(위키 미커버)은
    ``mine_missing``으로 정량화(구성원수 불변식 바가 이미 신호하는 것과 정합).
    """
    if grid is None:
        grid = [f"{y}-12-31" for y in range(2006, 2026)]
    per_date = {}
    for d in grid:
        mine = mp.members_asof(pit_stocks, d)
        theirs = members_asof(gh_rows, d)
        if not theirs:
            continue
        inter, union = mine & theirs, mine | theirs
        per_date[d] = {
            "jaccard": round(len(inter) / len(union), 4) if union else 1.0,
            "n_mine": len(mine), "n_github": len(theirs),
            "mine_missing": len(theirs - mine),   # GitHub엔 있는데 위키 재구성엔 없음(과거 갭)
            "mine_extra": len(mine - theirs),      # 위키엔 있는데 GitHub엔 없음(불일치·조사)
            "extra_sample": sorted(mine - theirs)[:8],
        }
    # 최근 3년(양 소스 모두 신뢰 구간)에서 일치 평가. 과거 불일치는 위키 커버리지 갭
    # (GitHub 권위화로 해소되므로 lineage 바에는 미반영).
    recent3 = sorted(per_date)[-3:]
    recent_min = min((per_date[d]["jaccard"] for d in recent3), default=0.0)
    return {
        "passed": recent_min >= threshold,
        "threshold": threshold,
        "recent_min_jaccard": round(recent_min, 4),
        "recent_window": recent3,
        "github_sha": None,  # run에서 채움
        "per_date": per_date,
    }


def authoritative_counts(gh_rows: list, grid: list[str] | None = None) -> dict:
    """GitHub 권위 소스의 as-of 구성원수(전 기간 구성원수 불변식용)."""
    if grid is None:
        grid = [f"{y}-12-31" for y in range(2006, 2026)]
    return {d: len(members_asof(gh_rows, d)) for d in grid}


def run_crosscheck(pin: bool = True) -> dict:
    """전체 흐름: pit + GitHub 로드/풀 → 대조 → kill-switch 재평가. 핀된 pit 우선."""
    pit_doc = mp.load_membership_pit() or mp.pull_membership_pit(pin=pin)
    gh_doc = load_github_constituents() or pull_github_constituents(pin=pin)
    cc = crosscheck(pit_doc["stocks"], gh_doc["rows"])
    cc["github_sha"] = gh_doc["source"]["sha"]
    auth = authoritative_counts(gh_doc["rows"])  # GitHub 권위 소스 전 기간 카운트
    fund = None  # EDGAR PIT 재무 커버리지(핀 존재 시 로드, 재풀 안 함)
    fpath = MEMBERSHIP_DIR.parent / "fundamentals" / "coverage_sample.json"
    if fpath.exists():
        fund = json.loads(fpath.read_text(encoding="utf-8"))
    delist = None  # 편출 종료수익 근사 커버리지(핀 존재 시 로드)
    dpath = MEMBERSHIP_DIR.parent / "delisting" / "returns.json"
    if dpath.exists():
        delist = json.loads(dpath.read_text(encoding="utf-8")).get("coverage")
    gate = mp.kill_switch_gate(pit_doc["stocks"], pit_doc.get("changes", []),
                               crosscheck=cc, authoritative_counts=auth,
                               fundamentals_coverage=fund, delisting_coverage=delist)
    return {"crosscheck": cc, "kill_switch": gate,
            "wiki_oldid": pit_doc["source"]["oldid"], "github_sha": gh_doc["source"]["sha"]}


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    res = run_crosscheck(pin=True)
    cc, gate = res["crosscheck"], res["kill_switch"]
    print(f"2계보 핀: wiki oldid={res['wiki_oldid']}  github sha={res['github_sha'][:12]}")
    print(f"── kill-switch verdict: {gate['verdict']} ──")
    for k, b in gate["bars"].items():
        mark = "ℹ️INFO " if "passed" not in b else ("🟢PASS" if b["passed"] else "🔴FAIL")
        extra = ""
        if k == "membership_count_invariant":
            extra = f" (source={b['source']})"
        elif k == "source_lineage":
            extra = f" (recent3 min Jaccard={cc['recent_min_jaccard']}, 임계={cc['threshold']})"
        print(f"  {mark}  {k}{extra}")
    print("── GitHub 권위 구성원수(연말, 전 기간 ≈500) ──")
    cnt = gate["bars"]["membership_count_invariant"]["all_counts"]
    print("  " + "  ".join(f"{d[:4]}:{c}" for d, c in list(cnt.items())[::4]))
    print("── 위키↔GitHub 최근 일치 ──")
    for d in cc["recent_window"]:
        v = cc["per_date"][d]
        print(f"  {d}: Jaccard={v['jaccard']:.3f} "
              f"(위키초과={v['mine_extra']}, 누락={v['mine_missing']})")
