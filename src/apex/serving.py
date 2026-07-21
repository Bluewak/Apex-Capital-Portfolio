"""Serving Plane (v2 §3.3) — run_advice 오케스트레이터. 레지스트리 O(1) 소비.

사용자 런의 유일 진입점. **결정론 코어**(score → 사전연산 조회 → 제약 재검증 →
forward-binding compliance → 판정)를 돌린 뒤, 격리된 **Advisory**(narrate)를 호출한다.
20년 백테스트를 반복하지 않는다(Model Plane 사전연산 소비). 강등 루프는 O(1) 조회.

이 모듈은 결정론 코어와 Advisory Plane을 잇는 **bridge**라 apex.advisory를 import한다
(코어 모듈은 금지, §5). numeric_hash는 서술 미포함(§7).
"""
from __future__ import annotations

from pydantic import BaseModel

from apex import advisory, allocation, compliance, factledger, investor, ips, registry, risk
from apex.pipeline import PipelineResult, _canonical_hash, _narrative_hash
from apex.provenance import ENV_HASH, SCHEMA_VERSION
from apex.schemas import (
    Allocation,
    Breach,
    InvestorProfile,
    IPSDocument,
    Narrative,
    NumericResult,
    Registry,
    RiskReport,
    SurveyAnswers,
)


class AdviceCommand(BaseModel):
    """서빙 입력(§3.3). data_version/model_version 미지정이면 최신 레지스트리."""

    answers: SurveyAnswers
    display_currency: str = "KRW"


def run_advice(cmd: AdviceCommand, reg: Registry | None = None) -> PipelineResult:
    """설문 → 사전연산 조회 기반 E2E. forward-binding compliance·강등 루프(O(1)).

    반환 타입은 pipeline.run과 동일한 PipelineResult(계약 불변) — report·store·replay 재사용.
    ``reg``=None이면 최신 레지스트리 로드(핀 우선). 테스트는 합성 레지스트리 주입.
    """
    reg = reg or registry.load_latest()
    profile: InvestorProfile = investor.score(cmd.answers)
    path: list[str] = []
    breaches: list[Breach] = []
    alloc: Allocation | None = None
    rr: RiskReport | None = None
    decision = "hold"
    exp_cagr: float | None = None

    for _ in range(6):  # 사다리 유한 → 반드시 종료. 각 반복 O(1) 조회(재계산 없음)
        entry = reg.lookup(profile.profile, profile.constraints.min_cash)
        alloc = allocation.apply_constraints(entry.allocation, profile.constraints)
        rr = risk.assemble(entry, display_currency=cmd.display_currency)  # forward + 실현 disclosed
        dec = compliance.check(rr, profile)  # forward-binding 활성
        breaches.extend(dec.breaches)
        breaches.extend(compliance.structural_breaches(alloc, profile))  # KG 구조 검증(§3, 골든 0)
        if dec.decision == "ok":
            decision = "ok"
            exp_cagr = entry.forward.expected_return
            break
        if dec.decision == "hold":
            decision = "hold"
            alloc, rr = None, None
            path.append(dec.downgrade_reason or "hold")
            break
        path.append(dec.downgrade_reason or f"{profile.profile.value} 강등")
        profile = dec.revised_profile  # type: ignore[assignment]

    ips_doc: IPSDocument | None = None
    if decision == "ok" and alloc is not None and rr is not None:
        ips_doc = ips.render(profile, alloc, cmd.answers, rr, exp_cagr or 0.0)

    numeric = NumericResult(
        decision=decision,
        final_profile=profile.profile.value,
        risk_score=profile.risk_score,
        downgrade_path=path,
        allocation=alloc,
        risk=rr,
        ips=ips_doc,
        expected_cagr=exp_cagr,
        breaches=breaches,
        schema_version=SCHEMA_VERSION,
        data_version=reg.data_version,
        model_version=reg.model_version,
        env_hash=ENV_HASH,
    )
    # 자문 계층(격리): FactLedger grounding → 서술(게이트·폴백·캐시). 해시 밖(§7).
    ledger = factledger.extract(numeric)
    narrative = Narrative(
        explanation=advisory.narrate(ledger),
        reelicitation=investor.reelicitation_note(cmd.answers),
    )
    return PipelineResult(
        numeric=numeric,
        narrative=narrative,
        numeric_hash=_canonical_hash(numeric),
        narrative_hash=_narrative_hash(narrative),
    )
