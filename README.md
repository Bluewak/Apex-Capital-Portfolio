# Apex Capital Portfolio

투자자 설문을 받아 **IPS → 자산배분 → 백테스트 → 리스크 리포트 → 설명 리포트**를 자동 생성하는
분석형 포트폴리오 리포트 서비스. MVP는 룰 기반·고정비중·분석리포트(실주문 없음).

- 기획·규격: [docs/00-INDEX.md](docs/00-INDEX.md) (01~08)
- 개발 실행계획: [docs/08-dev-plan.md](docs/08-dev-plan.md)

## 스택

Python 3.12 · **uv** · pydantic(계약) · pandas/numpy · yfinance/FRED/Stooq · Jinja2 · Typer(CLI) · pytest/ruff.

## 개발 환경

```bash
uv sync                 # .venv 생성 + 의존성 설치 + 잠금
uv run apex --help      # CLI
uv run pytest           # 테스트
uv run ruff check .     # 린트
```

> 로컬 참고: uv/python/node는 winget 사용자 범위 설치. 새 셸에서 PATH 반영됨.

## 구조 (06 컴포넌트 → 모듈)

```text
src/apex/
  schemas/    # 06 §3 서비스 계약 (pydantic)
  data/       # Data Layer: 수집·splice·캐시 (M4)
  investor/   # 설문 스코어링 → InvestorProfile (03)
  ips/        # IPS 렌더 (04)
  allocation/ # 고정비중 모델포트폴리오 4종 (02·03)
  backtest/   # 엔진·스트레스 시나리오 (05 §2)
  risk/       # 지표·민감도·집중도 (05 §1)
  compliance/ # 가드레일·강등 루프 (03 §4, 05 §3)
  report/     # 룰기반 자연어 리포트 (04 §2)
  currency.py # D4 통화 토글
  pipeline.py # 오케스트레이터 (06 §6)
  cli.py      # Typer 진입점
```

현재 단계: **스캐폴딩 + schemas 완료**. 다음: M4 Data Layer.
