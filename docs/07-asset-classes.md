# 07. 자산군 분류 체계 (Asset Class Taxonomy)

자산군의 **분류·역할·리스크 팩터·성향별 밴드**를 정의하는 정본. 티커 목록은 [02-etf-universe.md](02-etf-universe.md)가, 성향 매핑은 [03-investor-survey.md](03-investor-survey.md)가, 상한은 [05-risk-metrics.md](05-risk-metrics.md)가 참조한다.
Allocation Engine([06-architecture.md](06-architecture.md) §3.3)은 이 체계 안에서만 비중을 배정한다.

## 1. 4단 계층 분류

`대분류 → 중분류 → 자산군 슬롯 → 티커`. 슬롯이 배분·리스크·집중도의 기본 단위다.

| 대분류 | 중분류 | 자산군 슬롯(코드) | 대표 티커 | MVP 배분 |
| -- | -- | -- | -- | -- |
| 주식 EQUITY | 미국 광의 | 미국 대형주 `US_LC` | SPY | ✅ |
| 주식 EQUITY | 미국 광의 | 미국 성장/기술 `US_TECH` | QQQ | ✅ |
| 주식 EQUITY | 해외 선진 | 선진국(미국 외) `DEV_EXUS` | EFA | ✅ |
| 주식 EQUITY | 해외 신흥 | 신흥국 `EM` | EEM | ✅ |
| 주식 EQUITY | 스타일 | 배당주 `DIV` | VYM / SCHD | ✖ (유니버스만) |
| 채권 BOND | 국채·만기 | 중기국채 `GOV_MID` | IEF | ✅ |
| 채권 BOND | 국채·만기 | 장기국채 `GOV_LONG` | TLT | ✅ |
| 채권 BOND | 종합 | 미국 종합채권 `AGG` | AGG / BND | ✖ (유니버스만) |
| 현금성 CASH | 단기 | 단기채/현금성 `CASH_ST` | SHY / BIL | ✅ |
| 실물 REAL | 귀금속 | 금 `GOLD` | GLD | ✅ |

> MVP 배분 슬롯 = 8종(`US_LC, US_TECH, DEV_EXUS, EM, GOV_MID, GOV_LONG, CASH_ST, GOLD`). 배당주·종합채권은 v2 이후 편입 후보.

## 2. 자산군별 역할·리스크 팩터

각 슬롯을 **포트폴리오 내 역할**과 **주된 리스크 팩터**로 규정한다. 리스크 팩터는 05 §1.7 민감도·§2 스트레스 시나리오와 연결된다.

| 슬롯 | 역할 | 주 리스크 팩터 | 통화·환노출 |
| -- | -- | -- | -- |
| `US_LC` | 성장 코어 | 주식 | USD |
| `US_TECH` | 성장 가속(고변동) | 주식·금리(듀레이션 성격) | USD |
| `DEV_EXUS` | 지역 분산 | 주식·환(비USD) | 다통화 |
| `EM` | 성장 위성(고위험) | 주식·환·신흥국 | 다통화 |
| `DIV` | 방어적 주식·인컴 | 주식(저변동) | USD |
| `GOV_MID` | 방어·주식 상쇄 | 금리(D≈7.5) | USD |
| `GOV_LONG` | 강방어·디플레 헤지 | 금리(D≈17, 고변동) | USD |
| `AGG` | 채권 코어 | 금리·소폭 신용 | USD |
| `CASH_ST` | 유동성·안전판 | 금리(D≈1.9, 미미) | USD |
| `GOLD` | 인플레·위기 헤지 | 실물·실질금리·환 | USD |

> 국내 개인·원화 기준(D2/D4)이므로 **모든 해외자산은 USD/KRW 환리스크를 수반**한다. 환헤지 정책은 03 Q9·04 환헤지 필드로 결정, 05 §1.7 FX 민감도로 계측.

## 3. 성향별 자산군 밴드 (SAA 허용 범위)

03 §3 주식비중(안정30/중립55/성장75/공격90)과 정합하는 **대분류·핵심 슬롯 허용 밴드**. Compliance는 이 밴드 이탈을 차단한다.

