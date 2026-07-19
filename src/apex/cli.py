"""Apex CLI (프론트 = 명령줄). 진입점 `apex` (pyproject [project.scripts])."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import typer

from apex import __version__, pipeline, store
from apex import currency as ccy
from apex.schemas import SurveyAnswers

app = typer.Typer(
    help="Apex Capital Portfolio — 분석형 포트폴리오 리포트 CLI",
    no_args_is_help=True,
)


def _summarize(res: pipeline.PipelineResult) -> None:
    typer.echo(f"성향: {res.final_profile} (위험점수 {res.risk_score}) · 결정: {res.decision}")
    for step in res.downgrade_path:
        typer.echo(f"  ↓ {step}")
    typer.echo(res.explanation)
    typer.echo(f"[재현성 해시] {res.result_hash[:16]}… · 데이터버전 {res.data_version}")


def _write_result(res, answers: SurveyAnswers, currency: str, out: str, source: str) -> int:
    """산출물 요약·원장 봉인·파일 기록. pipeline.run/serving.run_advice 공용."""
    _summarize(res)
    # 서빙 계층에서만 원장 봉인(엔진은 순수, v2 §3.6)
    rec = store.append_run(res, answers, source, currency, datetime.now(UTC).isoformat())
    typer.echo(f"[원장] run_id {rec.run_id} → {store.LEDGER}")
    out_path = Path(out)
    if out_path.suffix.lower() == ".html":
        from apex import report

        out_path.write_text(report.render(res, answers), encoding="utf-8")
    else:
        out_path = out_path.with_suffix(".json")
        out_path.write_text(res.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"산출물: {out_path}")
    return 0 if res.decision == "ok" else 2  # hold=2 (null-allocation exit code, 08 §7)


def _run_and_write(
    answers: SurveyAnswers, currency: str, out: str, source: str = "synthetic"
) -> int:
    res = pipeline.run(answers, currency=currency, source=source)
    return _write_result(res, answers, currency, out, source)


@app.command()
def version() -> None:
    """버전 출력."""
    typer.echo(f"apex {__version__}")


@app.command()
def run(
    input_path: str = typer.Option(..., "--input", help="설문 응답 JSON 경로 (06 §3.1)"),
    currency: str = typer.Option("krw", "--currency", help="표시 통화 krw|usd (기본 krw, D4)"),
    out: str = typer.Option("report.html", "--out", help="산출물 경로(.html→리포트, 그 외→JSON)"),
    real: bool = typer.Option(False, "--real", help="실 20년 스냅샷 사용(M5). 기본은 합성"),
) -> None:
    """E2E: 설문→성향→배분→백테스트→리스크→컴플라이언스(강등 루프)→요약."""
    answers = SurveyAnswers(**json.loads(Path(input_path).read_text(encoding="utf-8")))
    src = "real" if real else "synthetic"
    raise typer.Exit(code=_run_and_write(answers, ccy.normalize(currency), out, source=src))


@app.command()
def replay(
    run_id: str = typer.Option(..., "--run-id", help="원장 run_id 또는 numeric_hash 접두"),
) -> None:
    """원장에서 입력·버전을 복원해 재실행 → numeric_hash 대조(v2 §3.6 재현성 증명).

    '재현성'을 주장이 아니라 실행 명령으로. 일치=exit 0, 불일치(표류)=exit 3.
    """
    rec = store.find(run_id)
    if rec is None:
        typer.echo(f"원장에 run_id={run_id} 없음 ({store.LEDGER})")
        raise typer.Exit(code=1)
    answers = SurveyAnswers(**rec.answers)
    res = pipeline.run(answers, currency=rec.display_currency, source=rec.source)
    match = res.numeric_hash == rec.numeric_hash
    typer.echo(f"run_id {rec.run_id} · source {rec.source} · data {rec.data_version}")
    typer.echo(f"  원장 numeric_hash: {rec.numeric_hash[:16]}…")
    typer.echo(f"  재실행 numeric_hash: {res.numeric_hash[:16]}…")
    if match:
        typer.echo("재현 일치 ✓ (수치 산출 동일)")
    else:
        typer.echo("재현 불일치 ✗ — 데이터/코드/환경 표류 가능(env_hash·data_version 확인)")
    raise typer.Exit(code=0 if match else 3)


@app.command()
def advise(
    input_path: str = typer.Option(..., "--input", help="설문 응답 JSON 경로"),
    currency: str = typer.Option("krw", "--currency", help="표시 통화 krw|usd"),
    out: str = typer.Option("report.html", "--out", help="산출물 경로(.html→리포트, 그 외→JSON)"),
) -> None:
    """서빙(v2 §3.3): 사전연산 레지스트리 O(1) 조회 + forward-binding compliance E2E.

    `apex model build`로 레지스트리를 먼저 생성해야 함(핀 우선). 20년 백테스트 미반복.
    """
    from apex import serving
    from apex.serving import AdviceCommand

    answers = SurveyAnswers(**json.loads(Path(input_path).read_text(encoding="utf-8")))
    ccy_n = ccy.normalize(currency)
    res = serving.run_advice(AdviceCommand(answers=answers, display_currency=ccy_n))
    raise typer.Exit(code=_write_result(res, answers, ccy_n, out, "advice"))


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
) -> None:
    """웹 브리지(v2 §7): 설문 폼 제출 → run_advice → HTML 리포트 즉시 반환(무터미널)."""
    from apex import web

    typer.echo(f"Apex 웹 브리지 · http://{host}:{port}  (Ctrl+C 종료)")
    web.serve(host, port)


portfolio_app = typer.Typer(help="포트폴리오 (M5): 07§7 포트↔상한 사전검증 게이트")
app.add_typer(portfolio_app, name="portfolio")


@portfolio_app.command("gate")
def portfolio_gate(
    start: str = typer.Option("2005-01-01", "--start", help="백테스트 시작일"),
) -> None:
    """07§7 게이트: 5종 고정포트를 실 20년으로 백테스트해 평시 상한 통과 판정(M5 DoD)."""
    from apex import gate

    res = gate.run(start=start)
    typer.echo(f"기간 {res['period'][0]}~{res['period'][1]} ({res['n_days']}일)\n")
    typer.echo(
        f"{'성향':8s} {'평시vol':>7s} {'평시MDD':>7s} {'평시VaR':>7s} {'상한':>5s} {'차단':>4s} "
        f"{'CAGR':>6s}  스트레스(08/20/22)"
    )
    for r in res["rows"]:
        mark = "OK" if r.passed else "FAIL"
        st = "/".join(f"{r.stress[k] * 100:.0f}%" for k in ("2008", "2020", "2022"))
        typer.echo(
            f"{r.profile:8s} {r.vol * 100:6.1f}% {r.mdd_normal * 100:6.1f}% "
            f"{r.var_annual * 100:6.1f}% {r.lim['var'] * 100:4.0f}% {mark:>4s} "
            f"{r.cagr_full * 100:5.1f}%  {st}"
        )
    typer.echo("\n벤치마크:")
    for name, b in res["benchmarks"].items():
        if "error" in b:
            typer.echo(f"  {name}: ERROR {b['error']}")
        else:
            typer.echo(
                f"  {name:26s} CAGR {b['cagr'] * 100:5.1f}%  vol {b['vol'] * 100:4.1f}%  "
                f"Sharpe {b['sharpe']:.2f}  MDD {b['mdd'] * 100:.0f}%"
            )
    all_pass = all(r.passed for r in res["rows"])
    typer.echo(f"\n07§7 게이트 전원 통과(VaR 바인딩): {all_pass}")
    raise typer.Exit(code=0 if all_pass else 1)


data_app = typer.Typer(help="데이터 스냅샷 (M4/M4.5): raw 수집·content-hash 피닝·TR 대사")
app.add_typer(data_app, name="data")


@data_app.command("pull")
def data_pull(
    start: str = typer.Option("2005-01-01", "--start", help="수집 시작일"),
    tol: float = typer.Option(0.0020, "--tol", help="대사 허용 연율 편차(기본 20bp)"),
    no_pin: bool = typer.Option(False, "--no-pin", help="artifacts 피닝 생략"),
) -> None:
    """9슬롯+벤치마크 raw 수집 → 로컬 TR 재계산 → Adj Close와 대사(M4.5 DoD)."""
    from apex.data import snapshot

    res = snapshot.pull(start=start, tol_annual=tol, pin=not no_pin)
    typer.echo(f"{'ticker':10s} {'rows':>6s} {'ann_dev':>10s} {'max_daily':>10s}  결과")
    all_pass = True
    for t, r in res.items():
        rc = r.get("recon")
        if rc is None:
            typer.echo(f"{t:10s} {'EMPTY':>6s}")
            all_pass = False
            continue
        mark = "OK" if rc.passed else "FAIL"
        all_pass = all_pass and rc.passed
        typer.echo(f"{t:10s} {r['rows']:6d} {rc.ann_dev:10.5f} {rc.max_daily_abs:10.5f}  {mark}")
    typer.echo(f"\n대사 전원 통과: {all_pass}")
    raise typer.Exit(code=0 if all_pass else 1)


@data_app.command("rates")
def data_rates(
    start: str = typer.Option("2005-01-01", "--start", help="수집 시작일"),
    no_pin: bool = typer.Option(False, "--no-pin", help="artifacts 피닝 생략"),
) -> None:
    """FRED에서 무위험금리(USD/KRW 3M)·환율(원/달러) 수집·피닝(§3.1, 하드코딩 rf 제거)."""
    from apex.data import rates

    r = rates.pull_rates(start=start, pin=not no_pin)
    typer.echo(
        f"USD rf {r['usd_rf'] * 100:.2f}% · KRW rf {r['krw_rf'] * 100:.2f}% · "
        f"원/달러 {r['fx_krwusd']:.0f} · 기간 {r['period'][0]}~{r['period'][1]}"
    )
    typer.echo(f"rates_version {r['rates_version']}")


@data_app.command("golden")
def data_golden(
    start: str = typer.Option("2010-01-01", "--start", help="대사 시작일"),
    no_pin: bool = typer.Option(False, "--no-pin", help="artifacts 피닝 생략"),
) -> None:
    """골든 대사(§3.1): 독립 계보(FDR Naver/KRX·2nd-vendor)와 가격피드 대조 → 자기참조 탈출."""
    from apex.data import golden

    res = golden.pull_golden(start=start, pin=not no_pin)
    typer.echo(f"golden_version {res['golden_version']}")
    typer.echo(f"{'ticker':10s} {'ann_dev':>8s} {'통과':>5s}  계보")
    for r in res["rows"]:
        if "error" in r:
            typer.echo(f"{r['ticker']:10s}     ERROR")
            continue
        typer.echo(
            f"{r['ticker']:10s} {r['ann_dev'] * 100:7.2f}% {str(r['passed']):>5s}  {r['lineage']}"
        )
    n_pass = sum(1 for r in res["rows"] if r.get("passed"))
    typer.echo(f"\n독립 대사 통과 {n_pass}/{len(res['rows'])}")


@data_app.command("membership")
def data_membership(
    no_pin: bool = typer.Option(False, "--no-pin", help="artifacts 피닝 생략"),
) -> None:
    """S&P500 종목 → 세부테마/테마군 분류·피닝(E1): 개별종목을 KG에 연결."""
    from collections import Counter

    from apex.data import membership

    res = membership.pull_membership(pin=not no_pin)
    mapped = sum(1 for v in res["stocks"].values() if v["mapped"])
    typer.echo(
        f"membership_version {res['membership_version']} · "
        f"종목 {res['n']} · 분류 {mapped}/{res['n']}"
    )
    for g, n in Counter(v["theme_group"] for v in res["stocks"].values()).most_common():
        typer.echo(f"  {g:8s} {n}")


@data_app.command("holdings")
def data_holdings(
    no_pin: bool = typer.Option(False, "--no-pin", help="artifacts 피닝 생략"),
) -> None:
    """ETF 상위 보유종목 수집·피닝(E3): ETF 포트 → 종목/테마 룩스루."""
    from apex.data import holdings

    h = holdings.pull_holdings(pin=not no_pin)
    typer.echo(f"holdings_version {h['holdings_version']}")
    for etf, hh in h["holdings"].items():
        top = " ".join(f"{s}{w * 100:.0f}" for s, w in list(hh.items())[:3])
        typer.echo(f"  {etf:10s} 보유 {len(hh):2d}종  {top}")


model_app = typer.Typer(help="Model Plane (M-v2): CMA→Optimizer 사전연산 레지스트리")
app.add_typer(model_app, name="model")


@model_app.command("build")
def model_build(
    start: str = typer.Option("2005-01-01", "--start", help="CMA·백테스트 시작일"),
) -> None:
    """피닝 스냅샷→CMA→Optimizer로 5성향×min_cash 사전연산 레지스트리 생성·저장(§3.2)."""
    from apex import registry

    reg = registry.build_from_pinned(start)
    path = registry.save(reg)
    typer.echo(f"CMA {reg.cma_version} · model {reg.model_version} · data {reg.data_version}")
    typer.echo(f"{'성향':8s} {'min$':>5s} {'fwd손실':>7s} {'fwdvol':>7s} {'실현VaR':>7s} 상위배분")
    for e in reg.entries:
        top = " ".join(
            f"{t}{w * 100:.0f}"
            for t, w in sorted(e.allocation.weights.items(), key=lambda x: -x[1])[:3]
        )
        rv = (
            f"{e.realized.var95_annual * 100:5.1f}%"
            if e.realized is not None else "  —  "
        )
        typer.echo(
            f"{e.profile.value:8s} {e.min_cash * 100:4.0f}% "
            f"{e.forward.expected_loss_1y * 100:6.1f}% "
            f"{e.forward.vol * 100:6.1f}% {rv:>7s} {top}"
        )
    typer.echo(f"\n엔트리 {len(reg.entries)}칸 저장: {path}")


@app.command()
def demo(
    case: str = typer.Option("retiree", "--case", help="retiree|aggressive|hold"),
) -> None:
    """내장 페르소나로 스켈레톤 시연(파일 없이). M4 DoD 확인용."""
    cases = {
        "retiree": dict(
            q1_age=62, q2_horizon=3, q3_objective="보전", q6_max_loss=-0.05,
            q7_experience="없음", q8_liquidity="보통", q9_fx="회피", q10_behavior="매도",
        ),
        "aggressive": dict(
            q1_age=29, q2_horizon=5, q3_objective="증식", q6_max_loss=-0.15,
            q7_experience="많음", q8_liquidity="낮음", q9_fx="일부허용", q10_behavior="추가매수",
        ),
        "hold": dict(
            q1_age=70, q2_horizon=2, q3_objective="보전", q6_max_loss=-0.015,
            q7_experience="없음", q8_liquidity="보통", q9_fx="회피", q10_behavior="매도",
        ),
    }
    if case not in cases:
        typer.echo(f"알 수 없는 case: {case} (retiree|aggressive|hold)")
        raise typer.Exit(code=1)
    base = dict(q4_capital=1, q5_monthly=0, input_snapshot_id=f"demo-{case}")
    answers = SurveyAnswers(**{**base, **cases[case]})
    res = pipeline.run(answers)
    _summarize(res)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
