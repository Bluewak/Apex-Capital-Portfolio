"""Compliance Guardrail (M5): RiskReport+profile → 차단/강등/통과 (03 §4, 05 §3).

성향별 상한 초과 시 강등→재계산. 최대 3회 강등 후 안정형 확정(08 §4). 미구현 — 08 §3 M5.
"""
from __future__ import annotations
