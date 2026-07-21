"""S&P500 PIT 리컨스트럭터 (v3-A Step 0) — 다구간 복원·좌측절단·사유분류. 네트워크 없음(픽스처)."""
from __future__ import annotations

from apex.data import membership_pit as mp


def _cur(date_added=None, cik="1"):
    return {"cik": cik, "name": "X", "sector": "", "sub": "", "date_added": date_added}


def test_current_member_no_changes_uses_date_added():
    """편입일자 있는 현행종목 = 단일 열린 구간, 좌측절단 아님."""
    pit = mp.reconstruct({"AAA": _cur("2000-01-01")}, [])
    ivs = pit["AAA"]["intervals"]
    assert ivs == [{"in": "2000-01-01", "out": None, "left_censored": False}]
    assert pit["AAA"]["status"] == "current"


def test_current_member_no_date_added_is_left_censored():
    pit = mp.reconstruct({"BBB": _cur(None)}, [])
    assert pit["BBB"]["intervals"] == [{"in": None, "out": None, "left_censored": True}]


def test_reentry_preserves_two_intervals_without_anomaly():
    """재편입 현행종목(AMD형): 옛 구간은 좌측절단, 현재 구간은 편입일자. out<in 없음."""
    current = {"AMD": _cur("2017-03-20")}
    changes = [
        {"date": "2017-03-20", "add": "AMD", "remove": None, "reason": ""},
        {"date": "2013-09-20", "add": None, "remove": "AMD", "reason": "market cap change"},
    ]
    ivs = mp.reconstruct(current, changes)["AMD"]["intervals"]
    assert len(ivs) == 2
    # 정렬: 옛 구간(좌측절단) 먼저, 현재 구간 나중
    assert ivs[0] == {"in": None, "out": "2013-09-20", "out_reason": "rebalance",
                      "left_censored": True}
    assert ivs[1] == {"in": "2017-03-20", "out": None, "left_censored": False}
    # 핵심 불변식: 어떤 구간도 out < in 이 아니다(과거 버그)
    for iv in ivs:
        if iv["in"] and iv["out"]:
            assert iv["out"] >= iv["in"]


def test_removed_member_left_censored_with_reason():
    changes = [{"date": "2011-02-25", "add": None, "remove": "OLD", "reason": "acquired by ACME"}]
    pit = mp.reconstruct({}, changes)
    assert pit["OLD"]["status"] == "removed"
    assert pit["OLD"]["intervals"] == [
        {"in": None, "out": "2011-02-25", "out_reason": "ma", "left_censored": True}]


def test_classify_reason():
    assert mp.classify_reason("Acquired by Broadcom") == "ma"
    assert mp.classify_reason("Chapter 11 bankruptcy") == "bankruptcy"
    assert mp.classify_reason("Market cap too small") == "rebalance"
    assert mp.classify_reason("") == "other"


def test_members_asof_respects_intervals():
    current = {"AMD": _cur("2017-03-20")}
    changes = [
        {"date": "2017-03-20", "add": "AMD", "remove": None, "reason": ""},
        {"date": "2013-09-20", "add": None, "remove": "AMD", "reason": "market cap change"},
    ]
    pit = mp.reconstruct(current, changes)
    assert "AMD" in mp.members_asof(pit, "2012-01-01")   # 옛 구간(좌측절단, out까지)
    assert "AMD" not in mp.members_asof(pit, "2015-01-01")  # 편출~재편입 사이
    assert "AMD" in mp.members_asof(pit, "2020-01-01")   # 현재 구간


def test_no_out_before_in_invariant_on_synthetic():
    """합성 다케이스에서 out<in 이상치 0 (coverage_report 불변식)."""
    current = {"CUR": _cur("2005-05-05")}
    changes = [
        {"date": "2020-01-01", "add": "CUR", "remove": "GONE", "reason": "Acquired"},
        {"date": "2010-06-06", "add": None, "remove": "CUR", "reason": "float"},
    ]
    pit = mp.reconstruct(current, changes)
    cov = mp.coverage_report(pit, changes)
    assert cov["n_anomaly_out_before_in"] == 0


def test_kill_switch_forward_only_when_bars_missing():
    """상장폐지수익·PIT재무·2계보 미구축 → verdict='forward_only'(정직한 격하)."""
    pit = mp.reconstruct({"AAA": _cur("2000-01-01")}, [])
    gate = mp.kill_switch_gate(pit, [])
    assert gate["verdict"] == "forward_only"
    assert gate["bars"]["delisting_return_coverage"]["passed"] is False


def test_load_pit_empty_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(mp, "PIT_PATH", tmp_path / "none.json")
    assert mp.load_membership_pit() == {}
