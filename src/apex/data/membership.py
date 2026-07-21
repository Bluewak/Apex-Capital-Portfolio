"""개별종목 KG 소속 (v2 E1) — S&P500 종목 → 세부테마/테마군 (07 §6 크로스워크).

sp500 도구의 GICS→세부테마 **정본 크로스워크**를 재사용해 위키 현행 구성종목을 분류·피닝.
graph.py가 이걸 로드해 **종목 → 세부테마 → 테마군 → 주식(자산군)** 으로 KG에 연결한다.
개별종목이 KG에 실제로 매달리는 첫 단계(v3 종목 CMA·최적화의 데이터 토대).

라이브 fetch(위키)는 `apex data membership`에서만(핀 우선). 편출 353종·ETF 보유종목
룩스루는 후속(docs/12 §9·§10). 결정론: 도구 크로스워크는 고정, 위키 스냅샷만 갱신.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

MEMBERSHIP_DIR = Path("artifacts/membership")
_TOOL = Path(__file__).resolve().parents[3] / "tools" / "sp500" / "build_sp500_universe.py"


def _load_tool():
    """sp500 도구를 모듈로 로드(크로스워크·분류·fetch 재사용). main은 __main__ 가드로 안전."""
    spec = importlib.util.spec_from_file_location("_sp500tool", _TOOL)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def pull_membership(pin: bool = True) -> dict:
    """위키 현행 S&P500 → 종목별 (세부테마·테마군) 분류·피닝. 라이브 fetch(§3.1)."""
    m = _load_tool()
    df = m._flatten_cols(m.fetch_tables(m.WIKI_URL)[0])
    c_sym = m._find_col(df, "symbol") or m._find_col(df, "ticker")
    c_sec = m._find_col(df, "gics", "sector") or m._find_col(df, "sector")
    c_sub = m._find_col(df, "sub", "industry")
    stocks: dict[str, dict] = {}
    for _, row in df.iterrows():
        tk = str(row[c_sym]).strip().upper().replace(".", "-")
        sub_ind, sector = str(row[c_sub]), str(row[c_sec])
        group, subtheme, mapped = m.classify_by_subindustry(sub_ind, sector)
        stocks[tk] = {
            "gics_sub": sub_ind, "sector": sector,
            "subtheme": subtheme, "theme_group": group, "mapped": bool(mapped),
        }
    version = hashlib.sha256(json.dumps(stocks, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    out = {"n": len(stocks), "membership_version": version, "stocks": stocks}
    if pin:
        MEMBERSHIP_DIR.mkdir(parents=True, exist_ok=True)
        (MEMBERSHIP_DIR / "stocks.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return out


def load_membership() -> dict:
    """피닝된 종목 소속 {ticker: {...}}. 부재 시 빈 dict(오프라인 안전)."""
    path = MEMBERSHIP_DIR / "stocks.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))["stocks"]