| 대분류/슬롯 | 안정형 | 중립형 | 성장형 | 공격형 |
| -- | -- | -- | -- | -- |
| **주식 합계** | 20–35% | 45–60% | 65–80% | 85–95% |
| └ `EM`(신흥국) 상한 | ≤ 5% | ≤ 10% | ≤ 15% | ≤ 20% |
| └ `US_TECH` 상한 | ≤ 10% | ≤ 15% | ≤ 25% | ≤ 35% |
| **채권 합계** | 50–70% | 30–45% | 12–25% | 3–10% |
| └ `GOV_LONG`(장기) 상한 | ≤ 15% | ≤ 15% | ≤ 12% | ≤ 10% |
| **실물 `GOLD`** | 5–15% | 5–12% | 3–10% | 0–10% |
| **현금성 `CASH_ST`** | ≥ 5% | ≥ 3% | ≥ 3% | ≥ 3% |

가드레일:
- 유동성 필요 "높음"(Q8) → `CASH_ST` 최소 **≥ 10%** (05 §3.1).
- 밴드는 **주식비중 상한**과 상충 시 03 §3 성향 등급을 우선(더 보수적 값 채택, 05 §3 주석).
- 고변동 위성(`EM`·`US_TECH`·`GOV_LONG`)은 별도 상한으로 집중 억제.

## 4. 집중도 규칙 (05 §3.1 연동)

- 단일 ETF ≤ 30%
- 단일 자산군 슬롯 ≤ 해당 성향 대분류 상한
- 통화 집중: 비USD 해외자산 노출 합을 별도 표기(05 §1.8 국가/통화 집중)
- 개별종목(v2) ≤ 5% — 테마군·세부테마 집중 상한은 §6.4

## 5. 확장 로드맵 (v2 이후 편입 후보)

| 후보 슬롯 | 대분류 | 편입 조건 |
| -- | -- | -- |
| 배당주 `DIV` | 주식 | 인컴 수요 옵션 |
| 종합채권 `AGG` | 채권 | 채권 코어 단순화 |
| 리츠 `REIT` | 실물 | 인플레·인컴 분산 |
| 팩터(모멘텀/퀄리티/저변동) | 주식 | 스타일 틸트 |
| 하이일드 `HY` | 채권 | 신용 팩터 도입(리스크 재정의 필요) |
| 개별종목 | 주식 | v2 규제·데이터 요건 충족 후 → **테마 분류·집중도는 §6** (후보 유니버스: [S&P500 5개년 합집합 593종](../tools/sp500/sp500_by_sector.html)) |

> 신용·리츠·팩터 편입 시 05 리스크 팩터 목록과 §2 스트레스 시나리오를 함께 확장해야 정합이 유지된다.

## 6. 개별종목 테마 분류 체계 (v2 위성 슬리브)

개별종목은 MVP에서 제외(01 D3·02 §4)되며 **v2 위성(satellite) 슬리브**로만 편입한다. 성향별 주식밴드(§3) 안에서 코어 ETF 위에 얹는 알파 레이어이고, 집중도는 §4·§6.4로 억제한다.

> **축 구분(정본)**: §1~5의 **ETF 슬롯 자산군** 축(대분류→슬롯 `US_LC`/`US_TECH`…, MVP 배분·집중도 단위)과 본 §6의 **개별종목 테마** 축(테마군8→세부테마→GICS Sub-Industry, v2)은 별개다. GICS 섹터를 자산군 슬롯 배분과 혼동하지 말 것. 두 축의 관계 정의는 **이 §6 한 곳에만** 두고, 다른 문서(00/01/02/05/06)는 링크로만 참조한다.

분류축은 **메가트렌드 하이브리드**다. GICS를 버리지 않고 그 위에 테마를 얹는다:

- **1차 분할(전 유니버스 100% 커버)** = `테마군(8) → 세부테마 → GICS Sub-Industry`. 모든 종목은 자신의 **GICS Sub-Industry로 정확히 1개 세부테마**에 자동 배정된다(§6.3 크로스워크). 상호배타·완전분할이라 잔여 없음.
- **2차 오버레이(교차 필터)** = 티커 집합으로 정의하는 **메가트렌드 태그**(§6.5). GICS가 못 가르는 핫테마(사이버보안·GLP-1·전기차 등)를 세분화·필터링용으로 얹는다. 1차 분할과 독립이며 종목당 0~N개.

> 근거 데이터: 2026-07-02 Wikipedia S&P 500 현재 구성종목 503종의 실측 GICS Sub-Industry 127종을 전량 매핑. 편출·미분류 종목은 §6.6 규칙으로 처리.

