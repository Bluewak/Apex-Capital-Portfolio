"""실 raw 스냅샷 수집 + content-hash 피닝 + 대사 (08 §3 M4·M4.5).

`auto_adjust=False`로 raw(unadjusted OHLCV + Dividends/Splits/Capital Gains)를 받아
정규화 바이트에 content-hash(=data_version 구성요소)를 건다. 조정종가는 저장하지 않고
로컬 TR 엔진(adjust.py)으로 재계산 — yfinance 소급조정 회피(R3).
대사는 착수 1회 레퍼런스(Adj Close)와 로컬 TR을 비교(오라클).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from apex.data.adjust import ReconResult, local_tr_returns, reconcile, returns_from_adjclose
from apex.universe import BENCHMARKS, CORE_SLOTS

RAW_COLS = ("Open", "High", "Low", "Close", "Volume", "Dividends", "Stock Splits")
ARTIFACTS = Path("artifacts/snapshots")


def fetch_raw(ticker: str, start: str = "2005-01-01", end: str | None = None) -> pd.DataFrame:
    """raw OHLCV + 이벤트 (auto_adjust=False). Adj Close는 대사 레퍼런스용으로만."""
    import yfinance as yf

    df = yf.Ticker(ticker).history(
        start=start, end=end, auto_adjust=False, actions=True, raise_errors=False
    )
    return df


def content_hash(df: pd.DataFrame) -> str:
    """raw 스냅샷 정규화 바이트의 SHA256 (조정종가 제외 — 소급 변형 회피)."""
    cols = [c for c in RAW_COLS if c in df.columns]
    raw = df[cols].copy()
    raw.index = raw.index.map(lambda ts: ts.strftime("%Y-%m-%d"))
    buf = raw.round(6).to_csv(float_format="%.6f")
    return hashlib.sha256(buf.encode("utf-8")).hexdigest()


def _col(df: pd.DataFrame, name: str) -> np.ndarray | None:
    if name not in df.columns:
        return None
    return df[name].fillna(0.0).to_numpy(dtype=float)


def reconcile_ticker(df: pd.DataFrame, tol_annual: float = 0.0020) -> ReconResult:
    """로컬 TR(raw에서 재계산) ↔ 레퍼런스(Adj Close) 대사.

    NaN/0 종가 행 정리(휴장·결측). yfinance Close는 분할조정이므로 splits 재적용 안 함.
    """
    df = df.dropna(subset=["Close", "Adj Close"])
    df = df[(df["Close"] > 0) & (df["Adj Close"] > 0)]
    close = df["Close"].to_numpy(dtype=float)
    div = _col(df, "Dividends")
    capg = _col(df, "Capital Gains")
    local = local_tr_returns(
        close,
        np.zeros(len(close)) if div is None else div,
        np.zeros(len(close)),  # splits 재적용 안 함(Close 분할조정 전제)
        capg,
    )
    ref = returns_from_adjclose(df["Adj Close"].to_numpy(dtype=float))
    return reconcile(local, ref, tol_annual=tol_annual)


def pull(
    tickers: tuple[str, ...] = CORE_SLOTS + BENCHMARKS,
    start: str = "2005-01-01",
    end: str | None = None,
    tol_annual: float = 0.0020,
    pin: bool = True,
) -> dict[str, dict]:
    """전 티커 수집·대사·피닝. 반환: {ticker: {rows, hash, recon}}. M4.5 DoD = 전원 대사 통과."""
    results: dict[str, dict] = {}
    manifest: dict[str, str] = {}
    if pin:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
    for t in tickers:
        df = fetch_raw(t, start, end)
        if df is None or df.empty:
            results[t] = {"rows": 0, "hash": None, "recon": None, "error": "empty"}
            continue
        h = content_hash(df)
        recon = reconcile_ticker(df, tol_annual)
        results[t] = {"rows": len(df), "hash": h, "recon": recon}
        manifest[t] = h
        if pin:
            cols = [c for c in RAW_COLS if c in df.columns]
            df[cols].to_csv(ARTIFACTS / f"{t.replace('.', '_')}.csv", float_format="%.6f")
    if pin and manifest:
        data_version = hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        (ARTIFACTS / "manifest.json").write_text(
            json.dumps({"data_version": data_version, "tickers": manifest}, indent=2),
            encoding="utf-8",
        )
    return results
