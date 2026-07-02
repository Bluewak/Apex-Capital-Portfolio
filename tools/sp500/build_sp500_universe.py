#!/usr/bin/env python3
"""
S&P 500 N개년 합집합 유니버스 → 섹터별 HTML 페이지 생성기.

최근 N년(기본 5년) 동안 S&P 500에 '한 번이라도 든' 모든 종목을 수집한다.
  합집합 = 현재 구성종목  ∪  기간 내 편출(removed)된 종목

데이터 소스 (D7: 무료):
  - Wikipedia "List of S&P 500 companies"
      · 현재 구성종목 표 (Symbol, Security, GICS Sector, Sub-Industry, Date added)
      · "Selected changes to the list of S&P 500 components" 표 (Date, Added, Removed, Reason)
  - (선택) yfinance: 편출 종목의 섹터 보강. 없으면 '미분류(편출)'로 표기.

출력: 섹터별로 묶은 단일 HTML 파일 (검색·상태 배지 포함, 오프라인 열람 가능).

사용:
  python build_sp500_universe.py                 # 최근 5년, 기본 출력 파일
  python build_sp500_universe.py --years 3       # 최근 3년
  python build_sp500_universe.py --no-enrich     # yfinance 섹터 보강 생략(빠름)
  python build_sp500_universe.py -o out.html
"""
from __future__ import annotations

import argparse
import html
import sys
from datetime import datetime
from io import StringIO

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ApexSP500UniverseBot/1.0)"}

# yfinance 섹터명 → Wikipedia GICS 섹터명 정합 매핑
YF_TO_GICS = {
    "Technology": "Information Technology",
    "Financial Services": "Financials",
    "Healthcare": "Health Care",
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Industrials": "Industrials",
    "Energy": "Energy",
    "Basic Materials": "Materials",
    "Real Estate": "Real Estate",
    "Utilities": "Utilities",
    "Communication Services": "Communication Services",
}
REMOVED_UNKNOWN = "미분류 (편출)"


def fetch_tables(url: str):
    import pandas as pd
    import requests

    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return pd.read_html(StringIO(resp.text))


def _flatten_cols(df):
    import pandas as pd

    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = [
            "_".join(str(x) for x in col if "Unnamed" not in str(x)).strip("_")
            for col in df.columns
        ]
    else:
        df.columns = [str(c).strip() for c in df.columns]
    return df


def _find_col(df, *needles):
    """컬럼명에 needles가 (순서대로) 모두 들어가는 첫 컬럼 반환."""
    for c in df.columns:
        low = c.lower()
        if all(n.lower() in low for n in needles):
            return c
    return None


def parse_current(tables):
    """현재 구성종목: {ticker: (name, gics_sector)}."""
    for t in tables:
        tt = _flatten_cols(t)
        sym = _find_col(tt, "symbol")
        sec = _find_col(tt, "gics", "sector")
        nam = _find_col(tt, "security")
        if sym and sec:
            out = {}
            for _, row in tt.iterrows():
                ticker = str(row[sym]).strip().upper()
                if not ticker or ticker == "NAN":
                    continue
                out[ticker] = (
                    str(row[nam]).strip() if nam else "",
                    str(row[sec]).strip(),
                )
            if out:
                return out
    raise RuntimeError("현재 구성종목 표를 찾지 못했습니다 (위키 구조 변경 가능).")


def parse_removed(tables, cutoff):
    """기간 내 편출 종목: {ticker: name}. cutoff 이후 removed만."""
    import pandas as pd

    for t in tables:
        tt = _flatten_cols(t)
        rem_tk = _find_col(tt, "removed", "ticker")
        date_c = _find_col(tt, "date")
        if not (rem_tk and date_c):
            continue
        rem_nm = _find_col(tt, "removed", "security")
        removed = {}
        dates = pd.to_datetime(tt[date_c], errors="coerce")
        for i, (_, row) in enumerate(tt.iterrows()):
            d = dates.iloc[i]
            if pd.isna(d) or d < cutoff:
                continue
            ticker = str(row[rem_tk]).strip().upper()
            if not ticker or ticker == "NAN":
                continue
            removed[ticker] = str(row[rem_nm]).strip() if rem_nm else ""
        return removed
    # 변경 표를 못 찾으면 편출 없음으로 간주(현재 구성종목만).
    print("경고: 변경(changes) 표를 찾지 못했습니다. 편출 종목 없이 진행합니다.", file=sys.stderr)
    return {}


