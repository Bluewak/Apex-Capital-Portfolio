"""Model Registry (v2 §3.2·§3.6) — 5성향×min_cash 사전연산 그리드 빌드·저장·조회.

오프라인 배치(`apex model build`)가 CMA→Optimizer로 (성향×min_cash) 각 칸의 배분·
forward 리스크·실현 요약을 1회 계산해 버전드 아티팩트로 봉인한다. 사용자 런(Step 3)은
이 레지스트리를 **O(1) 조회** — 20년 백테스트를 반복하지 않는다.

핀 우선(§3.1): 실현 리스크는 피닝 스냅샷에서만. 라이브 재수집 없음.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from apex import forward, optimizer, validation
from apex.provenance import ENV_HASH
from apex.schemas import (
    Allocation,
    CMASet,
    PrecomputedEntry,
    Registry,
    RiskReport,
    ValidationResult,
)
from apex.schemas.enums import Profile

REGISTRY_DIR = Path("artifacts/registry")
DEFAULT_MIN_CASH_GRID = (0.0, 0.05, 0.10)


def _realized(mat: pd.DataFrame, alloc: Allocation) -> tuple[RiskReport, np.ndarray]:
    """배분 백테스트 → (실현 평시 RiskReport, 포트 일별수익률). 위기 제외 평시."""
    from apex import risk
    from apex.data import build_return_series, loader

    port = loader.portfolio_returns_quarterly(
        mat, alloc.weights, cost_bps=loader.DEFAULT_COST_BPS
    )
    series = build_return_series(port.to_numpy(), currency="USD", index=port.index)
    rr = risk.report(series, alloc, display_currency="KRW", normal_only=True)
    return rr, port.to_numpy()


def _daily_sr(ret: np.ndarray) -> float:
    return float(ret.mean() / ret.std(ddof=1)) if ret.std(ddof=1) > 0 else 0.0


def _validate(ret: np.ndarray, var_1d: float, sr_star: float) -> ValidationResult:
    """포트 수익률 → 검증 게이트(다중검정 보정 PSR·Kupiec·OOS)."""
    psr = validation.probabilistic_sharpe(ret, sr_benchmark=sr_star)
    kp, kpass = validation.kupiec_pof(ret, var_1d, alpha=0.05)
    oos = validation.walk_forward_stable(ret)
    return ValidationResult(
        psr=round(psr, 6), kupiec_p=kp, kupiec_pass=kpass, oos_stable=oos,
        passed=bool(psr > 0.95 and kpass and oos),
    )


def build(
    cma: CMASet,
    mat: pd.DataFrame | None = None,
    min_cash_grid: tuple[float, ...] = DEFAULT_MIN_CASH_GRID,
    profiles: tuple[Profile, ...] = tuple(Profile),
) -> Registry:
    """CMA(+선택적 실현 백테스트 행렬) → 사전연산 Registry.

    ``mat``=None이면 forward만(실현 None). CLI는 피닝 행렬을 주입해 실현 병기.
    결정론: 동일 (cma, mat, grid) → 동일 Registry.
    """
    # 1패스: 배분·forward·실현 + 포트 일별수익률 수집(검증용)
    rows = []
    for profile in profiles:
        for mc in min_cash_grid:
            alloc = optimizer.optimize(cma, profile, min_cash=mc)
            fr = forward.forward_risk(cma, alloc.weights)
            if mat is None:
                rows.append((profile, mc, alloc, fr, None, None))
            else:
                rr, port = _realized(mat, alloc)
                rows.append((profile, mc, alloc, fr, rr, port))

    # 다중검정 보정 SR*(전 엔트리 일별 Sharpe에서) → PSR을 deflate
    ports = [p for *_, p in rows if p is not None]
    sr_star = validation.deflated_sr_benchmark([_daily_sr(p) for p in ports]) if ports else 0.0

    # 2패스: 검증 게이트 + 엔트리 봉인
    entries: list[PrecomputedEntry] = []
    for profile, mc, alloc, fr, rr, port in rows:
        val = None if port is None else _validate(port, rr.var95_1d, sr_star)
        entries.append(
            PrecomputedEntry(profile=profile, min_cash=mc, allocation=alloc,
                             forward=fr, realized=rr, validation=val)
        )
    return Registry(
        cma_version=cma.cma_version,
        data_version=cma.data_version,
        model_version="opt-" + optimizer.OPT_METHOD_VERSION,
        env_hash=ENV_HASH,
        as_of=cma.as_of,
        min_cash_grid=list(min_cash_grid),
        entries=entries,
    )


def save(reg: Registry, directory: Path = REGISTRY_DIR) -> Path:
    """레지스트리를 {cma_version}.json + latest.json으로 저장. 반환: 버전 파일 경로."""
    directory.mkdir(parents=True, exist_ok=True)
    payload = reg.model_dump_json(indent=2)
    path = directory / f"{reg.cma_version}.json"
    path.write_text(payload, encoding="utf-8")
    (directory / "latest.json").write_text(payload, encoding="utf-8")
    return path


def load_latest(directory: Path = REGISTRY_DIR) -> Registry:
    """가장 최근 저장된 레지스트리 로드(Step 3 서빙 조회의 진입점)."""
    path = directory / "latest.json"
    if not path.exists():
        raise FileNotFoundError(
            f"레지스트리 부재: {path} — 먼저 `apex model build`로 사전연산하세요(§3.2)."
        )
    return Registry(**json.loads(path.read_text(encoding="utf-8")))


def build_from_pinned(start: str = "2005-01-01") -> Registry:
    """피닝 스냅샷 → CMA → 사전연산 Registry(실현 병기). 라이브 재수집 없음(§3.1)."""
    from apex import cma as cma_mod
    from apex.allocation import MODEL_PORTFOLIOS
    from apex.data import loader

    universe = tuple(sorted({t for w in MODEL_PORTFOLIOS.values() for t in w}))
    mat = loader.load_returns_matrix(universe, start)
    cset = cma_mod.build_from_pinned(start)
    return build(cset, mat=mat)
