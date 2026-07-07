#!/usr/bin/env python3
"""
S&P 500 N개년 합집합 유니버스 → 테마 분류 HTML 페이지 생성기.

docs/07-asset-classes.md §6(개별종목 테마 분류 체계)의 **인터랙티브 실측 뷰**.
최근 N년(기본 5년) 동안 S&P 500에 '한 번이라도 든' 모든 종목을 수집해
  1차 분할: 테마군(8) → 세부테마   (GICS Sub-Industry 크로스워크, §6.3)
  2차 오버레이: 메가트렌드 태그      (티커 집합, §6.5)
로 재분류한다. 크로스워크·태그의 정본은 07 문서이며 이 스크립트는 복제다(어긋나면 문서 우선).

합집합 = 현재 구성종목 ∪ 기간 내 편출 종목.
데이터 출처(D7 무료): Wikipedia 구성종목/변경이력 + (편출종목) yfinance 섹터 보강.

사용:
  python build_sp500_universe.py                 # 최근 5년, 테마 뷰
  python build_sp500_universe.py --years 3
  python build_sp500_universe.py --no-enrich     # 편출종목 yfinance 보강 생략
  python build_sp500_universe.py -o out.html
"""
from __future__ import annotations

import argparse
import html
import sys
from collections import defaultdict
from datetime import datetime
from io import StringIO

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ApexSP500UniverseBot/1.0)"}

# ── 07 §6.1 테마군(8) + 순서·라벨 ─────────────────────────────────────────────
THEME_ORDER = ["AI_HW", "SW_CLD", "FIN", "HLTH", "CONS", "COMM", "INDU", "REAL", "미분류"]
THEME_LABEL = {
    "AI_HW": "AI·반도체·하드웨어",
    "SW_CLD": "소프트웨어·클라우드·플랫폼",
    "FIN": "핀테크·결제·금융",
    "HLTH": "헬스케어·바이오",
    "CONS": "소비·리테일·브랜드",
    "COMM": "미디어·통신·엔터",
    "INDU": "산업·인프라·모빌리티",
    "REAL": "에너지·소재·유틸·부동산",
    "미분류": "미분류",
}

# ── 07 §6.2 세부테마 라벨 ────────────────────────────────────────────────────
SUBTHEME_LABEL = {
    "AI_HW.SEMI": "반도체·AI칩", "AI_HW.SEMIEQ": "반도체 장비/소재", "AI_HW.HW": "하드웨어·기기·부품",
    "AI_HW.NET": "네트워크장비", "AI_HW.DCI": "데이터센터·디지털인프라",
    "SW_CLD.SYS": "시스템/인프라 SW", "SW_CLD.APP": "애플리케이션 SW·SaaS",
    "SW_CLD.PLAT": "인터넷 플랫폼", "SW_CLD.SVC": "IT·데이터 서비스",
    "FIN.PAY": "디지털결제·핀테크", "FIN.EXCH": "거래소·금융데이터", "FIN.BANK": "은행",
    "FIN.CAP": "자산운용·IB·증권", "FIN.INS": "보험", "FIN.CONS": "소비자금융", "FIN.HOLD": "복합지주",
    "HLTH.PHARMA": "제약", "HLTH.BIO": "바이오테크", "HLTH.DEV": "의료기기·소모품",
    "HLTH.TOOLS": "생명과학 툴·진단", "HLTH.SVC": "헬스서비스·매니지드케어",
    "CONS.STAPLE": "필수소비·식음료·생활", "CONS.RETAIL": "리테일·유통",
    "CONS.BRAND": "브랜드·럭셔리·레저상품", "CONS.LEISURE": "여행·레저·외식·게이밍",
    "COMM.MEDIA": "미디어·엔터·방송·광고", "COMM.TELCO": "통신",
    "INDU.AERO": "항공·방산", "INDU.MACH": "기계·자동화·전기장비", "INDU.CONGLO": "복합산업",
    "INDU.TRANS": "운송·물류", "INDU.INFRA": "인프라·건설·건자재", "INDU.SVC": "기업·시설·인력서비스",
    "INDU.AUTO": "모빌리티·전기차",
    "REAL.OILGAS": "에너지(석유·가스)", "REAL.MAT": "소재·화학·포장", "REAL.METAL": "금속·광물·귀금속",
    "REAL.UTIL": "유틸리티·전력·물", "REAL.REIT": "리츠·부동산", "REAL.HOUSE": "주택·건설(주택)",
}

