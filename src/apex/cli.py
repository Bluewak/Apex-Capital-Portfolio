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


def _run_and_write(answers: SurveyAnswers, currency: str, out: str) -> int:
    res = pipeline.run(answers, currency=currency)
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
) -> None:
    """E2E(M4 스켈레톤): 설문→성향→배분→백테스트→리스크→컴플라이언스(강등 루프)→요약."""
    answers = SurveyAnswers(**json.loads(Path(input_path).read_text(encoding="utf-8")))
    raise typer.Exit(code=_run_and_write(answers, currency.upper(), out))


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