### 6.1 테마군 8분류 (1차, 대분류)

| 코드 | 테마군 | 포함 GICS 섹터(주) | 성격·역할 | 주 리스크 팩터 |
| -- | -- | -- | -- | -- |
| `AI_HW` | AI·반도체·하드웨어 | IT, (RE 디지털인프라) | 컴퓨트·연결 백본, 고성장·고변동 | 주식·경기순환·기술사이클 |
| `SW_CLD` | 소프트웨어·클라우드·플랫폼 | IT, Comm | 구독·플랫폼 성장, 고멀티플 | 주식·금리(듀레이션성) |
| `FIN` | 핀테크·결제·금융 | Financials, IT | 금리 레버리지·경기민감 | 주식·금리·신용 |
| `HLTH` | 헬스케어·바이오 | Health Care | 방어+혁신 이원, 규제·파이프라인 | 주식·규제·특허 |
| `CONS` | 소비·리테일·브랜드 | Cons Staples/Disc | 필수(방어)+재량(경기) | 주식·소비경기·환 |
| `COMM` | 미디어·통신·엔터 | Comm | 콘텐츠·통신 인프라 | 주식·경쟁·규제 |
| `INDU` | 산업·인프라·모빌리티 | Industrials, Cons Disc(자동차) | 캐펙스·전동화·리쇼어링 | 주식·경기순환·원자재 |
| `REAL` | 에너지·소재·유틸·부동산 | Energy/Materials/Utilities/RE | 실물·인컴·인플레 헤지 | 주식·원자재·금리·실질금리 |

### 6.2 세부테마 (2차 드릴다운) — 개요

각 테마군은 아래 세부테마로 드릴다운된다. 코드는 `테마군.세부` 점표기(필터 UI의 계층키). 전체 GICS Sub-Industry 귀속은 §6.3 크로스워크가 정본.

- `AI_HW`: `.SEMI` 반도체·AI칩 · `.SEMIEQ` 반도체 장비/소재 · `.HW` 하드웨어·기기·부품 · `.NET` 네트워크장비 · `.DCI` 데이터센터·디지털인프라
- `SW_CLD`: `.SYS` 시스템/인프라 SW(보안 포함) · `.APP` 애플리케이션 SW·SaaS · `.PLAT` 인터넷 플랫폼 · `.SVC` IT·데이터 서비스
- `FIN`: `.PAY` 디지털결제·핀테크 · `.EXCH` 거래소·금융데이터 · `.BANK` 은행 · `.CAP` 자산운용·IB·증권 · `.INS` 보험 · `.CONS` 소비자금융 · `.HOLD` 복합지주
- `HLTH`: `.PHARMA` 제약 · `.BIO` 바이오테크 · `.DEV` 의료기기·소모품 · `.TOOLS` 생명과학 툴·진단 · `.SVC` 헬스서비스·매니지드케어
- `CONS`: `.STAPLE` 필수소비·식음료·생활 · `.RETAIL` 리테일·유통 · `.BRAND` 브랜드·럭셔리·레저상품 · `.LEISURE` 여행·레저·외식·게이밍
- `COMM`: `.MEDIA` 미디어·엔터·방송·광고 · `.TELCO` 통신
- `INDU`: `.AERO` 항공·방산 · `.MACH` 기계·자동화·전기장비 · `.CONGLO` 복합산업 · `.TRANS` 운송·물류 · `.INFRA` 인프라·건설·건자재 · `.SVC` 기업·시설·인력서비스 · `.AUTO` 모빌리티·전기차
- `REAL`: `.OILGAS` 에너지(석유·가스) · `.MAT` 소재·화학·포장 · `.METAL` 금속·광물·귀금속 · `.UTIL` 유틸리티·전력·물 · `.REIT` 리츠·부동산 · `.HOUSE` 주택·건설(주택)

### 6.3 GICS Sub-Industry → 세부테마 크로스워크 (전 유니버스 매핑 정본)

Wikipedia가 제공하는 **GICS Sub-Industry**를 키로 한 결정적 매핑. 종목이 어느 Sub-Industry든 아래 표로 세부테마·테마군이 유일하게 결정된다(HTML은 이 표를 dict로 인코딩). ⨯표는 GICS 섹터와 테마군이 갈리는 **크로스섹터 배정**(메가트렌드 우선).

