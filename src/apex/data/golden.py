"""골든 대사 (v2 §3.1) — 독립 계보 레퍼런스 대조. 자기참조 탈출.

현 내부 대사(로컬 TR vs yfinance Adj Close)는 **같은 계보**(Yahoo/CSI)라 자기참조성이
있다(로컬을 로컬로 검증). 골든 대사는 **다른 데이터 계보**와 대조한다:
- 한국 069500(KODEX200): FinanceDataReader = **Naver/KRX → 진짜 독립**(Yahoo 무관).
- 미국 9종: FDR = 2nd-vendor(계보가 일부 겹칠 수 있어 독립성 약함). 발행사 공시 NAV가
  최강이나 엔드포인트가 취약(iShares HTML·SPDR zip) → 문서화, 향후 배선(docs/12 §10).

대조 지표 = **가격피드 일별수익률**(원 Close, 배당 무관·관례 자유) → 피드 오류를
직접 검출. 결과는 피닝(golden_version). 라이브 fetch는 `apex data golden`에서만(핀 우선).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

GOLDEN_DIR = Path("artifacts/golden")

# 우리 티커 → FDR 심볼
_FDR_SYMBOL: dict[str, str] = {
    "SPY": "SPY", "QQQ": "QQQ", "EFA": "EFA", "EEM": "EEM", "IEF": "IEF",
    "TLT": "TLT", "AGG": "AGG", "SHY": "SHY", "GLD": "GLD", "069500.KS": "069500",
}
# 계보 독립성(정직 고지)
_LINEAGE: dict[str, str] = {t: "2nd-vendor(FDR-US)" for t in _FDR_SYMBOL}
_LINEAGE["069500.KS"] = "independent(Naver/KRX)"


def _price_returns(px: pd.Series) -> pd.Series:
    """원 종가 → 일별 가격수익률(배당 무관·관례 자유). tz-naive 날짜 인덱스."""
    px = px.dropna()
    px = px[px > 0]
    idx = pd.DatetimeIndex(px.index)
    idx = (idx.tz_localize(None) if idx.tz is not None else idx).normalize()
    return pd.Series(px.to_numpy(dtype=float), index=idx).pct_change().dropna()


def _reference_returns(ticker: str, start: str, end: str | None) -> pd.Series:
    """독립 레퍼런스(FDR) 일별 가격수익률."""
    import FinanceDataReader as fdr

    df = fdr.DataReader(_FDR_SYMBOL[ticker], start, end)
    return _price_returns(df["Close"])


def _our_returns(ticker: str, start: str, end: str | None) -> pd.Series:
    """우리 피닝 스냅샷의 원 종가 → 일별 가격수익률."""
    from apex.data import snapshot

    df = snapshot.load_pinned(ticker)
    df = df[df.index >= pd.Timestamp(start)] if start else df
    df = df[df.index <= pd.Timestamp(end)] if end else df
    return _price_returns(df["Close"])


def reconcile_golden(
    ticker: str, start: str = "2010-01-01", end: str | None = None, tol_annual: float = 0.005
) -> dict:
    """우리 가격수익률 ↔ 독립 레퍼런스 대조. 반환: 편차·통과·계보.

    판정 = **연율 수익률 편차**(``ann_dev`` < tol_annual, 기본 50bp/년). ``max_daily_abs``는
    타임존·ex-date 단일일 잡음이라 참고만. 연율 편차가 커지면 독립 피드와 실질 괴리 = 조사 대상.
    """
    ours = _our_returns(ticker, start, end)
    ref = _reference_returns(ticker, start, end)
    common = ours.index.intersection(ref.index)
    o, r = ours.loc[common].to_numpy(), ref.loc[common].to_numpy()
    if len(common) < 20:
        return {"ticker": ticker, "n": len(common), "passed": False, "error": "overlap<20"}
    ann_ours = float((1 + o).prod() ** (252 / len(o)) - 1)
    ann_ref = float((1 + r).prod() ** (252 / len(r)) - 1)
    ann_dev = abs(ann_ours - ann_ref)
    return {
        "ticker": ticker,
        "lineage": _LINEAGE[ticker],
        "n": len(common),
        "max_daily_abs": round(float(np.abs(o - r).max()), 6),
        "ann_ours": round(ann_ours, 6),
        "ann_ref": round(ann_ref, 6),
        "ann_dev": round(ann_dev, 6),
        "passed": bool(ann_dev < tol_annual),
    }


def pull_golden(
    tickers: tuple[str, ...] = tuple(_FDR_SYMBOL), start: str = "2010-01-01", pin: bool = True
) -> dict:
    """전 티커 골든 대사 → 피닝(golden.json). 라이브 fetch(§3.1)."""
    import hashlib

    rows = []
    for t in tickers:
        try:
            rows.append(reconcile_golden(t, start))
        except Exception as e:  # noqa: BLE001 — 개별 실패는 대사 중단 아님
            rows.append({"ticker": t, "passed": False, "error": repr(e)[:80]})
    out = {"start": start, "rows": rows}
    out["golden_version"] = hashlib.sha256(
        json.dumps(rows, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    if pin:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        (GOLDEN_DIR / "golden.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return out


def load_golden() -> dict | None:
    """피닝된 골든 대사 결과. 부재 시 None."""
    path = GOLDEN_DIR / "golden.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
