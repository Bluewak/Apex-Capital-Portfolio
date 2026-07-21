"""S&P500 2계보 교차검증 (v3-A Step 0) — GitHub as-of·Jaccard·kill-switch 통합. 네트워크 없음."""
from __future__ import annotations

from apex.data import membership_crosscheck as cc
from apex.data import membership_pit as mp


def _cur(date_added):
    return {"cik": "1", "name": "X", "sector": "", "sub": "", "date_added": date_added}


_GH = [
    {"date": "2000-01-01", "tickers": ["AAA", "BBB"]},
    {"date": "2018-06-01", "tickers": ["AAA", "CCC"]},  # BBB out, CCC in
]


def test_github_members_asof_step_function():
    assert cc.members_asof(_GH, "2010-05-05") == {"AAA", "BBB"}  # 첫 행 이후
    assert cc.members_asof(_GH, "2018-06-01") == {"AAA", "CCC"}  # 두번째 행 당일
    assert cc.members_asof(_GH, "1999-01-01") == set()          # 첫 행 이전


def test_github_ticker_normalization_on_load(monkeypatch):
    """CSV 파싱 시 BRK.B → BRK-B 정규화(위키측과 매칭 일관)."""
    assert cc._norm("brk.b") == "BRK-B"


def test_authoritative_counts_uses_github():
    counts = cc.authoritative_counts(_GH, grid=["2010-12-31", "2020-12-31"])
    assert counts == {"2010-12-31": 2, "2020-12-31": 2}


def test_crosscheck_agrees_when_sources_match():
    pit = mp.reconstruct({"AAA": _cur("2000-01-01")}, [])
    gh = [{"date": "2000-01-01", "tickers": ["AAA"]}]
    out = cc.crosscheck(pit, gh, grid=["2023-12-31", "2024-12-31", "2025-12-31"])
    assert out["passed"] is True
    assert out["recent_min_jaccard"] == 1.0
    assert all(v["jaccard"] == 1.0 for v in out["per_date"].values())


def test_crosscheck_flags_disagreement():
    pit = mp.reconstruct({"AAA": _cur("2000-01-01")}, [])  # 위키: AAA만
    gh = [{"date": "2000-01-01", "tickers": ["AAA", "ZZZ"]}]  # GitHub: AAA+ZZZ
    out = cc.crosscheck(pit, gh, grid=["2024-12-31", "2025-12-31"])
    assert out["passed"] is False  # Jaccard 0.5 < 0.97
    d = out["per_date"]["2025-12-31"]
    assert d["mine_missing"] == 1 and d["n_github"] == 2


def test_kill_switch_greens_two_bars_with_github_and_crosscheck():
    """GitHub 권위 카운트 + 통과 교차검증 → 구성원수·2계보 바 GREEN(verdict는 forward_only 유지)."""
    pit = mp.reconstruct({"AAA": _cur("2000-01-01")}, [])
    auth = {f"{y}-12-31": 500 for y in range(2006, 2026)}
    ccheck = {"passed": True, "recent_min_jaccard": 0.99, "threshold": 0.97, "github_sha": "abc123"}
    gate = mp.kill_switch_gate(pit, [], crosscheck=ccheck, authoritative_counts=auth)
    bars = gate["bars"]
    assert bars["membership_count_invariant"]["passed"] is True
    assert bars["membership_count_invariant"]["source"] == "github_authoritative"
    assert bars["source_lineage"]["passed"] is True
    assert bars["source_lineage"]["github_sha"] == "abc123"
    # 아직 상장폐지수익·PIT재무 미구축 → 정직하게 forward_only
    assert gate["verdict"] == "forward_only"


def test_load_github_empty_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(cc, "GH_PATH", tmp_path / "none.json")
    assert cc.load_github_constituents() == {}