def enrich_removed_sector(ticker: str) -> str:
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info or {}
        s = info.get("sector")
        return YF_TO_GICS.get(s, s) if s else REMOVED_UNKNOWN
    except Exception:
        return REMOVED_UNKNOWN


def build_records(current, removed, enrich: bool):
    """합집합 레코드 리스트: {ticker, name, sector, status}."""
    records = []
    for tk, (name, sector) in current.items():
        records.append({"ticker": tk, "name": name, "sector": sector, "status": "current"})
    cur_set = set(current)
    for tk, name in removed.items():
        if tk in cur_set:
            continue  # 편출됐다가 재편입 → 현재로 취급
        sector = enrich_removed_sector(tk) if enrich else REMOVED_UNKNOWN
        records.append({"ticker": tk, "name": name, "sector": sector, "status": "removed"})
    return records


def render_html(records, years, generated) -> str:
    from collections import defaultdict

    by_sector = defaultdict(list)
    for r in records:
        by_sector[r["sector"] or REMOVED_UNKNOWN].append(r)

    total = len(records)
    n_cur = sum(1 for r in records if r["status"] == "current")
    n_rem = total - n_cur

    def esc(s):
        return html.escape(str(s))

    # '미분류(편출)'은 항상 맨 끝으로 정렬
    def sector_key(name):
        return (name == REMOVED_UNKNOWN, name)

    sections = []
    for sector in sorted(by_sector, key=sector_key):
        rows = sorted(by_sector[sector], key=lambda r: r["ticker"])
        cur_c = sum(1 for r in rows if r["status"] == "current")
        row_html = "\n".join(
            f'      <tr data-status="{r["status"]}">'
            f'<td class="tk">{esc(r["ticker"])}</td>'
            f'<td>{esc(r["name"])}</td>'
            f'<td>{"<span class=\'badge cur\'>현재</span>" if r["status"]=="current" else "<span class=\'badge rem\'>편출</span>"}</td>'
            f"</tr>"
            for r in rows
        )
        sections.append(f"""    <section class="sector" data-sector="{esc(sector)}">
      <h2>{esc(sector)} <span class="cnt">{len(rows)}종 · 현재 {cur_c} / 편출 {len(rows)-cur_c}</span></h2>
      <table>
        <thead><tr><th>티커</th><th>기업명</th><th>상태</th></tr></thead>
        <tbody>
{row_html}
        </tbody>
      </table>
    </section>""")

    sections_html = "\n".join(sections)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>S&amp;P 500 최근 {years}개년 유니버스 (섹터별)</title>
