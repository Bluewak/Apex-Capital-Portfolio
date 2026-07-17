"""오케스트레이터 (06 §6). 단방향 파이프라인 + compliance→allocation 재계산 루프.

M4 walking skeleton: 1 프로파일을 설문→배분→백테스트→리스크→컴플라이언스(강등 루프)
→ 문장 1줄 → 재현성 해시로 관통한다. 루프 종료(수렴/hold)와 재현성이 M4 DoD(08 §3).

v2 §3.3·§7: 산출을 **결정론 코어(NumericResult, 해시 대상)** 와
**자문 서술(Narrative, 해시 제외)** 로 물리 분리한다. ``numeric_hash``는 서술을
포함하지 않으므로, 룰 템플릿을 LLM 서술로 교체해도 재현성 해시가 흔들리지 않는다.
원장 쓰기는 이 모듈이 아니라 **서빙 계층(cli/service)** 소관 — ``run``은 순수(디스크 무접촉).
"""
from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel

from apex import backtest, data, investor, ips, spi
from apex.provenance import ENV_HASH, MODEL_VERSION, SCHEMA_VERSION
from apex.schemas import (
    Allocation,
    Breach,
    InvestorProfile,
    IPSDocument,
    Narrative,
    NumericResult,
    RiskReport,
    SurveyAnswers,
)


class PipelineResult(BaseModel):
    """apex run 산출물 = 결정론 코어(numeric, 해시 대상) + 자문 서술(narrative, 해시 제외).

    하위호환 접근자(``decision``·``allocation``·``result_hash`` …)는 ``numeric``/``narrative``
    로 위임한다 — report·cli·tests의 기존 속성 접근을 깨지 않기 위함.
    """

    numeric: NumericResult
    narrative: Narrative = Narrative()
    numeric_hash: str = ""
    narrative_hash: str = ""

    # --- 하위호환 접근자(결정론 코어) ---
    @property
    def decision(self) -> str:
        return self.numeric.decision

    @property
    def final_profile(self) -> str:
        return self.numeric.final_profile

    @property
    def risk_score(self) -> int:
        return self.numeric.risk_score

    @property
    def downgrade_path(self) -> list[str]:
        return self.numeric.downgrade_path

    @property
    def allocation(self) -> Allocation | None:
        return self.numeric.allocation

    @property
    def risk(self) -> RiskReport | None:
        return self.numeric.risk

    @property
    def ips(self) -> IPSDocument | None:
        return self.numeric.ips

    @property
    def expected_cagr(self) -> float | None:
        return self.numeric.expected_cagr

    @property
    def breaches(self) -> list[Breach]:
        return self.numeric.breaches

    @property
    def data_version(self) -> str:
        return self.numeric.data_version

    @property
    def result_hash(self) -> str:
        """재현성 해시 = numeric_hash(서술 제외, §7). 하위호환 별칭."""
        return self.numeric_hash

    # --- 하위호환 접근자(자문 서술) ---
    @property
    def explanation(self) -> str:
        return self.narrative.explanation

    @property
    def reelicitation(self) -> str | None:
        return self.narrative.reelicitation


def _round_floats(obj, ndigits: int = 6):
    """산출물 정규화 — 부동소수를 고정 자릿수로(재현성 해시 안정화, 08 §6).

    6자리 = rtol≈1e-6 의도와 정합(ULP 차이엔 견고). 크로스머신 엄밀 검증은
    수치필드 rtol 비교 권장(08 §6, v2 정밀화).
    """
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {k: _round_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(v, ndigits) for v in obj]
    return obj


def _canonical_hash(numeric: NumericResult) -> str:
    """결정론 코어 정규화 JSON의 SHA256. 서술(Narrative) 미포함(§7)."""
    payload = numeric.model_dump(mode="json")
    canon = json.dumps(_round_floats(payload), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _narrative_hash(narr: Narrative) -> str:
    """자문 서술 해시(감사용). numeric_hash에는 포함하지 않는다(§3.4)."""
    payload = narr.model_dump(mode="json")
    canon = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def run(
    answers: SurveyAnswers,
    currency: str = "KRW",
    source: str = "synthetic",
    services: spi.Services | None = None,
) -> PipelineResult:
    """설문 → 리포트 E2E. 강등 루프는 여기(pipeline)가 소유(08 §7).

    source='synthetic'(기본, M4 스켈레톤·오프라인) | 'real'(M5, 실 20년 피닝 스냅샷).
    'real'은 **피닝 스냅샷만 소비**한다(라이브 재수집 없음, v2 §3.1) — 핀 부재 시 하드 실패.

    ``services``: 결정론 코어 서비스 번들(SPI DI, v2 §5). 기본은 룰 어댑터 —
    Step 2/3에서 최적화·LLM 구현으로 계약 불변 교체(구현 대신 인터페이스에 의존).
    """
    svc = services or spi.default_services()
    returns_fn = None
    data_version = data.DATA_VERSION
    if source == "real":
        from apex.allocation import MODEL_PORTFOLIOS
        from apex.data import loader, snapshot

        universe = tuple(sorted({t for w in MODEL_PORTFOLIOS.values() for t in w}))
        _mat = loader.load_returns_matrix(universe)  # 핀 소비(1회 로드, 루프 내 재사용)
        # 실 data_version = 피닝 매니페스트 해시(재실행·크로스머신 안정, §3.1·§6)
        data_version = "real-" + snapshot.pinned_data_version()

        def returns_fn(w: dict[str, float]) -> object:
            return loader.portfolio_returns_quarterly(_mat, w, cost_bps=loader.DEFAULT_COST_BPS)

    profile: InvestorProfile = svc.investor.score(answers)
    path: list[str] = []
    breaches: list[Breach] = []

    alloc: Allocation | None = None
    rr: RiskReport | None = None
    decision = "hold"

    # 재계산 루프: 위반 → 강등(revised_profile) 재배분. 사다리 유한 → 반드시 종료.
    for _ in range(6):  # 5구간 → 최대 4회 강등 + 여유
        alloc = svc.allocation.build(profile.profile, min_cash=profile.constraints.min_cash)
        _bt, series = backtest.run(alloc, currency="USD", returns_fn=returns_fn)
        rr = svc.risk.report(
            series, alloc, display_currency=currency, normal_only=(source == "real")
        )
        dec = svc.compliance.check(rr, profile)
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
        alloc, rr = None, None  # 방어: 미종료/hold 시 포트 미노출(대체 포트 0건, R5)
        explanation = (
            "배정 보류 — 감내 한도에 맞는 예시 배분이 없습니다. 원금보전형(예금·MMF)을 "
            "참고하시고, 감내 한도를 다시 확인해 보세요(교육용, 개인 지시 아님)."
        )

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
        data_version=data_version,
        model_version=MODEL_VERSION,
        env_hash=ENV_HASH,
    )
    narrative = Narrative(
        explanation=explanation,
        reelicitation=investor.reelicitation_note(answers),
    )
    return PipelineResult(
        numeric=numeric,
        narrative=narrative,
        numeric_hash=_canonical_hash(numeric),
        narrative_hash=_narrative_hash(narrative),
    )