| 세부테마 코드 | 포함 GICS Sub-Industry | 대표 종목 |
| -- | -- | -- |
| `AI_HW.SEMI` | Semiconductors | NVDA, AVGO, AMD, TXN, QCOM, MU, INTC |
| `AI_HW.SEMIEQ` | Semiconductor Materials & Equipment | AMAT, LRCX, KLAC |
| `AI_HW.HW` | Technology Hardware Storage & Peripherals · Electronic Components · Electronic Equipment & Instruments · Electronic Manufacturing Services · Technology Distributors · Consumer Electronics ⨯(Cons Disc) | AAPL, DELL, APH, KEYS, FLEX, CDW |
| `AI_HW.NET` | Communications Equipment | CSCO, ANET, MSI |
| `AI_HW.DCI` | Internet Services & Infrastructure · Data Center REITs ⨯(RE) · Telecom Tower REITs ⨯(RE) | EQIX, DLR, AMT, CCI, VRSN |
| `SW_CLD.SYS` | Systems Software | MSFT, ORCL, PANW, CRWD, FTNT |
| `SW_CLD.APP` | Application Software | CRM, ADBE, NOW, INTU, ADSK |
| `SW_CLD.PLAT` | Interactive Media & Services ⨯(Comm) | GOOGL, META, MTCH |
| `SW_CLD.SVC` | IT Consulting & Other Services · Data Processing & Outsourced Services ⨯(Industrials) | ACN, IBM, CTSH, BR |
| `FIN.PAY` | Transaction & Payment Processing Services | V, MA, PYPL, FI, GPN |
| `FIN.EXCH` | Financial Exchanges & Data | SPGI, ICE, CME, MCO, MSCI |
| `FIN.BANK` | Diversified Banks · Regional Banks | JPM, BAC, WFC, USB, PNC |
| `FIN.CAP` | Asset Management & Custody Banks · Investment Banking & Brokerage | BLK, GS, MS, SCHW, BX |
| `FIN.INS` | Life & Health Insurance · Property & Casualty Insurance · Multi-line Insurance · Reinsurance · Insurance Brokers | PGR, CB, MMC, AIG, MET |
| `FIN.CONS` | Consumer Finance | AXP, COF, SYF |
| `FIN.HOLD` | Multi-Sector Holdings | BRK.B |
| `HLTH.PHARMA` | Pharmaceuticals | LLY, JNJ, MRK, ABBV, PFE |
| `HLTH.BIO` | Biotechnology | AMGN, GILD, VRTX, REGN, BIIB |
| `HLTH.DEV` | Health Care Equipment · Health Care Supplies | ISRG, MDT, ABT, SYK, BSX |
| `HLTH.TOOLS` | Life Sciences Tools & Services | TMO, DHR, A, IQV |
| `HLTH.SVC` | Managed Health Care · Health Care Services · Health Care Facilities · Health Care Distributors · Health Care Technology | UNH, ELV, CI, CVS, MCK |
| `CONS.STAPLE` | Household Products · Packaged Foods & Meats · Soft Drinks & Non-alcoholic Beverages · Personal Care Products · Brewers · Distillers & Vintners · Tobacco · Agricultural Products & Services · Food Distributors | PG, KO, PEP, MDLZ, MO |
| `CONS.RETAIL` | Consumer Staples Merchandise Retail · Food Retail · Broadline Retail ⨯(AMZN) · Apparel Retail · Automotive Retail · Home Improvement Retail · Homefurnishing Retail · Computer & Electronics Retail · Other Specialty Retail · Distributors | WMT, COST, AMZN, HD, LOW |
| `CONS.BRAND` | Apparel Accessories & Luxury Goods · Footwear · Leisure Products | NKE, TPR, RL, DECK |
| `CONS.LEISURE` | Hotels Resorts & Cruise Lines · Restaurants · Casinos & Gaming · Specialized Consumer Services | MCD, SBUX, BKNG, MAR, LVS |
| `COMM.MEDIA` | Movies & Entertainment · Broadcasting · Cable & Satellite · Publishing · Advertising · Interactive Home Entertainment | DIS, NFLX, CMCSA, EA, TTWO |
| `COMM.TELCO` | Integrated Telecommunication Services · Wireless Telecommunication Services | T, VZ, TMUS |
| `INDU.AERO` | Aerospace & Defense | LMT, RTX, NOC, GD, BA |
| `INDU.MACH` | Industrial Machinery & Supplies & Components · Construction Machinery & Heavy Transportation Equipment · Agricultural & Farm Machinery · Electrical Components & Equipment · Heavy Electrical Equipment | CAT, DE, ETN, EMR, PH |
| `INDU.CONGLO` | Industrial Conglomerates | HON, MMM, GE |
| `INDU.TRANS` | Air Freight & Logistics · Cargo Ground Transportation · Rail Transportation · Passenger Airlines · Passenger Ground Transportation | UPS, FDX, UNP, DAL, UBER |
| `INDU.INFRA` | Construction & Engineering · Building Products · Trading Companies & Distributors | PWR, CARR, JCI, FAST |
| `INDU.SVC` | Diversified Support Services · Environmental & Facilities Services · Human Resource & Employment Services · Research & Consulting Services | WM, RSG, ADP, PAYX |
| `INDU.AUTO` | Automobile Manufacturers ⨯(Cons Disc) · Automotive Parts & Equipment ⨯(Cons Disc) | TSLA, GM, F, APTV |
| `REAL.OILGAS` | Integrated Oil & Gas · Oil & Gas Exploration & Production · Oil & Gas Equipment & Services · Oil & Gas Refining & Marketing · Oil & Gas Storage & Transportation | XOM, CVX, COP, EOG, SLB |
| `REAL.MAT` | Commodity Chemicals · Specialty Chemicals · Industrial Gases · Fertilizers & Agricultural Chemicals · Construction Materials · Metal Glass & Plastic Containers · Paper & Plastic Packaging Products & Materials | LIN, SHW, APD, ECL, DOW |
| `REAL.METAL` | Steel · Copper · Gold | NUE, STLD, FCX, NEM |
| `REAL.UTIL` | Electric Utilities · Multi-Utilities · Gas Utilities · Water Utilities · Independent Power Producers & Energy Traders | NEE, DUK, SO, CEG, AWK |
| `REAL.REIT` | Industrial REITs · Retail REITs · Health Care REITs · Multi-Family Residential REITs · Office REITs · Self-Storage REITs · Hotel & Resort REITs · Single-Family Residential REITs · Other Specialized REITs · Timber REITs · Real Estate Services | PLD, O, WELL, SPG, PSA |
| `REAL.HOUSE` | Homebuilding ⨯(Cons Disc) | DHI, LEN, PHM, NVR |

