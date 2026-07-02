# 08. 개발 착수 실행계획 (M4~M6)

01~07(M1~M3 기획)이 확정된 상태에서 **MVP 구현 착수**를 위한 실행 규격.
스택·프로젝트 구조·마일스톤·착수 전 결정사항·완료기준을 여기서 고정한다. (본 문서는 계획 확정본이며 코드는 미포함)

> **2026-07-03 레드팀 재검증(R2) 반영본.** 코드 착수 전 전문가 5인(퀀트·데이터·아키텍트·자문/컴플·PM)이 2라운드 적대적 재검증 → 아래를 반영해 갱신: 재현성 KPI 2체크포인트화, 마일스톤 척추/폭/경화 재배치, AGG 채권 슬롯 승격(안정형 구성 blocker 해소), 지표 load-bearing 최소화, 규제 설계 소변경(예시 프레이밍·개인식별 배제), Q6 가드레일 부등호·RiskReport 스키마·의존 사이클 결함 수정. 함께 개정된 문서: [03](03-investor-survey.md) §4·§5, [05](05-risk-metrics.md) §4·§5, [07](07-asset-classes.md) §1·§3·§5.

## 0. 확정 사항 (2026-07-03)

| 항목 | 확정 | 근거 |
| -- | -- | -- |
| 언어/런타임 | **Python 3.12** | D7 데이터 생태계 정합, 06 §7 |
| 패키지·환경 관리 | **uv** (pyproject + uv.lock) | 재현성·속도 |
| 프론트 형태 | **CLI 우선** → 리포트(HTML) 출력, 웹앱 후순위 | 사용자 결정 2026-07-03 |
| 계약(스키마) | **pydantic v2** | 06 §3 계약을 코드로 고정 |
| 계산 | **pandas / numpy** | 05 지표 |
| 데이터 | **yfinance**(`auto_adjust=False` raw OHLCV+이벤트만 저장, 조정은 로컬 계산), **FRED/ECOS**(환율·금리), **Stooq**(1회성 수동 백필) | 02 §5, D7, R2 §6 |
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
│  ├─ report/               # 룰기반 자연어 리포트 + Jinja2 템플릿 (04 §2) + 면책/예시 프레이밍
│  ├─ metrics/               # 공유 계산 커널: returns·CAGR·MDD·VaR 단일 구현 (05, backtest·risk 중복 방지)
│  └─ currency.py            # D4 통화 토글(계산 USD, 표시 KRW)
├─ tests/                    # pytest (05 §5·01 §5를 테스트로)
├─ data/                     # 로컬 캐시(파케이) — gitignore
├─ tools/sp500/              # 기존 유니버스 도구 (유지)
└─ docs/                     # 01~08
```

## 2. CLI 설계 (프론트 = 명령줄)

콘솔스크립트 `apex`. 각 단계는 독립 실행 가능하고, `apex run`이 전체를 관통한다(06 §6).

```text
apex run --input answers.json [--currency krw] [--out report.html]
    # E2E: 설문→성향→배분→백테스트→리스크→컴플라이언스(강등 루프)→IPS→리포트 (수용기준 ≤3분)

