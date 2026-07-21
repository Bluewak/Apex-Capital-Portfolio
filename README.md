# Apex Capital Portfolio

투자자 설문 → **IPS · 자산배분 · 백테스트 · 리스크 · 설명 리포트**를 자동 생성하는 **분석형**
포트폴리오 리포트 서비스. 실주문·일임 없음 — "예시 모델포트폴리오"의 교육·분석 정보. KRW 표시·USD 계산.

> **상태: v2 완료** — 4평면(Data·Model·Serving·Advisory) + Run Ledger. 결정론 코어·재현성·규제
> 가드레일이 코드·CI·테스트로 실체화. `pytest 136 · ruff clean`.

## 방향 문서 (착수 전 필독)

- **북극성(why) → [docs/11-direction.md](docs/11-direction.md)** — 방향성 + **절대 가드레일 §5** + 워치리스트.
- **v2 설계(how) → [docs/10-v2-pipeline-design.md](docs/10-v2-pipeline-design.md)** — 4평면·SPI·착수 스텝.
- 전체 인덱스 → [docs/00-INDEX.md](docs/00-INDEX.md) · KG/온톨로지 → [docs/12](docs/12-knowledge-graph-compliance.md).

## 아키텍처 — 4 평면 + Run Ledger

무거운 결정론 계산은 오프라인 배치로 내리고, 사용자 런은 O(1) 조회+판정만, LLM은 완전 격리.

| 평면 | 시점 | 역할 | 모듈 |
| -- | -- | -- | -- |
| ① Data | 오프라인·핀당 1회 | 핀 수집·**골든 대사**(발행사 독립 계보)·FX/금리 실소싱·KG 소속 | `data/`(snapshot·loader·adjust·rates·golden·membership·holdings)·`graph` |
| ② Model | 오프라인 배치 | **CMA**(빌딩블록 μ+Ledoit-Wolf Σ)→**Optimizer**(결정론 MVO)→사전연산 그리드·검증게이트 | `cma`·`optimizer`·`forward`·`validation`·`registry` |
| ③ Serving | 온라인·결정론 | `run_advice`(레지스트리 O(1)·강등 루프·**forward-binding** compliance)·FactLedger·numeric_hash | `serving`·`compliance`·`risk`·`allocation`·`investor`·`factledger` |
| ④ Advisory | 온라인·비결정론 | Narrator(룰/로컬 LLM)·자문 게이트·캐시·룰 폴백 — **LLM은 여기에만** | `advisory`(RuleNarrator·QwenNarrator) |
| ⑤ Run Ledger | 상시 | append-only 해시체인 원장 · `apex replay` 재현 | `store` |

공유 계약은 `schemas/`(pydantic), 오케스트레이터는 `pipeline`(레거시)·`serving`(레지스트리), 진입점은 `cli`·`web`.

## 절대 가드레일 (docs/11 §5 · 대부분 CI 게이트)

1. **AI는 배분·판정 금지** — 결정론 코어(`DETERMINISM_REQUIRED=True`)는 `apex.advisory`·`anthropic` 미import(AST 검사).
2. **`numeric_result_hash`에 서술 미포함** — `NumericResult`만 해시, `Narrative`는 분리.
3. **핀 우선 서빙** — 런타임은 피닝 스냅샷만(부재 시 하드 실패). 라이브는 `apex data …`에서만.
4. **계약 우선** — 전 산출물에 `(schema/data/model/env)_version` 각인. 재현성 2체크포인트(`apex replay`).

## 빠른 시작

```bash
uv sync                                   # .venv + 의존성 + 잠금
uv run pytest                             # 테스트(136)
uv run ruff check .                       # 린트

uv run apex data pull                     # ETF raw 스냅샷 수집·content-hash 피닝 + TR 대사
uv run apex data rates                    # FRED 무위험금리·환율 피닝
uv run apex data golden                   # 독립 계보(FDR) 골든 대사(TR 정합)
uv run apex data membership               # S&P500 → 세부테마/테마군 KG 소속
uv run apex data holdings                 # ETF 보유종목 룩스루
uv run apex model build                   # CMA→Optimizer 5성향×min_cash 사전연산 레지스트리

uv run apex advise --input examples/answers.sample.json --out report.html   # 서빙(레지스트리 O(1))
uv run apex run  --input examples/answers.sample.json --real                # 레거시 파이프라인
uv run apex replay --run-id <id>          # 원장 복원 재실행 → numeric_hash 대조
uv run apex serve                         # 무터미널 웹 브리지(설문 폼 → 리포트)
uv run apex portfolio gate                # 07§7 성향별 상한 사전검증
```

> Windows 콘솔(cp949)에서 CLI 실행 시 `PYTHONUTF8=1` 권장(터미널 인코딩 한계·코드 무관).

## 스택

Python 3.12 · **uv** · pydantic v2(계약) · pandas/numpy(순수 numpy 결정론, scipy 미사용) ·
yfinance / FRED(pandas-datareader) / FinanceDataReader · Jinja2 · Typer(CLI, stdlib 웹 브리지) · pytest/ruff.

로컬 LLM Narrator(선택): [Ollama](https://ollama.com) + Qwen2.5-7B(Apache-2.0). 미실행 시 룰 템플릿 폴백.
