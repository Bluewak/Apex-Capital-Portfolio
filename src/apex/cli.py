"""Apex CLI (프론트 = 명령줄). 진입점 `apex` (pyproject [project.scripts])."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from apex import __version__, pipeline
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


def _run_and_write(
    answers: SurveyAnswers, currency: str, out: str, source: str = "synthetic"
) -> int:
    res = pipeline.run(answers, currency=currency, source=source)
    _summarize(res)
    out_path = Path(out).with_suffix(".json")
    out_path.write_text(res.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"산출물(JSON): {out_path}")
    return 0 if res.decision == "ok" else 2  # hold=2 (null-allocation exit code, 08 §7)


@app.command()
def version() -> None:
    """버전 출력."""
    typer.echo(f"apex {__version__}")


@app.command()
def run(
    input_path: str = typer.Option(..., "--input", help="설문 응답 JSON 경로 (06 §3.1)"),
    currency: str = typer.Option("krw", "--currency", help="표시 통화 krw|usd (기본 krw, D4)"),
    out: str = typer.Option("result.json", "--out", help="산출물 경로"),
    real: bool = typer.Option(False, "--real", help="실 20년 스냅샷 사용(M5). 기본은 합성"),
) -> None:
    """E2E: 설문→성향→배분→백테스트→리스크→컴플라이언스(강등 루프)→요약."""
    answers = SurveyAnswers(**json.loads(Path(input_path).read_text(encoding="utf-8")))
    src = "real" if real else "synthetic"
    raise typer.Exit(code=_run_and_write(answers, currency.upper(), out, source=src))


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