# ── 07 §6.3 GICS Sub-Industry → 세부테마 크로스워크 (정본 복제) ────────────────
# 각 세부테마에 속하는 GICS Sub-Industry 목록. 크로스섹터(⨯) 배정 포함.
_CROSSWALK_GROUPS = {
    "AI_HW.SEMI": ["Semiconductors"],
    "AI_HW.SEMIEQ": ["Semiconductor Materials & Equipment"],
    "AI_HW.HW": ["Technology Hardware Storage & Peripherals", "Electronic Components",
                 "Electronic Equipment & Instruments", "Electronic Manufacturing Services",
                 "Technology Distributors", "Consumer Electronics"],
    "AI_HW.NET": ["Communications Equipment"],
    "AI_HW.DCI": ["Internet Services & Infrastructure", "Data Center REITs", "Telecom Tower REITs"],
    "SW_CLD.SYS": ["Systems Software"],
    "SW_CLD.APP": ["Application Software"],
    "SW_CLD.PLAT": ["Interactive Media & Services"],
    "SW_CLD.SVC": ["IT Consulting & Other Services", "Data Processing & Outsourced Services"],
    "FIN.PAY": ["Transaction & Payment Processing Services"],
    "FIN.EXCH": ["Financial Exchanges & Data"],
    "FIN.BANK": ["Diversified Banks", "Regional Banks", "Commercial & Residential Mortgage Finance"],
    "FIN.CAP": ["Asset Management & Custody Banks", "Investment Banking & Brokerage",
                "Diversified Capital Markets", "Diversified Financial Services"],
    "FIN.INS": ["Life & Health Insurance", "Property & Casualty Insurance", "Multi-line Insurance",
                "Reinsurance", "Insurance Brokers"],
    "FIN.CONS": ["Consumer Finance"],
    "FIN.HOLD": ["Multi-Sector Holdings"],
    "HLTH.PHARMA": ["Pharmaceuticals"],
    "HLTH.BIO": ["Biotechnology"],
    "HLTH.DEV": ["Health Care Equipment", "Health Care Supplies"],
    "HLTH.TOOLS": ["Life Sciences Tools & Services"],
    "HLTH.SVC": ["Managed Health Care", "Health Care Services", "Health Care Facilities",
                 "Health Care Distributors", "Health Care Technology"],
    "CONS.STAPLE": ["Household Products", "Packaged Foods & Meats",
                    "Soft Drinks & Non-alcoholic Beverages", "Personal Care Products", "Brewers",
                    "Distillers & Vintners", "Tobacco", "Agricultural Products & Services",
                    "Food Distributors"],
    "CONS.RETAIL": ["Consumer Staples Merchandise Retail", "Food Retail", "Broadline Retail",
                    "Apparel Retail", "Automotive Retail", "Home Improvement Retail",
                    "Homefurnishing Retail", "Computer & Electronics Retail", "Other Specialty Retail",
                    "Distributors"],
    "CONS.BRAND": ["Apparel Accessories & Luxury Goods", "Footwear", "Leisure Products"],
    "CONS.LEISURE": ["Hotels Resorts & Cruise Lines", "Restaurants", "Casinos & Gaming",
                     "Specialized Consumer Services", "Leisure Facilities", "Education Services"],
    "COMM.MEDIA": ["Movies & Entertainment", "Broadcasting", "Cable & Satellite", "Publishing",
                   "Advertising", "Interactive Home Entertainment"],
    "COMM.TELCO": ["Integrated Telecommunication Services", "Wireless Telecommunication Services"],
    "INDU.AERO": ["Aerospace & Defense"],
    "INDU.MACH": ["Industrial Machinery & Supplies & Components",
                  "Construction Machinery & Heavy Transportation Equipment",
                  "Agricultural & Farm Machinery", "Electrical Components & Equipment",
                  "Heavy Electrical Equipment"],
    "INDU.CONGLO": ["Industrial Conglomerates"],
    "INDU.TRANS": ["Air Freight & Logistics", "Cargo Ground Transportation", "Rail Transportation",
                   "Passenger Airlines", "Passenger Ground Transportation", "Marine Transportation"],
    "INDU.INFRA": ["Construction & Engineering", "Building Products",
                   "Trading Companies & Distributors"],
    "INDU.SVC": ["Diversified Support Services", "Environmental & Facilities Services",
                 "Human Resource & Employment Services", "Research & Consulting Services",
                 "Commercial Printing", "Security & Alarm Services"],
    "INDU.AUTO": ["Automobile Manufacturers", "Automotive Parts & Equipment", "Tires & Rubber"],
    "REAL.OILGAS": ["Integrated Oil & Gas", "Oil & Gas Exploration & Production",
                    "Oil & Gas Equipment & Services", "Oil & Gas Refining & Marketing",
                    "Oil & Gas Storage & Transportation", "Coal & Consumable Fuels"],
    "REAL.MAT": ["Commodity Chemicals", "Specialty Chemicals", "Industrial Gases",
                 "Fertilizers & Agricultural Chemicals", "Construction Materials",
                 "Metal Glass & Plastic Containers", "Paper & Plastic Packaging Products & Materials",
                 "Diversified Chemicals", "Paper Products", "Forest Products"],
    "REAL.METAL": ["Steel", "Copper", "Gold", "Silver", "Aluminum",
                   "Precious Metals & Minerals", "Diversified Metals & Mining"],
    "REAL.UTIL": ["Electric Utilities", "Multi-Utilities", "Gas Utilities", "Water Utilities",
                  "Independent Power Producers & Energy Traders"],
    "REAL.REIT": ["Industrial REITs", "Retail REITs", "Health Care REITs",
                  "Multi-Family Residential REITs", "Office REITs", "Self-Storage REITs",
                  "Hotel & Resort REITs", "Single-Family Residential REITs",
                  "Other Specialized REITs", "Timber REITs", "Real Estate Services",
                  "Diversified REITs", "Real Estate Development", "Real Estate Operating Companies"],
    "REAL.HOUSE": ["Homebuilding"],
}


