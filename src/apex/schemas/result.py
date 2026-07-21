"""산출 계약 — 결정론 코어(해시 대상) vs 자문 서술(해시 제외) 물리 분리.

v2 §3.3·§4·§7: LLM화(Advisory Plane)의 물리적 전제. ``NumericResult``만
재현성 해시(numeric_hash)에 들어가고, 서술(``Narrative``)은 해시 밖 + 캐시.
→ 룰 템플릿을 LLM 서술로 바꿔도 재현성 해시가 흔들리지 않는다.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from apex.provenance import ENV_HASH, MODEL_VERSION, SCHEMA_VERSION

from .allocation import Allocation
from .ips import IPSDocument
from .risk import Breach, RiskReport


class NumericResult(BaseModel):
    """결정론 코어 산출 — 재현성 해시 대상(§7). 서술 미포함.

    프로버넌스(schema/data/env 버전)를 필드로 각인 → 재현성 스코프를 타입이 강제.
    """

    decision: str  # "ok" | "hold"
    final_profile: str
    risk_score: int
    downgrade_path: list[str] = Field(default_factory=list)
    allocation: Allocation | None = None
    risk: RiskReport | None = None
    ips: IPSDocument | None = None
    expected_cagr: float | None = None
    breaches: list[Breach] = Field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    data_version: str = ""
    model_version: str = MODEL_VERSION  # 배분 산출 모델 리니지(Step 2 레지스트리 교체 대상)
    env_hash: str = ENV_HASH


class Narrative(BaseModel):
    """비결정론 자문 서술 — 재현성 해시 제외(§3.4·§7). LLM화 시 여기만 교체.

    현재는 룰 템플릿 산출(explanation·reelicitation). 감사용 narrative_hash는
    별도 계산하되 numeric_result_hash에 **포함하지 않는다**.
    """

    explanation: str = ""
    reelicitation: str | None = None  # 모순 주문 재보정 문구(R5)