apex survey score --input answers.json          # → InvestorProfile(JSON)
apex portfolio build --profile profile.json     # → Allocation
apex backtest run --alloc alloc.json --years 20 # → BacktestResult
apex risk report --returns series.parquet       # → RiskReport
apex comply check --risk risk.json --profile p.json  # → 위반 판정·강등(RevisedProfile)·재계산 트리거
apex ips render --profile p.json --alloc a.json # → IPS (compliance 확정 후)
apex data pull [--years 20]                      # 코어 9슬롯(+AGG)+FX+금리 raw 스냅샷 갱신
```

- 입력: 설문 응답 JSON(06 §3.1 스키마). 대화형 입력은 후순위.
- 출력: 단계별 JSON 아티팩트 + 최종 HTML 리포트. 모든 산출물에 입력스냅샷·모델버전 기록(재현성, 05 §0).

## 3. 마일스톤 (2026-07-03 레드팀 R2 재배치: 척추→폭→경화)

> **재배치 원리**: 넓은 병렬을 먼저 벌이지 않는다. **① 계약(역간선 포함)을 코드로 동결 → ② 얇은 수직 슬라이스(walking skeleton)로 재현성·강등 루프 종료를 실 20년 1케이스로 선증명 → ③ 폭(4포트·지표) → ④ 랜덤 전수 검증**. "성향 위반 0건" 랜덤 property test는 전 루프를 실데이터로 돌려야 하므로 **M5 DoD가 아니라 M6 E2E**다.

### M4 — 척추(Spine): 계약 동결 + 데이터 스냅샷 + Walking Skeleton
- **schemas 동결**: 06 계약을 pydantic로 고정. **핵심: compliance→allocation 역간선(강등 재배분)을 1급 타입 계약으로** — compliance 반환 = `{decision, revised_profile: InvestorProfile|None, breaches}`, 강등은 `downgrade(profile)→InvestorProfile`(constraints 보존, 03 §5)로 한 곳에서. 문자열 `"중립형"` 반환 금지.
- **데이터 스냅샷 동결**(재현성 토대, §6): 코어 **9슬롯**(SPY·QQQ·EFA·EEM·IEF·TLT·**AGG**·SHY·GLD)을 `auto_adjust=False` **raw OHLCV + 배당/분할 이벤트**로 수집 → 정규화 raw에 content-hash(=`data_version`) 피닝. **조정종가는 저장하지 않고 로컬 결정론 계산**(yfinance 소급조정 회피). USD/KRW(FRED `DEXKOUS`)·무위험금리(USD=DTB3 BEY변환, KRW CD=한국은행 ECOS) 수집.
- **M4 데이터 게이트 3개**(최소): ① 거래일 캘린더(pandas-market-calendars) 커버리지 + 명시 fill 정책 ② 정의된 sanity 스위트(단조 날짜·음수/0 없음·분배/분할일 스파이크 검출) ③ raw 스냅샷 content-hash. (자동 소스 다중화·상시 Stooq 대사는 컷 — Stooq는 불량구간 1회성 수동 백필만.)
- **Walking skeleton**: 1개 프로파일(**강등을 강제하는 적대적 케이스** — 예: 공격형 요청인데 예상 VaR가 Q6 초과)로 investor→allocation→backtest(CAGR·MDD)→risk→compliance(루프)→문장 1줄→해시를 실 20년으로 **관통**.
- **DoD**: (a) skeleton E2E 1케이스가 **동일 스냅샷 재실행 시 동일 산출-JSON 해시**(재현성) (b) **강등 루프가 실제로 돌고 종료조건에서 멈춤**(compliance→allocation 역간선 실증) (c) 9슬롯×20년 raw 스냅샷이 게이트 3종 통과.

### M5 — 폭(Breadth): 고정포트 4종 + 포트↔상한 사전검증
- allocation: 성향별 고정비중 4종(안정/중립/성장/공격), 티커 매핑(02·07 §3). **안정형은 AGG 승격분 반영**.
- **⭐ 07 §7 포트↔상한 사전검증 게이트**: 4종 포트가 각 성향의 05 §3 상한(vol/MDD/연율VaR)을 **실측 20년·스트레스에서 실제 통과하는지** 먼저 확정. **특히 안정형(A: AGG기반)이 2022 국면 `MDD≥-10%`를 통과하는지 판정 → 미통과 시 채권 하한 45%로 하향(B, 07 §3)**. 통과 못 하는 포트는 무게 조정 or 상한 개정을 **M5 안에서** 결정(뒤로 미루면 순환).
- backtest: 일별수익률·CAGR·MDD, **벤치마크 = ETF TR 프록시**(S&P500→SPY 조정종가 / 60·40→SPY60+IEF40 / KOSPI200→KODEX200 `069500.KS` 조정종가). `^GSPC`/`^KS200`(price-return) 금지. 리밸런싱 규칙(분기말)·거래비용 가정·환산순서 명시. 실측 스트레스 3구간(2008/2020/2022).
- risk: **축소 지표세트**(vol/MDD/**Historical VaR95 1d+연율**/CVaR95/Sharpe/Calmar/집중도 + 통화노출%). 금리·주식충격 민감도, 가상 스트레스 4종, 통화 2종 저장은 **v2**(05 §4 R2 정정).
- compliance: 05 §3 상한 대비 차단→강등→재계산 루프(종료조건 03 §4). `apex comply` 동사.
- **DoD**: 4종 포트가 각 성향 상한을 통과함을 확인(안정형 A/B 판정 완료) + 05 §5 체크리스트.

### M6 — 경화(Hardening): 리포트 + 랜덤 전수 + 규제
- IPS 문장 템플릿(04 §2) + 룰기반 설명 리포트(추천마다 자연어 1회 이상, "추천" 단위 정의 명시).
- **규제 하드요구**: 면책·투자권유 아님·원금손실·과거성과 무보장 고지 렌더 + **"예시 모델포트폴리오" 프레이밍**(개인 지시형 문구 금지) + 개인식별정보 배제(Q4/Q5 밴드 입력).
- **랜덤 프로파일 "성향 위반 0건" property test**(전 루프 실데이터 E2E) + D4 통화 토글(KRW 기본, USD계산·KRW표시) + `apex run` ≤3분·재현성 전면.
- **DoD**: 01 §5 수용기준 전항 충족(아래 §6).

## 4. 착수 전 결정 (제안 기본값 — 확정/반대 표시)

스캐폴딩 자체는 아래 없이 가능. 각 모듈 착수 직전 확정한다.

1. **splice 정책** (M4 전) — **확정: MVP는 splice 없이 대표 티커 실데이터만.** 9슬롯 대표 티커 모두 20년+ 확보(AGG 2003-09 포함). 대안 티커·지수 splice는 v2. **BND(2007상장)는 20년 미달이라 채권 슬롯에서 제외**하고 AGG 사용.
2. **최대 강등 횟수** — **확정: 최대 3회 강등. 3회 후에도 감내 한도 미달이면 "안정형 확정"이 아니라 "배정 보류"(포트폴리오 미발행) + `breaches` 기록**(03 §4·06 §2). R1의 "안정형 확정"은 위반을 알고도 발행하는 것이라 철회.
3. **통화** — 표시 KRW(D4), 계산 USD. 이중 통화 전량 재계산·저장은 v2(05 §4 R2).
4. **안정형 채권 슬롯** (R2 신규) — **확정: A안(AGG 승격) 잠정 채택**으로 산술 구성 blocker 제거. 안정형 4종이 05 §3 상한(특히 2022 `MDD≥-10%`)을 실측 통과하는지는 **M5 §7 게이트에서 판정 → 미통과 시 B안(채권 하한 45% 하향)**. C안(SHY 재분류)은 방어력 착시로 기각.
5. **규제 조치** (R2 신규) — **확정: [필수] 면책·투자권유 아님·원금손실·과거성과 무보장 고지 렌더 + "예시 모델포트폴리오" 프레이밍 + 개인식별정보 배제(Q4/Q5 밴드 입력).** [권고] 상용화 전 자문업 등록/테스트베드 로드맵·법률의견 1회. (형사 리스크 프레이밍은 과대라 톤 다운, 단 disclaimer만으론 불충분 — 경계는 맞춤성.)

> **정정(R2)**: 07 §7의 성향별 상한·집중도밴드 검증은 "M5 이후 튜닝"이 아니라 **M5 착수 조건인 "포트↔상한 사전검증 게이트"**다(§3 M5). "성향 위반 0건"의 성립 근거이므로 뒤로 미루면 M5 DoD가 순환한다. EM/US_TECH 상한 수치 미세조정·오버레이 갱신주기만 튜닝 항목.

## 5. 저장소 위생 (0단계 — 스캐폴딩 시 함께)

- `.gitignore`: `.venv/`, `__pycache__/`, `*.pyc`, `data/`, `*.parquet`, `tools/sp500/*.html`, `.env`
- `pyproject.toml`(uv), `src/apex/` 뼈대, 루트 `README.md`
- 현재 커밋 안 된 문서 변경 9건 정리 커밋

## 6. 완료 기준 (01 §5 → 검증 매핑)

| 수용기준 | 검증 방법 |
| -- | -- |
| 설문→리포트 ≤ 3분 | `apex run` 실행시간 측정(**핀 고정 캐시 전제, 데이터 pull 제외**) |
| 2008/2020/2022 개별 성과 표시 | backtest 스트레스 구간 출력 존재 |
| 벤치마크 3종 위험조정 비교 | RiskReport에 Sharpe/Calmar 대비값 (**ETF TR 프록시**: SPY / SPY60+IEF40 / KODEX200) |
| 모든 추천에 자연어 설명 100% | report 렌더 커버리지 테스트 (**"추천 단위"=성향별 배분 1건으로 정의**) |
| 성향 위반 배정 0건 | **랜덤 프로파일 property test(M6, 전 루프 실데이터 E2E)** — "위반"=배정 예상손실이 min(성향상한, Q6 감내)을 초과. 강등 3회 후에도 미달이면 "배정 보류"가 정답(위반 아님) |
| 재현성 100% | **2체크포인트**: (a) 입력=raw 스냅샷 content-hash 일치 (b) 산출=동일 스냅샷·`(schema_version, model_version)` 하 재실행 시 **정규화 산출-JSON 해시 동일**. 파생물(파케이·조정종가)은 바이트 해시 대신 rtol≤1e-9 비교. "100%"는 **핀 고정 스냅샷 스코프**(Yahoo 재수집 하 아님) |
| **모든 리포트에 면책·투자권유 아님 고지 100%** | report 렌더에 disclaimer·"예시 포트폴리오" 프레이밍·원금손실/과거성과 경고 존재 검사(없으면 빌드 실패) |

## 7. 의존 순서 (병렬 착수 지도)

```text
schemas ─▶ data ─▶ ┌─────────── 재계산 루프 ───────────┐
                   │                                   ▼
   investor ─▶ allocation ─▶ backtest ─▶ risk ─▶ compliance ─(위반: 강등)─┐
                   ▲──────────────────────────────────────────────────────┘
                                                              │(수렴)
                                                              ▼
                                                  ips ─▶ report ─▶ pipeline(apex run)
```
- **이건 DAG가 아니라 사이클**이다: `compliance ─(위반)─▶ allocation` 역간선(강등 재배분)이 있다(06 §2). 이 간선은 `RevisedProfile` 1급 계약(03 §5)으로 서고, **루프 소유는 pipeline**(`while decision==downgrade and n<3`). 종료조건: 수렴 or 3회 후 "배정 보류"(03 §4).
- **IPS는 compliance 확정 후**에 렌더한다(강등 뒤 최종 SAA·허용손실이 정해지므로 — investor 직후 렌더 금지).
- schemas·데이터 스냅샷 동결 + skeleton(강등 강제 1케이스) 통과 = **M4 완료 후에만** allocation/backtest/risk의 폭 확장을 병렬 착수. 계약 미실행 상태의 "종이 병렬"은 순환 은닉이므로 금지.

## 8. 다음 액션

승인 시 순서: **§5 저장소 위생 → `src/apex` 뼈대 → schemas(06 계약, compliance→allocation 역간선 `RevisedProfile` 포함) 동결 → M4 데이터 raw 스냅샷 + walking skeleton(강등 강제 1케이스로 재현성·루프 종료 선증명)**. 이 M4 척추가 통과된 뒤에만 M5 폭 확장을 병렬 착수한다. (사용자 선택: "계획만 확정" → 현재 단계 종료)