def _norm(s: str) -> str:
    """GICS 명칭 매칭용 정규화: 쉼표 제거 + 공백 정규화.
    (위키피디아는 'Apparel, Accessories & Luxury Goods'처럼 쉼표를 쓰지만
     07 §6.3은 쉼표를 생략 → 쉼표 무시로 양쪽을 일치시킨다.)"""
    return " ".join(str(s).replace(",", " ").split())


# 정규화된 Sub-Industry → 세부테마 코드
SUBIND_TO_SUBTHEME = {}
for _code, _subs in _CROSSWALK_GROUPS.items():
    for _s in _subs:
        SUBIND_TO_SUBTHEME[_norm(_s)] = _code

# ── 07 §6.5 메가트렌드 오버레이 태그 (티커 집합) ──────────────────────────────
OVERLAY = {
    "#AI": {"NVDA", "AVGO", "AMD", "MU", "MSFT", "GOOGL", "META", "ANET", "ORCL"},
    "#CYBER": {"PANW", "CRWD", "FTNT", "GEN"},
    "#CLOUD": {"MSFT", "AMZN", "GOOGL", "CRM", "NOW", "ADBE", "ORCL"},
    "#GLP1": {"LLY"},
    "#EV": {"TSLA", "GM", "F", "APTV", "ON"},
    "#CLEAN": {"NEE", "FSLR", "ENPH", "CEG", "VST", "GEV", "ETN"},
    "#DEFENSE": {"LMT", "RTX", "NOC", "GD", "LHX", "AXON"},
}
OVERLAY_ORDER = list(OVERLAY.keys())

# yfinance 섹터명 → GICS 섹터명 (편출종목 보강용)
YF_TO_GICS = {
    "Technology": "Information Technology", "Financial Services": "Financials",
    "Healthcare": "Health Care", "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples", "Industrials": "Industrials", "Energy": "Energy",
    "Basic Materials": "Materials", "Real Estate": "Real Estate", "Utilities": "Utilities",
    "Communication Services": "Communication Services",
}
# GICS 섹터 → 테마군 (Sub-Industry 매칭 실패/편출종목 폴백; §6.6)
SECTOR_TO_GROUP = {
    "Information Technology": "SW_CLD", "Communication Services": "COMM", "Financials": "FIN",
    "Health Care": "HLTH", "Consumer Discretionary": "CONS", "Consumer Staples": "CONS",
    "Industrials": "INDU", "Energy": "REAL", "Materials": "REAL", "Utilities": "REAL",
    "Real Estate": "REAL",
}


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
        df.columns = ["_".join(str(x) for x in col if "Unnamed" not in str(x)).strip("_")
                      for col in df.columns]
    else:
        df.columns = [str(c).strip() for c in df.columns]
    return df


