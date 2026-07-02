# 08. 개발 착수 실행계획 (M4~M6)

01~07(M1~M3 기획)이 확정된 상태에서 **MVP 구현 착수**를 위한 실행 규격.
스택·프로젝트 구조·마일스톤·착수 전 결정사항·완료기준을 여기서 고정한다. (본 문서는 계획 확정본이며 코드는 미포함)

## 0. 확정 사항 (2026-07-03)

| 항목 | 확정 | 근거 |
| -- | -- | -- |
| 언어/런타임 | **Python 3.12** | D7 데이터 생태계 정합, 06 §7 |
| 패키지·환경 관리 | **uv** (pyproject + uv.lock) | 재현성·속도 |
| 프론트 형태 | **CLI 우선** → 리포트(HTML) 출력, 웹앱 후순위 | 사용자 결정 2026-07-03 |
| 계약(스키마) | **pydantic v2** | 06 §3 계약을 코드로 고정 |
| 계산 | **pandas / numpy** | 05 지표 |
| 데이터 | **yfinance**(시세·배당), **FRED**(환율·금리; `pandas-datareader` 또는 API), **Stooq** 폴백 | 02 §5, D7 |
| 리포트 | **Jinja2**(HTML) → 후에 PDF(weasyprint) | 04 §2 |
| 테스트/품질 | **pytest**, **ruff**(lint+format) | 05 §5 재현성 |

## 1. 프로젝트 구조 (06 컴포넌트 → 모듈)

src 레이아웃. 각 모듈 경계는 06 §3 계약(pydantic)으로만 소통 → 병렬 개발·교체 가능.

```text
Apex_Capital_Portfolio/
├─ pyproject.toml            # uv 프로젝트·의존성·콘솔스크립트 apex
├─ uv.lock
├─ .gitignore
├─ README.md                 # 루트 개요·실행법
├─ src/apex/
│  ├─ __init__.py
│  ├─ cli.py                 # Typer 진입점 (apex run/survey/backtest/report)
│  ├─ pipeline.py            # 오케스트레이터 (06 §6, 재계산 루프)
│  ├─ schemas/               # 06 §3 계약: InvestorProfile, Allocation, BacktestResult, RiskReport, Compliance…
│  ├─ data/                  # Data Layer: 수집·splice·캐시 (02 §5, D7)
│  ├─ investor/              # 설문 스코어링 → InvestorProfile (03)
│  ├─ ips/                   # IPS 렌더 (04)
│  ├─ allocation/            # 고정비중 모델포트폴리오 4종 (02·03)
│  ├─ backtest/              # 엔진·스트레스 시나리오 (05 §2)
│  ├─ risk/                  # 지표·민감도·집중도 (05 §1)
│  ├─ compliance/            # 가드레일·강등 루프 (03 §4, 05 §3)
│  ├─ report/               # 룰기반 자연어 리포트 + Jinja2 템플릿 (04 §2)
│  └─ currency.py            # D4 통화 토글(계산 USD, 표시 KRW/USD)
├─ tests/                    # pytest (05 §5·01 §5를 테스트로)
├─ data/                     # 로컬 캐시(파케이) — gitignore
├─ tools/sp500/              # 기존 유니버스 도구 (유지)
└─ docs/                     # 01~08
```

## 2. CLI 설계 (프론트 = 명령줄)

콘솔스크립트 `apex`. 각 단계는 독립 실행 가능하고, `apex run`이 전체를 관통한다(06 §6).

```text
apex run --input answers.json [--currency krw] [--out report.html]
    # E2E: 설문→성향→IPS→배분→백테스트→리스크→컴플라이언스→리포트 (수용기준 ≤3분)

apex survey score --input answers.json          # → InvestorProfile(JSON)
apex portfolio build --profile profile.json     # → Allocation + IPS
apex backtest run --alloc alloc.json --years 20 # → BacktestResult
apex risk report --returns series.parquet       # → RiskReport
apex data pull [--years 20]                      # 코어 8슬롯+FX+금리 캐시 갱신
```

- 입력: 설문 응답 JSON(06 §3.1 스키마). 대화형 입력은 후순위.
- 출력: 단계별 JSON 아티팩트 + 최종 HTML 리포트. 모든 산출물에 입력스냅샷·모델버전 기록(재현성, 05 §0).

## 3. 마일스톤

