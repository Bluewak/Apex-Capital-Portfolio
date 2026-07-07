"""로컬 TR 조정 엔진 + 대사 단위 테스트 (08 §3 M4.5). 네트워크 없음 — 손검증 픽스처."""
from __future__ import annotations

import numpy as np

from apex.data.adjust import ReconResult, local_tr_returns, reconcile, returns_from_adjclose


def test_dividend_reinvestment_tr():
    """배당 $1(2일차 ex) 재투자 → 총수익이 가격수익 + 배당수익 (손검증)."""
    close = np.array([100.0, 101.0, 102.0, 103.0])
    div = np.array([0.0, 0.0, 1.0, 0.0])
    split = np.zeros(4)
    r = local_tr_returns(close, div, split)
    # day1: 101/100-1 ; day2: (102+1)/101-1 ; day3: 103/102-1(배당 재투자분 반영 동일 비율)
    assert np.isclose(r[0], 0.01)
    assert np.isclose(r[1], 103.0 / 101.0 - 1.0)      # 0.0198019…
    assert np.isclose(r[2], 103.0 / 102.0 - 1.0)      # 재투자로 비율수익은 가격비율과 동일
    # 누적 총수익 = 가격상승 + 배당 재투자
    assert np.prod(1 + r) > 103.0 / 100.0             # 배당분 초과


def test_split_raw_unadjusted_close():
    """raw unadjusted 종가(분할일 반토막) + splits=2.0 → 총수익 0 (가치 불변).

    close_is_split_adjusted=False 경로. yfinance Close는 이미 분할조정이라 기본은 True.
    """
    close = np.array([100.0, 50.0])
    split = np.array([0.0, 2.0])
    r = local_tr_returns(close, np.zeros(2), split, close_is_split_adjusted=False)
    assert np.isclose(r[0], 0.0)


def test_split_adjusted_close_ignores_splits():
    """분할조정 종가(기본 True)에선 splits 컬럼을 재적용하지 않는다(이중적용 방지)."""
    close = np.array([100.0, 101.0])
    split = np.array([0.0, 3.0])  # 정보성 — 재적용 금지
    r = local_tr_returns(close, np.zeros(2), split)  # 기본 True
    assert np.isclose(r[0], 0.01)  # 3배 유령수익 없음


def test_capital_gains_included():
    """자본이득 분배도 재투자 대상."""
    close = np.array([100.0, 100.0])
    r = local_tr_returns(close, np.zeros(2), np.zeros(2), capital_gains=np.array([0.0, 2.0]))
    assert np.isclose(r[0], 2.0 / 100.0)  # 가격 불변 + 분배 2 → +2%


def test_reconcile_identical_passes():
    ret = np.array([0.01, -0.02, 0.005, 0.0])
    res = reconcile(ret, ret, tol_annual=0.001)
    assert isinstance(res, ReconResult)
    assert res.passed and np.isclose(res.ann_dev, 0.0) and res.max_daily_abs == 0.0


def test_reconcile_detects_drift():
    """레퍼런스 대비 매일 +5bp 초과 → 연율 편차가 허용오차 초과."""
    n = 252
    ref = np.zeros(n)
    loc = np.full(n, 0.0005)  # 매일 +5bp
    res = reconcile(loc, ref, tol_annual=0.002)
    assert not res.passed
    assert res.ann_dev > 0.10  # 대략 (1.0005^252 - 1) ≈ 13%


def test_returns_from_adjclose():
    adj = np.array([100.0, 110.0, 99.0])
    r = returns_from_adjclose(adj)
    assert np.isclose(r[0], 0.10) and np.isclose(r[1], 99.0 / 110.0 - 1.0)
