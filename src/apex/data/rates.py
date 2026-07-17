"""무위험금리·환율 실소싱 (v2 §3.1) — FRED 수집·피닝. 하드코딩 rf 제거.

`apex data rates`가 FRED에서 USD 3M(DGS3MO)·Korea 3M 은행간(IR3TIB01KRM156N)·
원/달러(DEXKOUS)를 수집해 `artifacts/rates/`에 피닝한다. Sharpe 무위험은 **통화별**
(05 §3·08 §6). 핀 부재 시 문서화 기본값으로 폴백(오프라인 안전) — 라이브는 pull에서만.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

RATES_DIR = Path("artifacts/rates")
_FRED_SERIES = {
    "usd_rf": "DGS3MO",  # 미 3개월 T-bill(%)
    "krw_rf": "IR3TIB01KRM156N",  # 한국 3개월 은행간 금리(%)
    "fx_krwusd": "DEXKOUS",  # 원/달러
}
# 문서화 기본값(핀 부재 시 폴백). 08 §3·§6 근사, pull로 실측 대체.
_DEFAULTS = {"usd_rf": 0.02, "krw_rf": 0.025, "fx_krwusd": 1330.0, "rates_version": "default"}


def pull_rates(start: str = "2005-01-01", end: str | None = None, pin: bool = True) -> dict:
    """FRED에서 금리·환율 수집 → 기간 평균 rf + 최신 FX. 피닝(rates_version 해시)."""
    import pandas_datareader.data as web

    df = web.DataReader(list(_FRED_SERIES.values()), "fred", start, end)
    out: dict[str, float | str] = {}
    for key, series in _FRED_SERIES.items():
        s = df[series].dropna()
        if key == "fx_krwusd":
            out[key] = round(float(s.iloc[-1]), 4)  # 최신 환율
        else:
            out[key] = round(float(s.mean()) / 100.0, 6)  # 기간 평균 rf(연율, %→소수)
    out["rates_version"] = hashlib.sha256(
        json.dumps(out, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    out["period"] = [str(df.index[0].date()), str(df.index[-1].date())]
    if pin:
        RATES_DIR.mkdir(parents=True, exist_ok=True)
        (RATES_DIR / "rates.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return out


def load_pinned_rates() -> dict:
    """피닝된 금리·환율 로드. 핀 부재 시 문서화 기본값(오프라인 안전, §3.1)."""
    path = RATES_DIR / "rates.json"
    if not path.exists():
        return dict(_DEFAULTS)
    return json.loads(path.read_text(encoding="utf-8"))
