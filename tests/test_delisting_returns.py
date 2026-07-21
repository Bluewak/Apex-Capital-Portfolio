"""편출 종료수익 근사 (v3-A Step 0) — 사유매핑·교체가능 provenance·provisional verdict."""
from __future__ import annotations

from apex.data import delisting_returns as dr
from apex.data import membership_pit as mp

_PIT = {
    "MA1": {"status": "removed", "intervals": [
        {"in": "2005-01-01", "out": "2015-06-01", "out_reason": "ma"}]},
    "BK1": {"status": "removed", "intervals": [
        {"in": None, "out": "2008-09-16", "out_reason": "bankruptcy", "left_censored": True}]},
    "RB1": {"status": "removed", "intervals": [
        {"in": "2010-01-01", "out": "2020-01-01", "out_reason": "rebalance"}]},
    "CUR": {"status": "current", "intervals": [
        {"in": "2000-01-01", "out": None, "left_censored": False}]},
    "RE1": {"status": "current", "intervals": [  # 재편입: 과거 편출 1건 존재
        {"in": None, "out": "2013-01-01", "out_reason": "rebalance", "left_censored": True},
        {"in": "2017-01-01", "out": None, "left_censored": False}]},
}


def test_build_assigns_terminal_return_by_reason_with_provenance():
    r = dr.build_delisting_returns(_PIT)
    assert r["MA1@2015-06-01"]["terminal_return"] == 0.0     # 인수가 ≈ 시장가
    assert r["BK1@2008-09-16"]["terminal_return"] == -1.0    # 파산 총손실
    assert r["RB1@2020-01-01"]["terminal_return"] == 0.0     # 리밸 계속거래
    for e in r.values():  # 전부 교체가능 표식
        assert e["is_approximation"] is True and e["replaceable"] is True
        assert e["source"] == "reason_heuristic" and e["method"].startswith("approx_")


def test_current_ticker_open_interval_has_no_exit_but_reentry_exit_counted():
    r = dr.build_delisting_returns(_PIT)
    assert "CUR@" not in " ".join(r)          # 현재까지 보유 → 종료 없음
    assert "RE1@2013-01-01" in r               # 재편입 과거 편출은 종료수익 있음


def test_coverage_report_full_with_confidence_breakdown():
    cov = dr.coverage_report(dr.build_delisting_returns(_PIT))
    assert cov["n_exits"] == 4                 # MA1·BK1·RB1·RE1(과거)
    assert cov["coverage_frac"] == 1.0
    assert cov["is_approximation"] is True
    assert cov["confidence_breakdown"]["high"] == 2   # rebalance ×2
    assert cov["confidence_breakdown"]["medium"] == 2  # ma + bankruptcy


def test_terminal_return_lookup():
    r = dr.build_delisting_returns(_PIT)
    assert dr.terminal_return(r, "BK1", "2008-09-16")["terminal_return"] == -1.0
    assert dr.terminal_return(r, "NOPE", "2000-01-01") is None


def test_delisting_bar_passes_with_coverage():
    cov = dr.coverage_report(dr.build_delisting_returns(_PIT))
    bar = mp._delisting_bar(cov)
    assert bar["passed"] is True and bar["is_approximation"] is True
    assert mp._delisting_bar(None)["passed"] is False


def test_kill_switch_backtest_ok_provisional_when_all_pass_but_approx():
    """전 바 통과 + 종료수익 근사 → verdict=backtest_ok_provisional(정직한 구분)."""
    pit = mp.reconstruct({"AAA": {"cik": "1", "name": "A", "sector": "", "sub": "",
                                  "date_added": "2000-01-01"}}, [])
    gate = mp.kill_switch_gate(
        pit, [],
        crosscheck={"passed": True, "recent_min_jaccard": 0.99, "threshold": 0.97,
                    "github_sha": "abc"},
        authoritative_counts={f"{y}-12-31": 500 for y in range(2006, 2026)},
        fundamentals_coverage={"core_coverage_frac_span_adjusted": 0.95, "n_tickers": 40},
        delisting_coverage=dr.coverage_report(dr.build_delisting_returns(_PIT)))
    assert gate["verdict"] == "backtest_ok_provisional"
    assert all(gate["bars"][k]["passed"] for k in
               ("membership_count_invariant", "source_lineage", "pit_fundamentals",
                "delisting_return_coverage"))


def test_load_empty_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(dr, "RETURNS_PATH", tmp_path / "none.json")
    assert dr.load_delisting_returns() == {}