<style>
  :root {{ --bg:#0f1115; --card:#181b22; --line:#2a2f3a; --fg:#e6e9ef; --muted:#8b93a7; --cur:#3fb950; --rem:#d29922; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 -apple-system,Segoe UI,Roboto,'Malgun Gothic',sans-serif; }}
  header {{ padding:24px 20px; border-bottom:1px solid var(--line); position:sticky; top:0; background:var(--bg); z-index:5; }}
  h1 {{ margin:0 0 6px; font-size:20px; }}
  .meta {{ color:var(--muted); font-size:13px; }}
  .stats {{ display:flex; gap:16px; margin-top:12px; flex-wrap:wrap; }}
  .stat {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:10px 14px; }}
  .stat b {{ font-size:20px; }}
  #q {{ margin-top:14px; width:100%; max-width:420px; padding:9px 12px; border-radius:8px; border:1px solid var(--line); background:var(--card); color:var(--fg); font-size:14px; }}
  main {{ padding:20px; max-width:1000px; margin:0 auto; }}
  .sector {{ margin-bottom:28px; }}
  h2 {{ font-size:16px; border-left:3px solid var(--cur); padding-left:10px; margin:0 0 10px; }}
  .cnt {{ color:var(--muted); font-weight:400; font-size:12px; margin-left:6px; }}
  table {{ width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
  th,td {{ text-align:left; padding:8px 12px; border-bottom:1px solid var(--line); font-size:14px; }}
  th {{ color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.03em; }}
  tr:last-child td {{ border-bottom:0; }}
  .tk {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-weight:600; }}
  .badge {{ font-size:11px; padding:2px 8px; border-radius:20px; font-weight:600; }}
  .badge.cur {{ color:var(--cur); background:rgba(63,185,80,.12); }}
  .badge.rem {{ color:var(--rem); background:rgba(210,153,34,.12); }}
  .hidden {{ display:none !important; }}
</style>
</head>
<body>
<header>
  <h1>S&amp;P 500 최근 {years}개년 유니버스 — 섹터별</h1>
  <div class="meta">기간 내 한 번이라도 편입된 모든 종목의 합집합 · 생성 {esc(generated)} · 출처: Wikipedia (GICS 섹터)</div>
  <div class="stats">
    <div class="stat"><b>{total}</b><br>총 종목(합집합)</div>
    <div class="stat"><b style="color:var(--cur)">{n_cur}</b><br>현재 구성</div>
    <div class="stat"><b style="color:var(--rem)">{n_rem}</b><br>기간 내 편출</div>
    <div class="stat"><b>{len(by_sector)}</b><br>섹터 수</div>
  </div>
  <input id="q" type="search" placeholder="티커·기업명·섹터 검색…">
</header>
<main>
{sections_html}
</main>
<script>
  const q = document.getElementById('q');
  q.addEventListener('input', () => {{
    const term = q.value.trim().toLowerCase();
    document.querySelectorAll('section.sector').forEach(sec => {{
      let shown = 0;
      const secName = sec.dataset.sector.toLowerCase();
      sec.querySelectorAll('tbody tr').forEach(tr => {{
        const hay = (tr.textContent + ' ' + secName).toLowerCase();
        const hit = !term || hay.includes(term);
        tr.classList.toggle('hidden', !hit);
        if (hit) shown++;
      }});
      sec.classList.toggle('hidden', shown === 0);
    }});
  }});
</script>
</body>
</html>
"""


def main():
    import pandas as pd

    ap = argparse.ArgumentParser(description="S&P 500 N개년 합집합 → 섹터별 HTML 생성")
    ap.add_argument("--years", type=int, default=5, help="합집합 기간(년), 기본 5")
    ap.add_argument("-o", "--output", default="sp500_by_sector.html", help="출력 HTML 경로")
    ap.add_argument("--no-enrich", action="store_true", help="yfinance 섹터 보강 생략")
    args = ap.parse_args()

    now = pd.Timestamp(datetime.now().date())
    cutoff = now - pd.DateOffset(years=args.years)
    print(f"기간: {cutoff.date()} ~ {now.date()} (최근 {args.years}년)")

    tables = fetch_tables(WIKI_URL)
    current = parse_current(tables)
    print(f"현재 구성종목: {len(current)}종")
    removed = parse_removed(tables, cutoff)
    print(f"기간 내 편출: {len(removed)}종")

    enrich = not args.no_enrich
    if enrich:
        print("편출 종목 섹터 보강(yfinance) 중… (실패 시 '미분류(편출)')")
    records = build_records(current, removed, enrich)
    print(f"합집합 총계: {len(records)}종")

    out = render_html(records, args.years, now.strftime("%Y-%m-%d"))
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"완료 → {args.output}")


if __name__ == "__main__":
    main()