def _find_col(df, *needles):
    for c in df.columns:
        low = c.lower()
        if all(n.lower() in low for n in needles):
            return c
    return None


def parse_current(tables):
    """현재 구성종목: {ticker: {name, sector, sub}}."""
    for t in tables:
        tt = _flatten_cols(t)
        sym = _find_col(tt, "symbol")
        sec = _find_col(tt, "gics", "sector")
        sub = _find_col(tt, "sub")           # GICS Sub-Industry
        nam = _find_col(tt, "security")
        if sym and sec:
            out = {}
            for _, row in tt.iterrows():
                ticker = str(row[sym]).strip().upper()
                if not ticker or ticker == "NAN":
                    continue
                out[ticker] = {
                    "name": str(row[nam]).strip() if nam else "",
                    "sector": str(row[sec]).strip(),
                    "sub": str(row[sub]).strip() if sub else "",
                }
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
    print("경고: 변경(changes) 표를 찾지 못했습니다. 편출 없이 진행.", file=sys.stderr)
    return {}


def classify_by_subindustry(sub: str, sector: str):
    """(group, subtheme, mapped). Sub-Industry 우선, 실패 시 섹터 폴백(*.기타)."""
    code = SUBIND_TO_SUBTHEME.get(_norm(sub))
    if code:
        return code.split(".")[0], code, True
    group = SECTOR_TO_GROUP.get(_norm(sector), "미분류")
    return group, f"{group}.기타", False


def enrich_removed(ticker: str):
    """편출종목: yfinance 섹터 → (group, subtheme). 실패 시 미분류."""
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info or {}
        yf_sec = info.get("sector")
        gics = YF_TO_GICS.get(yf_sec)
        if gics:
            group = SECTOR_TO_GROUP.get(gics, "미분류")
            return group, f"{group}.기타", gics
    except Exception:
        pass
    return "미분류", "미분류.기타", ""


def tags_for(ticker: str):
    return [t for t in OVERLAY_ORDER if ticker in OVERLAY[t]]


def build_records(current, removed, enrich):
    """레코드: {ticker,name,sector,sub,group,subtheme,tags,status,mapped}."""
    records, unmapped = [], set()
    for tk, meta in current.items():
        group, subtheme, mapped = classify_by_subindustry(meta["sub"], meta["sector"])
        if not mapped and meta["sub"]:
            unmapped.add(meta["sub"])
        records.append({"ticker": tk, "name": meta["name"], "sector": meta["sector"],
                        "sub": meta["sub"], "group": group, "subtheme": subtheme,
                        "tags": tags_for(tk), "status": "current", "mapped": mapped})
    cur = set(current)
    for tk, name in removed.items():
        if tk in cur:
            continue  # 재편입 → 현재로 취급
        if enrich:
            group, subtheme, gics = enrich_removed(tk)
        else:
            group, subtheme, gics = "미분류", "미분류.기타", ""
        records.append({"ticker": tk, "name": name, "sector": gics, "sub": "",
                        "group": group, "subtheme": subtheme, "tags": tags_for(tk),
                        "status": "removed", "mapped": False})
    return records, unmapped