> 크로스섹터(⨯) 배정 4곳이 핵심: 데이터센터·통신타워 REIT와 인터넷인프라 → `AI_HW.DCI`(디지털 백본), 자동차 → `INDU.AUTO`(모빌리티), 주택건설 → `REAL.HOUSE`(주택), Broadline Retail(AMZN 등) → `CONS.RETAIL`. GICS 섹터와 다르게 배정되는 지점이므로 HTML도 이 표를 따른다.

### 6.4 개별종목·테마 집중도 밴드 (제안값, §6 미결정 검증 전)

성향별 주식밴드(§3) 안에서 위성 슬리브에 적용. 수치는 제안값이며 백테스트 검증(§7) 후 확정.

| 항목 | 안정형 | 중립형 | 성장형 | 공격형 |
| -- | -- | -- | -- | -- |
| 개별종목 슬리브 합계(주식 중) | 0% | ≤ 10% | ≤ 20% | ≤ 30% |
| 단일 종목 상한 | ≤ 5% | ≤ 5% | ≤ 5% | ≤ 5% |
| 단일 세부테마 상한 | — | ≤ 8% | ≤ 12% | ≤ 15% |
| 단일 테마군 상한 | — | ≤ 15% | ≤ 20% | ≤ 25% |

- 단일 종목 ≤ 5%는 성향 무관 하드 룰(05 §3.1과 정합).
- 오버레이 태그(§6.5) 합산 노출은 별도 **모니터링**(하드 상한 아님) — 예: `#AI` 태그 종목 합이 세부테마 상한을 우회해 과집중되는지 감시.

### 6.5 메가트렌드 오버레이 태그 (2차, 티커 기반 교차 필터)

GICS 분할로는 안 잡히는 핫테마. 티커 집합으로 관리하며 1차 분할과 독립(종목당 다중 태그 가능). 대표 종목은 예시이며 **비완전**(정기 갱신 대상).

