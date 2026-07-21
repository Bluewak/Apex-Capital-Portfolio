"""FactLedger (v2 §3.4) — NumericResult에서 인용 가능한 값만 뽑은 화이트리스트.

Narrator(자문 계층)의 **유일 진실 소스**. 원값 PII·개별 금액 없음(밴드 수준). 성향 라벨·
밴드 수치·계산 지표·decision·강등 경로만. 자문 게이트가 서술의 숫자를 이 원장과 대조해
창작을 폐기한다(수치 충실도). 결정론 코어(비-LLM) 산출.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from apex.schemas import NumericResult


def _band_pct(x: float) -> str:
    """수치를 정수 % 밴드로(거짓 정밀·과잉 노출 방지)."""
    return f"{round(abs(x) * 100)}%"


class FactLedger(BaseModel):
    """서술이 인용 가능한 사실의 화이트리스트(밴드·PII 없음)."""

    profile_label: str
    decision: str
    downgrade_path: list[str] = Field(default_factory=list)
    facts: dict[str, str] = Field(default_factory=dict)  # 인용 가능 사실(밴드 문자열)
    numbers: list[str] = Field(default_factory=list)  # 서술 허용 숫자 토큰(밴드 %) 화이트리스트


def extract(numeric: NumericResult) -> FactLedger:
    """NumericResult → FactLedger. ok면 지표·상위비중을 밴드로, hold면 라벨·결정만."""
    facts: dict[str, str] = {"성향": numeric.final_profile, "결정": numeric.decision}
    numbers: list[str] = []
    if numeric.decision == "ok" and numeric.risk is not None and numeric.allocation is not None:
        r = numeric.risk
        cagr = _band_pct(numeric.expected_cagr or 0.0)
        vol = _band_pct(r.vol_annual)
        mdd = _band_pct(r.mdd)
        floss = _band_pct(r.expected_loss_1y_forward or 0.0)
        facts.update(
            {"기대수익": cagr, "평시변동성": vol, "평시MDD": mdd, "forward기대손실": floss}
        )
        numbers += [cagr, vol, mdd, floss]
        for t, w in sorted(numeric.allocation.weights.items(), key=lambda kv: -kv[1])[:3]:
            b = _band_pct(w)
            facts[f"비중:{t}"] = b
            numbers.append(b)
    return FactLedger(
        profile_label=numeric.final_profile,
        decision=numeric.decision,
        downgrade_path=list(numeric.downgrade_path),
        facts=facts,
        numbers=numbers,
    )
