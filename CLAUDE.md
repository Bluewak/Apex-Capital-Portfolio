# CLAUDE.md — Apex Capital Portfolio

투자자 설문 → IPS → 자산배분 → 백테스트 → 리스크 → 설명 리포트를 자동 생성하는 **분석형** 포트폴리오 리포트 서비스. 실주문·일임 없음.

## 지금 어디인가

**v2 Step 0~3 전부 완료 · 4평면(Data·Model·Serving·Advisory)+Run Ledger 구현(pytest 95).**
잔여는 선택·비차단(골든 대사·FX 실소싱·DSR/PBO·핀 커밋·LLM Narrator 실교체).
어떤 작업이든 **착수 전 아래 두 문서를 먼저 읽고 방향을 정합**한다:

- **방향성 북극성 → [docs/11-direction.md](docs/11-direction.md)** — why/direction + 절대 가드레일(§5) + 워치리스트. **v2 작업 전 §5 필독.**
- **v2 설계(how) → [docs/10-v2-pipeline-design.md](docs/10-v2-pipeline-design.md)** — 4평면·SPI·착수 스텝(§9).
- 배경: [docs/00-INDEX.md](docs/00-INDEX.md)(전체 인덱스) · [08 v1 실행계획](docs/08-dev-plan.md) · [05 리스크](docs/05-risk-metrics.md).

## 절대 깨면 안 되는 것 (상세·근거는 docs/11 §5 — 대부분 CI 게이트로 강제)

1. **AI는 배분·판정 금지.** 코어 모듈(`investor`/`optimizer`/`allocation`/`risk`/`compliance`, `DETERMINISM_REQUIRED=True`)은 `apex.advisory`·`anthropic` import 금지. LLM은 Narrator(자문 평면)에만.
2. **`numeric_result_hash`에 서술(LLM) 포함 금지.** 숫자·판정만 해시; `narrative_hash`는 분리.
3. **핀 우선 서빙.** 런타임은 피닝 스냅샷만(핀 부재 시 하드 실패). 라이브 수집은 `apex data pull`만.
4. **계약 우선.** 경계는 pydantic/Protocol로만. 전 산출물에 `(schema_version, data_version, model_version, env_hash)` 각인.
5. **강등 역간선은 1급 타입**(`RevisedProfile`), 루프 소유=pipeline, 종료 유한(수렴 or "배정 보류"). 문자열 성향 반환 금지.
6. **규제 경계.** 실주문·일임 없음 · "예시 모델포트폴리오" 프레이밍 · 개인지시형 금지 · PII 밴드화 · 면책 렌더 필수.
7. **폭 금지(v3로).** 개별종목·세금·이중통화 전량 재계산·RL은 v2 Step 0~3에 넣지 않는다.
8. **재현성 2체크포인트.** 핀 스냅샷 하 별도 2프로세스 `numeric_hash` 동일 + `rtol≤1e-6`.

## 스택 · 실행

Python 3.12 · **uv** · pydantic v2(계약) · pandas/numpy · yfinance/FRED/ECOS/Stooq · Jinja2 · Typer(CLI) · pytest/ruff.

```bash
uv sync
uv run apex --help
uv run pytest
uv run ruff check .
```

## 구조 (06 컴포넌트 → 모듈)

`src/apex/`: `schemas/`(계약) · `data/`(수집·splice·캐시) · `investor/` · `ips/` · `allocation/` · `backtest/` · `risk/` · `compliance/`(가드레일·강등 루프) · `report/` · `metrics/`(공유 커널) · `currency.py` · `pipeline.py`(오케스트레이터) · `cli.py`.
