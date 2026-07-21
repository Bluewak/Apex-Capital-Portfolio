"""Black-Litterman 엔진 (v3-B Step 3 · docs/13 §4.2) — 시총균형 prior + 뷰 → posterior μ.

**패널 [High] 반영**: optimizer.py에 BL이 없어 신규 구축. prior = **시총균형 역최적화**
(π=δΣw_mkt) — "성향 바스켓을 prior로" 하면 optimizer 산출을 되먹이는 순환이라 금지.
뷰는 신호 캘리브레이션([signal_calibration])이 만든 (Q,Ω), P는 단일종목 절대뷰(e_i).

**null-view 항등성**: 뷰 없으면 posterior = prior 정확 일치 → 신호 OFF면 순수 결정론 바스켓
으로 우아 폴백(패널 [Med], CI 핏함수로 강제). 결정론(순수 numpy).
"""
from __future__ import annotations

import numpy as np

from apex import signal_calibration as sc

BL_METHOD_VERSION = "bl-mktcap-prior-v1"
DEFAULT_TAU = 0.05          # prior 불확실성 스케일(BL 관행)
DEFAULT_RISK_AVERSION = 2.5  # δ(시장 위험회피) — 균형 역최적화


def equilibrium_returns(cov: np.ndarray, w_mkt: np.ndarray,
                        risk_aversion: float = DEFAULT_RISK_AVERSION) -> np.ndarray:
    """시총균형 역최적화 prior: π = δ Σ w_mkt (연율). 순환 없는 앵커."""
    return risk_aversion * (cov @ w_mkt)


def mktcap_weights(tickers: list[str], mktcaps: dict[str, float]) -> np.ndarray:
    """시가총액 → 정규화 시장 비중(prior 앵커용)."""
    caps = np.array([max(mktcaps.get(t, 0.0), 0.0) for t in tickers], dtype=float)
    s = caps.sum()
    return caps / s if s > 0 else np.full(len(tickers), 1.0 / len(tickers))


def build_views(signals: dict[str, str], tickers: list[str]):
    """이산 신호 {ticker: signal_class} → (P, Q_excess, Ω). neutral·미지티커 제외.

    P=단일종목 절대뷰(e_i), Q_excess=캘리브 뷰크기(prior 대비 초과), Ω=캘리브 불확실성.
    뷰 없으면 None(→ null-view = prior).
    """
    rows, q, om = [], [], []
    for tk, sig in signals.items():
        if tk not in tickers or sig == "neutral" or not sc.is_valid_signal(sig):
            continue
        qi, oi = sc.view_qomega(sig)
        p = np.zeros(len(tickers))
        p[tickers.index(tk)] = 1.0
        rows.append(p)
        q.append(qi)
        om.append(oi)
    if not rows:
        return None
    return np.array(rows), np.array(q), np.diag(om)


def posterior(pi: np.ndarray, cov: np.ndarray, views, tau: float = DEFAULT_TAU) -> np.ndarray:
    """BL posterior μ. views=(P, Q_excess, Ω) 또는 None(→ prior 정확 반환).

    절대뷰 수준 Q_abs = P·π + Q_excess(신호는 균형 대비 초과) → null-view면 posterior=π.
    μ_bl = [(τΣ)⁻¹ + PᵀΩ⁻¹P]⁻¹ [(τΣ)⁻¹π + PᵀΩ⁻¹Q_abs].
    """
    if views is None:
        return pi.copy()
    p_mat, q_excess, omega = views
    q_abs = p_mat @ pi + q_excess
    tsi = np.linalg.inv(tau * cov)
    oi = np.linalg.inv(omega)
    a = tsi + p_mat.T @ oi @ p_mat
    b = tsi @ pi + p_mat.T @ oi @ q_abs
    return np.linalg.solve(a, b)


def blend(cma, signals: dict[str, str], tau: float = DEFAULT_TAU) -> dict[str, float]:
    """CMA + 신호 → BL posterior μ dict(티커별).

    **prior = CMA GK μ**(시총균형 아님) — μ는 기대수익 추정이지 바스켓 산출이 아니라 순환
    없고, **신호 없으면 posterior=GK μ 정확** → optimize도 Step 2 바스켓과 정확 일치(overlay
    OFF 항등성, 패널 [Med]). 시총균형 앵커는 `equilibrium_returns`로 별도 제공(대안).
    """
    cov = cma.cov_mat()
    pi = cma.mu_vec()  # CMA GK μ = prior(순환 아님·OFF 항등성)
    mu_bl = posterior(pi, cov, build_views(signals, cma.tickers), tau)
    return {t: float(mu_bl[i]) for i, t in enumerate(cma.tickers)}