### M4 — Data Layer (기반)
- 코어 8슬롯 대표 티커(SPY·QQQ·EFA·EEM·IEF·TLT·SHY·GLD) **20년+ 조정종가** 수집(yfinance)
- USD/KRW 환율(FRED `DEXKOUS`), 무위험금리(USD 3M T-Bill, KRW CD) 수집
- 로컬 캐시(파케이) + **데이터 버전 태그**(재현성)
- 배당·분할 반영 확인
- **DoD**: `apex data pull`로 8슬롯×20년 결측 없이 캐시, sanity 테스트 통과

### M5 — 코어 파이프라인
- `schemas` 먼저(모든 경계 고정) → 이후 병렬:
  - investor: 03 §2 가중합 스코어링 + 03 §4 하드 가드레일
  - allocation: 성향별 고정비중 4종(안정/중립/성장/공격), 티커 매핑(02 §3)
  - backtest: 일별 수익률·CAGR·MDD 곡선, 벤치마크 3종(S&P500/60·40/KOSPI200), 스트레스 구간(2008/2020/2022)
  - risk: 05 §1 전지표(vol/MDD/VaR/CVaR/Sharpe/Calmar/민감도/집중도), 통화 2종 저장
  - compliance: 05 §3 상한 대비 차단→강등→재계산 루프
- **DoD**: 05 §5 검증 체크리스트 + 01 §5 "성향 위반 배정 0건" 테스트 통과

### M6 — 리포트 + 오케스트레이터
- IPS 문장 템플릿(04 §2) + 룰기반 설명 리포트(추천마다 자연어 1회 이상)
- D4 통화 토글(KRW 기본), 환효과 분리 표기(선택)
- `apex run` E2E 관통, HTML 리포트 출력
- **DoD**: 01 §5 수용기준 전항 충족(아래 §6)

## 4. 착수 전 결정 (제안 기본값 — 확정/반대 표시)

스캐폴딩 자체는 아래 없이 가능. 각 모듈 착수 직전 확정한다.

1. **splice 정책** (M4 전) — **제안: MVP는 splice 없이 대표 티커 실데이터만 사용.**
   코어 8슬롯 대표 티커가 모두 2004년 이전 상장이라 20년 확보됨(02 §1). 대안 티커(VOO/VEA/BND/BIL/SCHD)·지수 splice는 v2로 미룸 → 블로커 제거.
2. **최대 강등 횟수** (M5 compliance 전) — **제안: 최대 3회 강등, 실패 시 안정형 확정 + `breaches`에 사유 기록** (03 §4·06 §2 재계산 루프 종료조건).
3. **통화 기본값** — KRW(D4 확정), 계산은 USD. 추가 결정 불필요.

> 07 §7의 EM/US_TECH 상한·집중도밴드 검증, 오버레이 갱신주기는 **백테스트 튜닝 항목**으로 M5 이후 처리(스캐폴딩·초기구현 블로커 아님).

## 5. 저장소 위생 (0단계 — 스캐폴딩 시 함께)

- `.gitignore`: `.venv/`, `__pycache__/`, `*.pyc`, `data/`, `*.parquet`, `tools/sp500/*.html`, `.env`
- `pyproject.toml`(uv), `src/apex/` 뼈대, 루트 `README.md`
- 현재 커밋 안 된 문서 변경 9건 정리 커밋

## 6. 완료 기준 (01 §5 → 검증 매핑)

| 수용기준 | 검증 방법 |
| -- | -- |
| 설문→리포트 ≤ 3분 | `apex run` 실행시간 측정 테스트 |
| 2008/2020/2022 개별 성과 표시 | backtest 스트레스 구간 출력 존재 |
| 벤치마크 3종 위험조정 비교 | RiskReport에 Sharpe/Calmar 대비값 |
| 모든 추천에 자연어 설명 100% | report 렌더 커버리지 테스트 |
| 성향 위반 배정 0건 | compliance 프로퍼티 테스트(랜덤 프로파일) |
| 재현성 100% | 동일 입력·데이터버전 → 동일 산출물 해시 |

## 7. 의존 순서 (병렬 착수 지도)

```text
schemas ──▶ data ──▶ backtest ──▶ risk ──▶ compliance ──▶ report ──▶ pipeline(apex run)
        └─▶ investor ─▶ ips ─────────────────────────────▲
        └─▶ allocation ──────────▲(backtest 입력)
```
schemas 확정 후 data·investor·ips·allocation은 병렬 가능. backtest는 data+allocation, risk는 backtest, compliance는 risk에 의존.

## 8. 다음 액션

승인 시 §5 저장소 위생 + `src/apex` 뼈대 + `schemas`(06 계약)부터 생성한다. (사용자 선택: "계획만 확정" → 현재 단계 종료)
