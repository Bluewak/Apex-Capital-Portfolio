"""Apex CLI (프론트 = 명령줄). 진입점 `apex` (pyproject [project.scripts])."""
from __future__ import annotations

import typer

from apex import __version__

app = typer.Typer(
    help="Apex Capital Portfolio — 분석형 포트폴리오 리포트 CLI",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """버전 출력."""
    typer.echo(f"apex {__version__}")


@app.command()
def run(
    input_path: str = typer.Option(..., "--input", help="설문 응답 JSON 경로 (06 §3.1)"),
    currency: str = typer.Option("krw", "--currency", help="표시 통화 krw|usd (기본 krw, D4)"),
    out: str = typer.Option("report.html", "--out", help="리포트 출력 경로"),
) -> None:
    """E2E 파이프라인: 설문→성향→IPS→배분→백테스트→리스크→컴플라이언스→리포트.

    현재는 스캐폴딩 단계로 미구현(M4~M6에서 구현). docs/08-dev-plan.md 참조.
    """
    typer.echo("apex run: 파이프라인 미구현 (스캐폴딩 단계). 계획: docs/08-dev-plan.md")
    raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
