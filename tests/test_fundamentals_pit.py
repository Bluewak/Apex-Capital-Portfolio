"""EDGAR PIT 재무 추출 (v3-A Step 0) — as-first-reported·look-ahead 안전·태그병합. 네트워크 없음."""
from __future__ import annotations

from apex.data import fundamentals_pit as fp
from apex.data import membership_pit as mp


def _pt(start, end, val, filed, fy, form="10-K"):
    p = {"end": end, "val": val, "filed": filed, "fy": fy, "fp": "FY", "form": form}
    if start:
        p["start"] = start
    return p


_FACTS = {
    "entityName": "Test Co",
    "facts": {"us-gaap": {
        "NetIncomeLoss": {"units": {"USD": [
            _pt("2019-10-01", "2020-09-30", 100, "2020-11-01", 2020),   # 최초 공시
            _pt("2019-10-01", "2020-09-30", 110, "2021-11-01", 2021),   # 재작성(더 늦은 filed)
            _pt("2020-07-01", "2020-09-30", 30, "2020-11-01", 2020),    # 분기(스팬 필터로 제외)
            _pt("2020-10-01", "2021-09-30", 120, "2021-11-01", 2021),
        ]}},
        "ProfitLoss": {"units": {"USD": [
            _pt("2018-10-01", "2019-09-30", 90, "2019-11-01", 2019),    # 옛 태그(병합)
        ]}},
        "StockholdersEquity": {"units": {"USD": [
            _pt(None, "2020-09-30", 500, "2020-11-01", 2020),           # instant(스팬 없음)
        ]}},
        "Revenues": {"units": {"USD": [
            _pt("2019-10-01", "2020-09-30", 1000, "2020-11-01", 2020),
        ]}},
    }},
}


def test_all_points_merges_tag_variants():
    """net_income = NetIncomeLoss + ProfitLoss 병합(태그 시기변경 대응)."""
    pts = fp._all_points(_FACTS, ["NetIncomeLoss", "ProfitLoss"], "USD")
    tags = {t for t, _ in pts}
    assert tags == {"NetIncomeLoss", "ProfitLoss"}


def test_annual_first_reported_picks_first_filed_and_flags_restatement():
    s = fp.annual_first_reported(_FACTS, "net_income")
    assert s["2020-09-30"]["val"] == 100          # as-first-reported(110 아님)
    assert s["2020-09-30"]["restated_n"] == 1      # 재작성 1회 병기
    assert "2019-09-30" in s                        # ProfitLoss 병합
    assert "2021-09-30" in s


def test_quarterly_point_filtered_by_span():
    """같은 end의 분기 값(스팬~92일)은 연간 필터(350~380일)로 제외."""
    s = fp.annual_first_reported(_FACTS, "net_income")
    assert s["2020-09-30"]["val"] in (100,)  # 분기값 30이 끼어들지 않음


def test_instant_concept_has_no_span_filter():
    s = fp.annual_first_reported(_FACTS, "equity")
    assert s["2020-09-30"]["val"] == 500


def test_value_asof_is_lookahead_safe():
    s = fp.annual_first_reported(_FACTS, "net_income")
    v = fp.value_asof(s, "2021-01-01")   # FY2021은 아직 미공시(filed 2021-11)
    assert v["end"] == "2020-09-30" and v["val"] == 100
    v2 = fp.value_asof(s, "2019-06-01")  # FY2019도 미공시(filed 2019-11)
    assert v2 is None


def test_company_core_years():
    yrs = fp.company_core_years(_FACTS)
    assert 2020 in yrs["net_income"] and 2020 in yrs["revenue"] and 2020 in yrs["equity"]


def test_fundamentals_bar_passes_above_threshold():
    assert mp._fundamentals_bar({"core_coverage_frac_span_adjusted": 0.95,
                                 "n_tickers": 40})["passed"] is True
    assert mp._fundamentals_bar({"core_coverage_frac_span_adjusted": 0.80,
                                 "n_tickers": 40})["passed"] is False
    assert mp._fundamentals_bar(None)["passed"] is False


def test_kill_switch_pit_fundamentals_green_with_coverage():
    pit = mp.reconstruct({"AAA": {"cik": "1", "name": "A", "sector": "", "sub": "",
                                  "date_added": "2000-01-01"}}, [])
    gate = mp.kill_switch_gate(
        pit, [], fundamentals_coverage={"core_coverage_frac_span_adjusted": 0.948,
                                        "n_tickers": 40})
    assert gate["bars"]["pit_fundamentals"]["passed"] is True