def render_html(records, years, generated) -> str:
    def esc(s):
        return html.escape(str(s))

    # group → subtheme → rows
    tree = defaultdict(lambda: defaultdict(list))
    for r in records:
        tree[r["group"]][r["subtheme"]].append(r)

    total = len(records)
    n_cur = sum(1 for r in records if r["status"] == "current")
    n_rem = total - n_cur
    n_fallback = sum(1 for r in records if r["status"] == "current" and not r["mapped"])
    n_subtheme = sum(len(st) for st in tree.values())

    def gkey(g):
        return THEME_ORDER.index(g) if g in THEME_ORDER else len(THEME_ORDER)

    def stkey(code):
        return (code.endswith(".기타"), code)  # 기타는 뒤로

    def tag_badges(tags):
        return "".join(f'<span class="tag">{esc(t)}</span>' for t in tags)

    def row_html(r):
        status_badge = ('<span class="badge cur">현재</span>' if r["status"] == "current"
                        else '<span class="badge rem">편출</span>')
        return (
            f'      <tr data-status="{r["status"]}" data-tags="{esc(" ".join(r["tags"]))}">'
            f'<td class="tk">{esc(r["ticker"])}</td>'
            f'<td>{esc(r["name"])}</td>'
            f'<td class="dim">{esc(r["sector"])}</td>'
            f'<td class="dim">{esc(r["sub"])}</td>'
            f'<td>{tag_badges(r["tags"])}</td>'
            f"<td>{status_badge}</td></tr>"
        )

    groups_html = []
    for g in sorted(tree, key=gkey):
        subs = tree[g]
        g_rows = sum(len(v) for v in subs.values())
        g_cur = sum(1 for st in subs.values() for r in st if r["status"] == "current")
        sub_html = []
        for code in sorted(subs, key=stkey):
            rows = sorted(subs[code], key=lambda r: r["ticker"])
            label = SUBTHEME_LABEL.get(code, "기타 (섹터 폴백)")
            body = "\n".join(row_html(r) for r in rows)
            sub_html.append(f"""      <div class="subtheme" data-sub="{esc(code)}">
        <h3><code>{esc(code)}</code> {esc(label)} <span class="cnt">{len(rows)}</span></h3>
        <table><thead><tr><th>티커</th><th>기업명</th><th>GICS 섹터</th><th>GICS Sub-Industry</th><th>태그</th><th>상태</th></tr></thead>
        <tbody>
{body}
        </tbody></table>
      </div>""")
        groups_html.append(f"""    <details class="group" data-group="{esc(g)}" open>
      <summary><b>{esc(g)}</b> · {esc(THEME_LABEL.get(g, g))} <span class="cnt">{g_rows}종 · 현재 {g_cur} / 편출 {g_rows-g_cur}</span></summary>
{chr(10).join(sub_html)}
    </details>""")

    chips = "".join(
        f'<label class="chip"><input type="checkbox" value="{esc(t)}"> {esc(t)}</label>'
        for t in OVERLAY_ORDER
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>S&amp;P 500 최근 {years}개년 유니버스 — 테마 분류 (07 §6)</title>
<style>
  :root {{ --bg:#0f1115; --card:#181b22; --line:#2a2f3a; --fg:#e6e9ef; --muted:#8b93a7; --cur:#3fb950; --rem:#d29922; --tag:#7aa2f7; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 -apple-system,Segoe UI,Roboto,'Malgun Gothic',sans-serif; }}
  header {{ padding:22px 20px; border-bottom:1px solid var(--line); position:sticky; top:0; background:var(--bg); z-index:5; }}
  h1 {{ margin:0 0 6px; font-size:19px; }}
  .meta {{ color:var(--muted); font-size:13px; }}
  .stats {{ display:flex; gap:12px; margin-top:12px; flex-wrap:wrap; }}
  .stat {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:8px 13px; font-size:12px; color:var(--muted); }}
  .stat b {{ font-size:19px; color:var(--fg); }}
  .controls {{ margin-top:14px; display:flex; gap:14px; align-items:center; flex-wrap:wrap; }}
  #q {{ padding:9px 12px; border-radius:8px; border:1px solid var(--line); background:var(--card); color:var(--fg); font-size:14px; min-width:260px; }}
  .chips {{ display:flex; gap:6px; flex-wrap:wrap; }}
  .chip {{ font-size:12px; padding:5px 10px; border:1px solid var(--line); border-radius:20px; cursor:pointer; user-select:none; color:var(--tag); }}
  .chip input {{ margin-right:4px; vertical-align:middle; }}
  main {{ padding:18px; max-width:1080px; margin:0 auto; }}
  details.group {{ margin-bottom:14px; background:var(--card); border:1px solid var(--line); border-radius:12px; overflow:hidden; }}
  summary {{ padding:12px 16px; cursor:pointer; font-size:15px; }}
  summary .cnt {{ color:var(--muted); font-weight:400; font-size:12px; margin-left:8px; }}
  .subtheme {{ padding:4px 16px 14px; }}
  h3 {{ font-size:13px; margin:14px 0 6px; color:var(--fg); font-weight:600; }}
  h3 code {{ color:var(--tag); background:rgba(122,162,247,.1); padding:1px 6px; border-radius:5px; }}
  .cnt {{ color:var(--muted); font-weight:400; font-size:12px; margin-left:4px; }}
  table {{ width:100%; border-collapse:collapse; }}
  th,td {{ text-align:left; padding:6px 10px; border-bottom:1px solid var(--line); font-size:13px; vertical-align:top; }}
  th {{ color:var(--muted); font-weight:600; font-size:11px; text-transform:uppercase; letter-spacing:.03em; }}
  .tk {{ font-family:ui-monospace,Menlo,monospace; font-weight:600; white-space:nowrap; }}
  .dim {{ color:var(--muted); }}
  .tag {{ font-family:ui-monospace,Menlo,monospace; font-size:11px; color:var(--tag); background:rgba(122,162,247,.12); padding:1px 6px; border-radius:5px; margin-right:3px; }}
  .badge {{ font-size:11px; padding:2px 8px; border-radius:20px; font-weight:600; white-space:nowrap; }}
  .badge.cur {{ color:var(--cur); background:rgba(63,185,80,.12); }}
  .badge.rem {{ color:var(--rem); background:rgba(210,153,34,.12); }}
  .hidden {{ display:none !important; }}
</style>
</head>
<body>
<header>
  <h1>S&amp;P 500 최근 {years}개년 유니버스 — 테마 분류</h1>
  <div class="meta">07 §6 테마 분류 체계의 실측 뷰 · 테마군(8)→세부테마 + 메가트렌드 오버레이 · 생성 {esc(generated)} · 출처: Wikipedia GICS Sub-Industry + yfinance</div>
  <div class="stats">
    <div class="stat"><b>{total}</b> 총 종목(합집합)</div>
    <div class="stat"><b style="color:var(--cur)">{n_cur}</b> 현재</div>
    <div class="stat"><b style="color:var(--rem)">{n_rem}</b> 편출</div>
    <div class="stat"><b>{len([g for g in tree if g!='미분류'])}</b> 테마군</div>
    <div class="stat"><b>{n_subtheme}</b> 세부테마</div>
    <div class="stat"><b>{n_fallback}</b> 섹터폴백(미매칭)</div>
  </div>
  <div class="controls">
    <input id="q" type="search" placeholder="티커·기업명·Sub-Industry 검색…">
    <div class="chips">{chips}</div>
  </div>
</header>
<main>
{chr(10).join(groups_html)}
</main>
<script>
  const q = document.getElementById('q');
  const chips = [...document.querySelectorAll('.chip input')];
  function apply() {{
    const term = q.value.trim().toLowerCase();
    const sel = chips.filter(c => c.checked).map(c => c.value);
    document.querySelectorAll('details.group').forEach(g => {{
      let gShown = 0;
      g.querySelectorAll('.subtheme').forEach(st => {{
        let sShown = 0;
        st.querySelectorAll('tbody tr').forEach(tr => {{
          const hay = tr.textContent.toLowerCase();
          const rowTags = (tr.dataset.tags || '').split(' ').filter(Boolean);
          const okTerm = !term || hay.includes(term);
          const okTag = sel.length === 0 || sel.some(t => rowTags.includes(t));
          const hit = okTerm && okTag;
          tr.classList.toggle('hidden', !hit);
          if (hit) sShown++;
        }});
        st.classList.toggle('hidden', sShown === 0);
        gShown += sShown;
      }});
      g.classList.toggle('hidden', gShown === 0);
    }});
  }}
  q.addEventListener('input', apply);
  chips.forEach(c => c.addEventListener('change', apply));
</script>
</body>
</html>
"""


def main():
    import pandas as pd

    try:  # Windows 콘솔(cp949)에서 유니코드 출력 깨짐/크래시 방지
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="S&P 500 N개년 합집합 → 테마 분류 HTML (07 §6)")
    ap.add_argument("--years", type=int, default=20, help="합집합 기간(년), 기본 20(백테스트 정합)")
    ap.add_argument("-o", "--output", default="sp500_by_sector.html", help="출력 HTML 경로")
    ap.add_argument("--no-enrich", action="store_true", help="편출종목 yfinance 보강 생략")
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
        print("편출종목 테마군 보강(yfinance) 중…")
    records, unmapped = build_records(current, removed, enrich)
    print(f"합집합 총계: {len(records)}종")
    if unmapped:
        print(f"[!] 크로스워크 미매칭 Sub-Industry {len(unmapped)}종(섹터 폴백 처리) -> 07 §6.3 보강 후보:")
        for s in sorted(unmapped):
            print(f"    - {s}")

    out = render_html(records, args.years, now.strftime("%Y-%m-%d"))
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"완료 → {args.output}")


if __name__ == "__main__":
    main()
