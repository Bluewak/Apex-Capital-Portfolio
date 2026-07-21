"""네트워크 환경 보정 — 비ASCII 경로 CA 번들 우회 (Windows 한글 사용자명).

certifi CA 번들 경로에 비ASCII 문자(예: 한글 사용자명)가 있으면 curl_cffi(libcurl)가
'error setting certificate verify locations'로 SSL 실패한다(yfinance 등). ASCII 임시
경로로 복사하고 env를 설정해 우회(멱등). yfinance 요청 전에 호출.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def ensure_ascii_ca() -> None:
    """CA 번들 경로가 비ASCII면 ASCII 경로로 복사하고 SSL env 설정(멱등·no-op if ASCII)."""
    try:
        import certifi
    except ImportError:
        return
    src = certifi.where()
    if src.isascii():
        return  # 경로가 ASCII → 문제 없음
    base = os.environ.get("PUBLIC") or r"C:\Users\Public"
    dst = Path(base) / "apex_cacert.pem"
    try:
        if not dst.exists():
            shutil.copy(src, dst)
    except OSError:
        return  # 복사 실패 시 조용히 포기(원 동작 유지)
    for key in ("CURL_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        os.environ.setdefault(key, str(dst))
