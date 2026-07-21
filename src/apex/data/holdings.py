"""ETF 보유종목 룩스루 (v2 E3) — yfinance top holdings → 핀.

ETF의 상위 보유종목(가중)을 수집해 KG 룩스루를 완성한다: ETF 포트 → 보유종목 → 세부테마/
테마군(graph.theme_exposure_lookthrough). **한계(docs/12 §10)**: top-N만(무료 소스,
커버리지<100%)·**현재 스냅샷**(20년 PIT 아님)·해외 보유(EFA/EEM)는 S&P500 membership
밖이라 테마 미매핑(통화·지역은 ETF 레벨 exposedTo로 이미 처리). 라이브는 pull에서만.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from apex.universe import CORE_SLOTS

HOLDINGS_DIR = Path("artifacts/holdings")


def pull_holdings(tickers: tuple[str, ...] = CORE_SLOTS, pin: bool = True) -> dict:
    """ETF 상위 보유종목(가중) 수집·피닝. 라이브 fetch(§3.1). 채권·금 ETF는 빈 dict."""
    from apex.data.netfix import ensure_ascii_ca

    ensure_ascii_ca()  # 비ASCII 경로 SSL 우회
    import yfinance as yf

    out: dict[str, dict[str, float]] = {}
    for t in tickers:
        try:
            th = yf.Ticker(t).funds_data.top_holdings
            out[t] = {
                str(i).upper().replace(".", "-"): round(float(th.loc[i, "Holding Percent"]), 6)
                for i in th.index
            }
        except Exception:  # noqa: BLE001 — 보유종목 없는 ETF(채권/금)·소싱 실패는 빈 dict
            out[t] = {}
    version = hashlib.sha256(json.dumps(out, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    payload = {"holdings_version": version, "holdings": out}
    if pin:
        HOLDINGS_DIR.mkdir(parents=True, exist_ok=True)
        (HOLDINGS_DIR / "holdings.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return payload


def load_holdings() -> dict:
    """피닝된 ETF 보유종목 {etf: {stock: weight}}. 부재 시 빈 dict(오프라인 안전)."""
    path = HOLDINGS_DIR / "holdings.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))["holdings"]
