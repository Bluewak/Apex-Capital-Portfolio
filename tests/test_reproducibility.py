"""Step 0 DoD — 크로스프로세스 재현성 (v2 §6·§8-1).

**별도 2프로세스**에서 동일 입력을 실행해 numeric_hash가 동일함을 검증한다.
같은 프로세스 재호출(test_skeleton)보다 강한 보증 — 해시 시드·환경 순서 의존을 배제.
BLAS 스레드 핀(OMP/MKL/OPENBLAS=1)을 프로세스 진입 전에 세팅해 부동소수 비결정성 억제.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"

_SNIPPET = (
    "from apex import pipeline;"
    "from apex.schemas import SurveyAnswers;"
    "a=SurveyAnswers(q1_age=45,q2_horizon=3,q3_objective='균형',q4_capital=1,q5_monthly=0,"
    "q6_max_loss=-0.15,q7_experience='보통',q8_liquidity='보통',q9_fx='일부허용',"
    "q10_behavior='유지',input_snapshot_id='repro');"
    "print(pipeline.run(a).numeric_hash)"
)


def _run_once() -> str:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SRC) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONHASHSEED"] = "0"
    for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        env[k] = "1"
    out = subprocess.run(
        [sys.executable, "-c", _SNIPPET],
        capture_output=True, text=True, env=env, check=True,
    )
    return out.stdout.strip().splitlines()[-1]


def test_cross_process_numeric_hash_is_stable():
    """독립 2프로세스 → 동일 numeric_hash(64 hex)."""
    h1 = _run_once()
    h2 = _run_once()
    assert h1 == h2, f"크로스프로세스 재현 실패: {h1} != {h2}"
    assert len(h1) == 64
