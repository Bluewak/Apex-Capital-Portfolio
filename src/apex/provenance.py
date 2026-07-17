"""재현성 프로버넌스 — schema/env 버전 각인 (v2 §6, 10-v2-pipeline-design).

결정론 산출(NumericResult)의 정체성에 스키마·환경 버전을 붙여, 재현성 스코프를
타입이 강제하게 한다(08 §6 2체크포인트). ``ENV_HASH``는 파이썬·수치 라이브러리
버전 서명 — 환경이 바뀌면 해시가 바뀌므로 크로스머신 재현성이 '주장'이 아니라
'검증 가능한 사실'이 된다(같은 env → 같은 numeric_hash).
"""
from __future__ import annotations

import hashlib
import sys

import numpy as np
import pandas as pd

SCHEMA_VERSION = "1"


def _env_hash() -> str:
    """파이썬·numpy·pandas·스키마 버전 서명의 SHA256 앞 12자리."""
    sig = (
        f"py{sys.version_info.major}.{sys.version_info.minor}"
        f"|np{np.__version__}|pd{pd.__version__}|schema{SCHEMA_VERSION}"
    )
    return hashlib.sha256(sig.encode("utf-8")).hexdigest()[:12]


ENV_HASH = _env_hash()
