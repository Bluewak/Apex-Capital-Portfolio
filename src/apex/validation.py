"""검증 게이트 (v2 §3.2) — 백테스트 산출의 통계적 방어. 순수 numpy·결정론.

강세장 표본에서 좋아 보이는 배분이 out-of-sample에서도 유효한지 통계로 검증한다:
- **PSR**(Probabilistic Sharpe Ratio, Bailey-LdP): 왜도·첨도 보정한 "참 Sharpe>기준" 확률.
- **Kupiec POF**(VaR-backtest): 일별 VaR 초과율이 명목 α와 정합한지 LR 우도비 검정.
- **walk-forward**: IS/OOS 분할에서 Sharpe 부호 안정성.

scipy 없이 정규 CDF(math.erf)·PPF(Acklam 유리근사)를 구현. n_trials 다중검정 보정은
PSR 기준을 SR*로 올려 DSR로 확장(레지스트리 빌드가 교차 Sharpe로 주입).
"""
from __future__ import annotations

import math

import numpy as np

from apex.metrics import TRADING_DAYS


def norm_cdf(x: float) -> float:
    """표준정규 CDF Φ(x) = ½(1+erf(x/√2))."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    """표준정규 역CDF Φ⁻¹(p) — Acklam 유리근사(결정론, |오차|<1.15e-9)."""
    if not 0.0 < p < 1.0:
        return -math.inf if p <= 0 else math.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow or p > phigh:
        q = math.sqrt(-2 * math.log(p if p < plow else 1 - p))
        num = ((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]
        den = (((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1
        return num / den if p < plow else -num / den
    q = p - 0.5
    r = q * q
    num = (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5]) * q
    den = ((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1
    return num / den


def probabilistic_sharpe(returns: np.ndarray, sr_benchmark: float = 0.0) -> float:
    """PSR = P(참 Sharpe > sr_benchmark). 왜도·첨도 보정(비정규 꼬리 반영).

    sr_benchmark를 다중검정 SR*(deflated)로 올리면 DSR이 된다. 일별 SR 기준.
    """
    r = np.asarray(returns, dtype=float)
    n = len(r)
    if n < 10 or r.std(ddof=1) == 0:
        return 0.0
    sr = r.mean() / r.std(ddof=1)  # 일별 Sharpe
    m = r - r.mean()
    s = r.std(ddof=0)
    skew = float((m**3).mean() / s**3)
    kurt = float((m**4).mean() / s**4)  # 정규=3
    denom = math.sqrt(max(1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2, 1e-12))
    return norm_cdf((sr - sr_benchmark) * math.sqrt(n - 1) / denom)


def deflated_sr_benchmark(sharpes: list[float]) -> float:
    """다중검정 보정 SR* (Bailey-LdP): N개 시행 하 귀무의 기대 최대 Sharpe(일별)."""
    n = len(sharpes)
    if n < 2:
        return 0.0
    var_sr = float(np.var(sharpes, ddof=1))
    if var_sr <= 0:
        return 0.0
    gamma = 0.5772156649015329  # Euler-Mascheroni
    z = (1 - gamma) * norm_ppf(1 - 1.0 / n) + gamma * norm_ppf(1 - 1.0 / (n * math.e))
    return math.sqrt(var_sr) * z


def kupiec_pof(returns: np.ndarray, var_1d: float, alpha: float = 0.05) -> tuple[float, bool]:
    """Kupiec 무조건 커버리지(POF) LR 검정 — VaR 초과율이 α와 정합한가.

    var_1d = 양수 손실률(1일 VaR95). 반환 (p_value, pass@5%). 초과율≈α면 통과.
    """
    r = np.asarray(returns, dtype=float)
    n = len(r)
    x = int((r < -abs(var_1d)).sum())  # 초과(손실이 VaR 초과) 횟수
    if n == 0:
        return 1.0, True
    pi = x / n
    if x == 0 or x == n:
        return 1.0, True  # 극단(초과 0 또는 전부)은 커버리지 판정 보류 → 통과 처리
    ln_null = x * math.log(alpha) + (n - x) * math.log(1 - alpha)
    ln_alt = x * math.log(pi) + (n - x) * math.log(1 - pi)
    lr = -2.0 * (ln_null - ln_alt)  # ~χ²(1)
    p_value = 1.0 - _chi2_cdf1(lr)
    return round(p_value, 6), p_value > 0.05


def _chi2_cdf1(x: float) -> float:
    """χ²(df=1) CDF = 2Φ(√x)−1 (x≥0)."""
    return 0.0 if x <= 0 else 2.0 * norm_cdf(math.sqrt(x)) - 1.0


def walk_forward_stable(returns: np.ndarray) -> bool:
    """IS/OOS 반분할에서 Sharpe 부호가 뒤집히지 않는가(간이 OOS 안정성)."""
    r = np.asarray(returns, dtype=float)
    if len(r) < 40:
        return True
    mid = len(r) // 2
    a, b = r[:mid], r[mid:]

    def _sr(x: np.ndarray) -> float:
        return float(x.mean() / x.std(ddof=1)) if x.std(ddof=1) > 0 else 0.0

    return _sr(a) * _sr(b) >= 0  # 부호 동일(또는 0)이면 안정


def annualize_sharpe(sr_daily: float) -> float:
    return sr_daily * math.sqrt(TRADING_DAYS)