| 태그 | 정의 | 대표 종목 | 비고 |
| -- | -- | -- | -- |
| `#AI` | AI 컴퓨트·모델·인프라 밸류체인 | NVDA, AVGO, AMD, MU, MSFT, GOOGL, META, ANET, ORCL | `SEMI`+`SYS`+`PLAT`+`DCI` 교차 |
| `#CYBER` | 사이버보안 | PANW, CRWD, FTNT, GEN | GICS는 Systems Software로 뭉뚱그림 |
| `#CLOUD` | 클라우드·SaaS | MSFT, AMZN, GOOGL, CRM, NOW, ADBE, ORCL | 하이퍼스케일러+SaaS |
| `#GLP1` | 비만·당뇨(GLP-1) | LLY | (NVO는 S&P500 외) |
| `#EV` | 전기차·자율주행 | TSLA, GM, F, APTV, ON | 배터리·부품 포함 |
| `#CLEAN` | 클린에너지·전력화·원자력 | NEE, FSLR, ENPH, CEG, VST, GEV, ETN | AI 전력수요 수혜 교차 |
| `#DEFENSE` | 방산·우주 | LMT, RTX, NOC, GD, LHX, AXON | `INDU.AERO` 부분집합+α |

### 6.6 HTML 재분류 적용 노트 (`tools/sp500`)

[`build_sp500_universe.py`](../tools/sp500/build_sp500_universe.py)가 이 테마 분류를 **구현**한다 — [생성 HTML](../tools/sp500/sp500_by_sector.html) · [README](../tools/sp500/README.md). 2026-07-02 기준 합집합 **593종**(현재 503 + 편출 90)을 재분류하며, **현재 503종은 §6.3 크로스워크로 세부테마까지 100% 자동 배정(미매칭 0)**, 편출 90종은 아래 4번 규칙으로 테마군까지 축소 매핑(세부테마 `*.기타`/미분류). 구현 방식:

1. **Sub-Industry 파싱 추가** — 현재 표에서 `Sub-Industry` 컬럼을 이미 읽을 수 있음(`_find_col(tt, "sub")`). 레코드에 `sub` 필드 추가.
2. **크로스워크 dict 인코딩** — §6.3을 `SUBIND_TO_THEME = {"Semiconductors": ("AI_HW","AI_HW.SEMI"), ...}` 형태로. 503 현재종목 100% 자동 배정.
3. **오버레이 태그 세트** — §6.5를 `OVERLAY = {"#AI": {"NVDA", ...}, ...}` 티커 집합으로. 종목 렌더 시 매칭 태그 배지 부여.
4. **편출·미분류 처리(§6.6 규칙)** — 편출종목은 Sub-Industry가 없으므로 yfinance 섹터→테마군까지만 배정(세부테마 `*.기타`), 조회 실패 시 그룹 `미분류`.
5. **UI** — `테마군(8)` 아코디언 → `세부테마` 하위 그룹 → 종목 테이블. 상단에 오버레이 태그 멀티셀렉트 필터 + 기존 검색/현재·편출 배지 유지.

> 크로스워크·태그는 이 문서(§6.3·§6.5)를 **정본**으로 두고 도구는 복제. 둘이 어긋나면 문서를 우선한다.

## 7. 미결정

- [ ] `EM`·`US_TECH` 상한 수치는 백테스트로 성향별 변동성 가이드(05 §3) 충족 여부 검증 후 확정
- [ ] 환헤지형 자산군 슬롯을 별도 코드로 둘지(`DEV_EXUS_H` 등) 여부 — D5 최적화(2차년도)와 연동
- [ ] §6.4 개별종목·테마 집중도 밴드(제안값)를 백테스트로 검증 후 확정
- [ ] 오버레이 태그(§6.5) 목록·구성종목의 갱신 주기·기준(편입/편출 시 재태깅) 정의
- [ ] 편출종목 세부테마 보강 방식(yfinance sub-industry 조회 가능 여부) 확인 — 불가 시 `테마군.기타` 유지
- [ ] **유니버스 룩백 vs 백테스트 기간 불일치**: 도구는 5개년 편입 합집합인데 백테스트는 20년+(01 §5) → v2 개별종목 20년 백테스트 시 2021 이전 편출종목 누락으로 생존편향(15→20년으로 늘면 격차 확대). 착수 시 룩백을 백테스트 기간에 맞춰 확장 필요.
