"""오케스트레이터 (06 §6). 단방향 파이프라인 + compliance→allocation 재계산 루프.

M4 walking skeleton: 1 프로파일을 설문→배분→백테스트→리스크→컴플라이언스(강등 루프)
→ 문장 1줄 → 재현성 해시로 관통한다. 루프 종료(수렴/hold)와 재현성이 M4 DoD(08 §3).
"""
from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, Field

from apex import allocation, backtest, compliance, data, investor, ips, risk
from apex.schemas import (
    Allocation,
    Breach,
    InvestorProfile,
    IPSDocument,
    RiskReport,
    SurveyAnswers,
)


class PipelineResult(BaseModel):
    """apex run 산출물(스켈레톤). hold면 allocation/risk = None(포트 미발행, R5)."""

    decision: str  # "ok" | "hold"
    final_profile: str
    risk_score: int
    downgrade_path: list[str] = Field(default_factory=list)
    allocation: Allocation | None = None
    risk: RiskReport | None = None
    ips: IPSDocument | None = None
    expected_cagr: float | None = None
    breaches: list[Breach] = Field(default_factory=list)
    reelicitation: str | None = None  # 모순 주문 재보정 문구(R5)
    explanation: str
    data_version: str = data.DATA_VERSION
    result_hash: str = ""


def _round_floats(obj, ndigits: int = 9):
    """산출물 정규화 — 부동소수를 고정 자릿수로(재현성 해시 안정화, 08 §6)."""
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {k: _round_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(v, ndigits) for v in obj]
    return obj


def _canonical_hash(result: PipelineResult) -> str:
    payload = result.model_dump(mode="json", exclude={"result_hash"})
    canon = json.dumps(_round_floats(payload), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def run(
    answers: SurveyAnswers, currency: str = "KRW", source: str = "synthetic"
) -> PipelineResult:
    """설문 → 리포트 E2E. 강등 루프는 여기(pipeline)가 소유(08 §7).

    source='synthetic'(기본, M4 스켈레톤·오프라인) | 'real'(M5, 실 20년 스냅샷).
    """
    returns_fn = None
    if source == "real":
        from apex.allocation import MODEL_PORTFOLIOS
        from apex.data import loader

        universe = tuple(sorted({t for w in MODEL_PORTFOLIOS.values() for t in w}))
        _mat = loader.load_returns_matrix(universe)  # 1회 로드, 루프 내 재사용

        def returns_fn(w: dict[str, float]) -> object:
            return loader.portfolio_returns_quarterly(_mat, w, cost_bps=loader.DEFAULT_COST_BPS)

    profile: InvestorProfile = investor.score(answers)
    path: list[str] = []
    breaches: list[Breach] = []

    alloc: Allocation | None = None
    rr: RiskReport | None = None
    decision = "hold"

    # 재계산 루프: 위반 → 강등(revised_profile) 재배분. 사다리 유한 → 반드시 종료.
    for _ in range(6):  # 5구간 → 최대 4회 강등 + 여유
        alloc = allocation.build(profile.profile)
        _bt, series = backtest.run(alloc, currency="USD", returns_fn=returns_fn)
        rr = risk.report(series, alloc, display_currency=currency, normal_only=(source == "real"))
        dec = compliance.check(rr, profile)
        breaches.extend(dec.breaches)

        if dec.decision == "ok":
            decision = "ok"
            break
        if dec.decision == "hold":
            decision = "hold"
            alloc, rr = None, None  # 포트 미발행(R5)
            path.append(dec.downgrade_reason or "hold")
            break
        # downgrade
        path.append(dec.downgrade_reason or f"{profile.profile.value} 강등")
        profile = dec.revised_profile  # type: ignore[assignment]

    ips_doc: IPSDocument | None = None
    exp_cagr: float | None = None
    if decision == "ok" and alloc is not None and rr is not None:
        exp_cagr = _bt.cagr
        top = sorted(alloc.weights.items(), key=lambda kv: -kv[1])[:3]
        top_s = " · ".join(f"{t} {w:.0%}" for t, w in top)
        explanation = (
            f"{profile.profile.value} 유형 예시 배분({top_s} …) — 기대 CAGR "
            f"{_bt.cagr:.1%}, 평시 MDD {rr.mdd:.1%}, 연율 VaR95 {rr.var95_annual:.1%}. "
            "개별 투자권유 아님(교육·분석용)."
        )
        ips_doc = ips.render(profile, alloc, answers, rr, _bt.cagr)
    else:
        explanation = (
            "배정 보류 — 감내 한도에 맞는 예시 배분이 없습니다. 원금보전형(예금·MMF)을 "
            "참고하시고, 감내 한도를 다시 확인해 보세요(교육용, 개인 지시 아님)."
        )

    result = PipelineResult(
        decision=decision,
        final_profile=profile.profile.value,
        risk_score=profile.risk_score,
        downgrade_path=path,
        allocation=alloc,
        risk=rr,
        ips=ips_doc,
        expected_cagr=exp_cagr,
        breaches=breaches,
        reelicitation=investor.reelicitation_note(answers),
        explanation=explanation,
        data_version="real-snapshot" if source == "real" else data.DATA_VERSION,
    )
    result.result_hash = _canonical_hash(result)
    return result
