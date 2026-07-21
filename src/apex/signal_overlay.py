"""신호 오버레이 (v3-B Step 3 · docs/13 §4) — Step 2 바스켓 위 뉴스·선호 신호 BL 틸트.

**기본 OFF**(신호 없으면 Step 2 결정론 바스켓 정확 일치, forward-only 실험). AI는 이산 신호만
출력, 캘리브레이션([signal_calibration])이 (Q,Ω)로, BL([black_litterman])이 μ 틸트,
결정론 optimizer가 최종 비중. **해시 분리**: `basket_hash`(신호 무·백테스트 가능 코어) ⊥
`overlay_hash`(신호 핀 ID) — 코어 해시는 AI를 절대 안 담음(패널 [High]).

**뷰-검증 게이트**(advisory_gate 미러): 허용 어휘·알려진 티커만 통과, 실패 → 뷰 폐기(중립)·
prior 폴백. 뉴스=신뢰불가 입력이므로 신호원(SPI)은 allow-list·이산 어휘로 제한.
"""
from __future__ import annotations

import hashlib
import json
from typing import Protocol

from apex import black_litterman as bl
from apex import signal_calibration as sc
from apex import stock_optimizer
from apex.schemas import CMASet
from apex.schemas.enums import Profile

OVERLAY_METHOD = "signal-overlay-v1"


class SignalSource(Protocol):
    """뉴스·선호 → 이산 신호 SPI. LLM 허용(비결정)하되 **이산 어휘만** 출력(§4.1)."""

    DETERMINISM_REQUIRED = False

    def signals(self, context: object) -> dict[str, str]: ...


class NullSignalSource:
    """기본 신호원 — 항상 빈 신호(overlay OFF). LLM 뉴스 어댑터 부재 시 무손실 폴백."""

    DETERMINISM_REQUIRED = False

    def signals(self, context: object = None) -> dict[str, str]:
        return {}


def validate_signals(signals: dict[str, str], tickers: list[str]) -> tuple[dict, list]:
    """뷰-검증 게이트(결정론): 알려진 티커 + 허용 이산 어휘만 통과. 나머지 폐기(사유 기록)."""
    clean, rejected = {}, []
    for tk, sig in sorted(signals.items()):
        if tk not in tickers:
            rejected.append({"ticker": tk, "reason": "unknown_ticker"})
        elif not sc.is_valid_signal(sig):
            rejected.append({"ticker": tk, "signal": sig, "reason": "invalid_signal"})
        else:
            clean[tk] = sig
    return clean, rejected


def apply(cma: CMASet, profile: Profile, signals: dict[str, str] | None = None,
          single_stock_cap: float = stock_optimizer.DEFAULT_STOCK_CAP,
          tau: float = bl.DEFAULT_TAU) -> dict:
    """Step 2 바스켓 + 신호 → 틸트 바스켓. 신호 없으면 Step 2 바스켓 정확(OFF 항등성).

    반환: {weights, signals_applied, rejected, overlay_active, calib_version}.
    """
    clean, rejected = validate_signals(signals or {}, cma.tickers)
    mu_bl = bl.blend(cma, clean, tau)
    tilted = cma.model_copy(update={"mu": {t: round(mu_bl[t], 6) for t in cma.tickers}})
    weights = stock_optimizer.optimize(tilted, profile, single_stock_cap)
    return {"weights": weights, "signals_applied": clean, "rejected": rejected,
            "overlay_active": bool(clean), "calib_version": sc.calib_version()}


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False)
                          .encode("utf-8")).hexdigest()[:16]


def basket_and_overlay_hash(cma: CMASet, profile: Profile, signals: dict[str, str],
                            single_stock_cap: float = stock_optimizer.DEFAULT_STOCK_CAP) -> dict:
    """해시 물리 분리(§5): basket_hash(신호 무·결정론 코어) ⊥ overlay_hash(신호 반영).

    basket_hash는 AI를 절대 안 담아 백테스트 가능 코어를 오염 없이 봉인.
    """
    base = stock_optimizer.optimize(cma, profile, single_stock_cap)
    over = apply(cma, profile, signals, single_stock_cap)
    return {
        "basket_hash": _hash({"w": {k: round(v, 8) for k, v in base.items()}}),
        "overlay_hash": _hash({"w": {k: round(v, 8) for k, v in over["weights"].items()},
                               "signals": over["signals_applied"],
                               "calib": over["calib_version"]}),
        "overlay_active": over["overlay_active"],
    }
