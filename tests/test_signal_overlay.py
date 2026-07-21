"""신호 오버레이 (v3-B) — OFF 항등성·틸트·뷰검증 게이트·해시 분리. 네트워크 없음."""
from __future__ import annotations

from apex import signal_overlay, stock_optimizer
from apex.schemas import CMASet
from apex.schemas.enums import Profile


def _cma(n=8):
    tickers = [f"S{i}" for i in range(n)]
    mu = {t: 0.06 + 0.01 * i for i, t in enumerate(tickers)}
    vol = [0.15 + 0.01 * i for i in range(n)]
    cov = [[(0.3 if i != j else 1.0) * vol[i] * vol[j] for j in range(n)] for i in range(n)]
    return CMASet(tickers=tickers, mu=mu, vol={t: vol[i] for i, t in enumerate(tickers)},
                  cov=cov, shrinkage=0.1, as_of="2026-07-20", data_version="dv",
                  cma_version="scma-test")


def test_overlay_off_equals_step2_basket():
    """신호 없으면 Step 2 결정론 바스켓과 정확 일치(OFF 항등성)."""
    cma = _cma()
    base = stock_optimizer.optimize(cma, Profile.GROWTH, single_stock_cap=0.25)
    off = signal_overlay.apply(cma, Profile.GROWTH, {}, single_stock_cap=0.25)
    assert off["weights"] == base
    assert off["overlay_active"] is False


def test_signal_tilts_weights():
    """보유 종목에 강신호 → 비중 변화(결정론)."""
    cma = _cma()
    base = stock_optimizer.optimize(cma, Profile.GROWTH, single_stock_cap=0.25)
    top = max(base, key=base.get)
    on = signal_overlay.apply(cma, Profile.GROWTH, {top: "strong_neg"}, single_stock_cap=0.25)
    assert on["overlay_active"] is True
    assert on["weights"] != base                       # 틸트가 비중을 바꿈
    assert on["weights"].get(top, 0) <= base[top] + 1e-9  # 강매도 → 비중 비증가


def test_view_gate_drops_unknown_and_invalid():
    cma = _cma()
    r = signal_overlay.apply(cma, Profile.NEUTRAL, {"NOPE": "pos", "S1": "boom", "S2": "neg"},
                             single_stock_cap=0.25)
    assert list(r["signals_applied"]) == ["S2"]
    reasons = {x.get("ticker"): x["reason"] for x in r["rejected"]}
    assert reasons == {"NOPE": "unknown_ticker", "S1": "invalid_signal"}


def test_hash_separation_basket_invariant_overlay_varies():
    cma = _cma()
    h0 = signal_overlay.basket_and_overlay_hash(cma, Profile.GROWTH, {}, single_stock_cap=0.25)
    h1 = signal_overlay.basket_and_overlay_hash(
        cma, Profile.GROWTH, {"S3": "strong_pos"}, single_stock_cap=0.25)
    assert h0["basket_hash"] == h1["basket_hash"]      # 코어 해시는 AI 무관·불변
    assert h0["overlay_hash"] != h1["overlay_hash"]    # 오버레이 해시는 신호 반영


def test_null_signal_source_is_off():
    assert signal_overlay.NullSignalSource().signals() == {}
