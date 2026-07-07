"""M4 Walking Skeleton DoD 검증 (08 §3):
(a) 강등 루프가 실제로 돌고 종료조건(수렴/hold)에서 멈춘다 — compliance→allocation 역간선 실증.
(b) 동일 입력 재실행 시 동일 산출(재현성).
(c) R5: 초안정형 티어가 Q6=-5% 고객의 즉시-hold를 해소한다.
(d) ReturnSeries 계약(backtest→risk 경계) 검증.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apex import data, pipeline
from apex.schemas import SurveyAnswers


def _survey(**kw) -> SurveyAnswers:
    base = dict(
        q1_age=45, q2_horizon=3, q3_objective="균형", q4_capital=1, q5_monthly=0,
        q6_max_loss=-0.15, q7_experience="보통", q8_liquidity="보통",
        q9_fx="일부허용", q10_behavior="유지", input_snapshot_id="t",
    )
    base.update(kw)
    return SurveyAnswers(**base)


def test_downgrade_loop_runs_and_terminates():
    """공격형 요청 + Q6=-15% → VaR 초과로 강등, 사다리에서 종료(역간선 실증)."""
    res = pipeline.run(_survey(
        q1_age=29, q2_horizon=5, q3_objective="증식",
        q6_max_loss=-0.15, q7_experience="많음", q10_behavior="추가매수",
    ))
    assert res.decision == "ok"  # 강등 끝에 수렴
    assert len(res.downgrade_path) >= 1  # 최소 1회 강등 발생
    assert res.breaches  # 위반이 기록됨
    assert res.final_profile in {"성장형", "중립형", "안정형", "초안정형"}  # 공격형보다 낮아짐
    assert res.allocation is not None


def test_ultra_conservative_resolves_hold():
    """R5: Q6=-5% 최보수 은퇴 고객 → 초안정형 발행(hold 아님). 시뮬 Persona A 해소."""
    res = pipeline.run(_survey(
        q1_age=62, q2_horizon=3, q3_objective="보전",
        q6_max_loss=-0.05, q7_experience="없음", q8_liquidity="보통",
        q9_fx="회피", q10_behavior="매도",
    ))
    assert res.decision == "ok"
    assert res.final_profile == "초안정형"
    assert res.allocation is not None
    assert res.allocation.weights["SHY"] >= 0.5  # near-cash


def test_hold_for_sub_ultra_demand():
    """초안정형(평시 VaR≈2%)보다 더 타이트한 감내(-1.5%) → 사다리 소진 → hold."""
    res = pipeline.run(_survey(q1_age=70, q3_objective="보전", q6_max_loss=-0.015,
                               q7_experience="없음", q10_behavior="매도"))
    assert res.decision == "hold"
    assert res.allocation is None  # 포트 미발행(R5)
    assert res.risk is None
    assert res.breaches and res.breaches[-1].metric == "var95_annual"


def test_reproducibility_same_input_same_hash():
    """동일 입력·동일 스냅샷 → 동일 산출 해시(08 §6 재현성)."""
    s = _survey(q1_age=50, q6_max_loss=-0.20)
    r1 = pipeline.run(s)
    r2 = pipeline.run(s)
    assert r1.result_hash == r2.result_hash
    assert len(r1.result_hash) == 64  # sha256


def test_return_series_contract_ok_and_rejects_bad():
    """ReturnSeries 계약: 정상 통과 + NaN/dtype 위반 하드 실패."""
    good = data.build_return_series(np.array([0.001, -0.002, 0.0]), currency="USD")
    data.validate_return_series(good)  # 통과

    bad = good.copy()
    bad.iloc[0] = np.nan
    with pytest.raises(ValueError):
        data.validate_return_series(bad)

    # tz-naive 인덱스 거부
    naive = pd.Series([0.001, 0.0], index=pd.bdate_range("2020-01-01", periods=2), name="ret")
    naive.attrs.update(currency="USD", data_version="x")
    with pytest.raises(ValueError):
        data.validate_return_series(naive)
