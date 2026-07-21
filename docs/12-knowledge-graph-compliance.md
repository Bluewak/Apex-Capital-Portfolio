# 12. 지식그래프 기반 Compliance/추천 (온톨로지 상세 설계)

[10 §3.7 Knowledge Plane](10-v2-pipeline-design.md)의 **상세 설계**. 자산·자산군·리스크팩터·통화·성향·제약·시나리오·벤치마크의 관계를 **명시적 그래프**로 세우고, compliance 판정과 설명을 그 관계에서 **유도(infer)**한다.

> **범위(§3.7 정본 준수).** 스코프 정본은 [10 §3.7](10-v2-pipeline-design.md)이며 본 문서는 그 확장이다.
> - **자리1 — 결정론 검증**(SHACL/그래프쿼리로 compliance·모델검증 강화): **v2 Step 2**.
> - **자리2 — GraphRAG grounding**(Advisory 설명의 추적가능 근거): **v2 Step 3**.
> - **FIBO 전체 정렬·Neo4j/GraphDB·대규모 GraphRAG·개별종목 KG**: **v3**([10 §12](10-v2-pipeline-design.md)).
>
> 판정·수치 정확도는 퀀트 모델(②)이 올린다. KG는 **검증·설명**을 올리며 판정 경로에 RAG/LLM/GNN을 붙이지 않는다([10](10-v2-pipeline-design.md) §1.7·§3.7 거부).

관련: [10 §3.7·§3.5·§12](10-v2-pipeline-design.md) · [11 방향성 §5](11-direction.md) · [07 자산군](07-asset-classes.md) §2 · [05 리스크](05-risk-metrics.md) §3 · `src/apex/universe.py`

---

## 1. 동기 — 왜 그래프인가

현재 규칙·매핑은 코드에 흩어 하드코딩된다. 그래프로 옮기면:

1. **판정이 관계 탐색이 된다.** "SPY는 주식인가?"를 사람이 매핑하지 않고 `belongsTo`/`subClassOf` 클로저로 유도.
2. **설명이 경로에서 나온다.** breach 근거 = 그래프 경로(SPY→미국대형주→미국주식→주식) → **자리2 GraphRAG**(§3.7)의 추적가능 grounding.
3. **단일 진실 원천.** `universe.py`·07 §2·05 §3의 **암묵 관계가 이미 ~70% 존재**(§3.7) → 명시화가 핵심 일.

**AI-free 강화**: 자리1은 결정론 규칙 추론이라 [11](11-direction.md) §5.1(판정에 AI 금지)을 **오히려 더 튼튼히** 만든다. GNN 임베딩 대체는 거부(블랙박스·감사불가, §3.7).

## 2. 온톨로지 모델 (§3.7 스케치 = 정본 어휘)

### 2.1 엔티티

`Asset · AssetClass · RiskFactor · Currency · Region · Profile · ModelPortfolio · Constraint · Metric · Scenario · Benchmark` (FIBO 정렬, 경량 시작).

### 2.2 관계 (§3.7 어휘 준수)

```text
Asset          —belongsTo→ AssetClass      · —loadsOn→ RiskFactor{w}
               —exposedTo→ Currency        · —overlaps→ Asset{lookthrough}
AssetClass     —subClassOf→ AssetClass                 (07 4단 계층: 미국대형주⊂미국주식⊂주식)
ModelPortfolio —holds→ Asset{w}            · —forProfile→ Profile
Profile        —hasBand→ AssetClass{min,max} · —hasLimit→ Metric
Scenario       —shocks→ RiskFactor{mag}    · Benchmark —proxies→ Asset(TR)
```

### 2.3 공리(추론 규칙)

- **이행성**: `subClassOf`·`belongsTo`는 이행적 → 조상 클로저로 자산군 소속 유도.
- **가중 집계(급소)**: 자산군/팩터/통화 비중 = Σ(`w` × 배정비중). **⚠️ 단순 집합합 금지** — 다자산 ETF·`overlaps` 중복은 **분수 노출**로 집계해야 이중계상을 피한다(§8).
- **제약 판정**: `Profile hasBand/hasLimit` 대비 집계 초과 → breach + 근거경로.
- **룩스루**: 통화·팩터도 가중 전파(EFA/EEM 기초통화 분해, 하드코딩 USD 제거).

## 3. 자리1 — Compliance = 그래프 추론 (v2 Step 2)

§3.7 자리1이 강화하는 검증: **팩터 레벨 집중도·룩스루 중복·통화노출·밴드 정합·시나리오 일관성.** 결정론·해시가능한 개념 증명(~20줄):

```python
BELONGS = {"SPY": ["미국대형주"], "QQQ": ["미국대형주"],
           "미국대형주": ["미국주식"], "미국주식": ["주식"],
           "IEF": ["미국국채"], "미국국채": ["채권"]}   # belongsTo + subClassOf
BANDS = {"안정형": {"주식": (0.0, 0.30)}}               # Profile —hasBand→ {min,max}

def ancestors(node):                                    # 이행 클로저(결정론)
    out, stack = set(), [node]
    while stack:
        for p in BELONGS.get(stack.pop(), []):
            if p not in out: out.add(p); stack.append(p)
    return out

def class_weights(weights):                             # 가중 집계
    agg = {}
    for tk, w in weights.items():
        for cls in ancestors(tk): agg[cls] = agg.get(cls, 0) + w
    return agg

def check(profile, weights):
    cw = class_weights(weights)
    out = []
    for cls, (lo, hi) in sorted(BANDS[profile].items()):
        v = cw.get(cls, 0)
        if not (lo <= v <= hi):
            out.append({"class": cls, "actual": round(v, 3), "band": (lo, hi),
                        "because": sorted(t for t in weights if cls in ancestors(t))})
    return out

# check("안정형", {"SPY": 0.4, "IEF": 0.6})
# → [{'class': '주식', 'actual': 0.4, 'band': (0.0, 0.3), 'because': ['SPY']}]
```

규칙을 하드코딩하지 않았는데 "SPY는 주식이라 밴드 초과"가 근거경로와 함께 나온다. `sorted` 정규화 → **해시가능·재현가능**([11](11-direction.md) §5.8). 실제 구현은 SHACL shape 또는 타입드 pydantic 그래프 쿼리로(§6).

## 4. 자리2 — 추천 설명 & GraphRAG (v2 Step 3)

**그래프는 배분 숫자를 고르지 않는다.** 그건 Model Plane의 **CMA→최적화**([10](10-v2-pipeline-design.md) §3.2) 몫. 그래프 역할은 둘:

1. **제약 생성기**: 최적화에 넣을 성향별 제약집합(`hasBand`·`hasLimit`·집중도·통화노출)을 그래프에서 생성.
2. **설명기(자리2)**: 선택된 비중의 근거를 `playsRole`/`loadsOn`/`shocks` 다홉 경로로 서술. 예: *"왜 안정형인데 2022 −20%?" → 채권 `loadsOn` 듀레이션 → Scenario 2022 `shocks` 듀레이션*(§3.7). `FactLedger`+KG+문서가 GraphRAG grounding 소스.

> "그래프가 포트폴리오를 골라준다"는 **과장**. 그래프 = 제약 + 설명, 옵티마이저 = 숫자.

## 5. 결정론·재현성 정합 ([11](11-direction.md) §5)

| 가드레일 | 준수 |
| -- | -- |
| §5.1 판정에 AI 금지 | 자리1 = 결정론 규칙. 자리2 LLM은 설명 계층에만(판정 경로 밖) |
| §5.2 해시에 서술 미포함 | 자리1 판정은 numeric_hash. 자리2 근거·서술은 FactLedger/narrative로 분리 |
| §5.4 계약우선·버전각인 | 그래프 = 버전드 아티팩트(`graph_version`), 레지스트리 등재 |
| §5.8 재현성 | 탐색순서 정규화(sorted). LLM 재현성은 캐시로(§3.4) |

**추론기 원칙**: OWL 추론기(HermiT 등) 비결정성·성능은 결정론 코어에 독 → 코어엔 **SHACL 검증/명시 규칙**만. 학습 임베딩(GNN) 거부.

## 6. 기술 선택 (§3.7 구현 준수)

| 단계 | 방식 | 스코프 |
| -- | -- | -- |
| **경량 시작** | `rdflib`(OWL) + `pySHACL` 검증 **또는 타입드 pydantic 그래프** | ✅ v2 Step 2 |
| GraphRAG 검색 | Cypher/SPARQL + LlamaIndex PropertyGraphIndex | v2 Step 3(경량) |
| 확장 | Neo4j / Ontotext GraphDB(FIBO 네이티브) · 대규모 GraphRAG(reranker) | v3 |

핀우선·단일프로세스·결정론 이념상 **상시 DB(Neo4j)는 코어 판정 밖**에 두고 탐색·grounding 보조로만.

## 7. FactLedger / Advisory 연계

- breach·배분의 **근거경로**를 FactLedger 화이트리스트로 추출 → Narrator는 이 경로만 서술(창작 금지, [10](10-v2-pipeline-design.md) §3.4).
- 그래프 어휘(자산군·역할·팩터 라벨)가 곧 LLM **허용 어휘 사전** → 금칙·환각 게이트([10](10-v2-pipeline-design.md) §8-6) 기준.

## 8. 가중 소속 정밀화 (구현 급소)

- 다자산 ETF(예 AOR)·개별종목·`overlaps`(SPY∩QQQ 중복)은 **한 자산군이 아니라 분수 노출**을 가진다.
- 집계는 `belongsTo{w}`/`loadsOn{w}`/`exposedTo{w}` **분수 곱**이어야 하며 **단순 집합합은 이중계상**을 낳는다.
- §2.3 가중 집계 공리 + §3.7 자리1 "룩스루 중복(`overlaps`)" 검증으로 강제. 단일소속 티커는 `w=1`.

## 9. 마이그레이션 경로 (Step 매핑)

```text
v2 Step 2 (자리1): domain 관계를 그래프 아티팩트로 명시화(universe.py+07+05, ~70% 존재)
                   → SHACL/쿼리 결정론 검증(집중도·룩스루·통화·밴드·시나리오)
                   → 기존 compliance 결정과 골든 동일성 테스트(행동 변화 0) · graph_version 각인
v2 Step 3 (자리2): FactLedger+KG grounding → Advisory GraphRAG(경량 PropertyGraphIndex)
v3        : FIBO 전체 정렬 · Neo4j/GraphDB · 대규모 GraphRAG(reranker) · 개별종목 KG(PIT·생존편향)
```

## 10. 미결정·오픈 이슈

- **가중 소속(§8)** 데이터 소스: 기초자산 분해(통화·팩터 노출)의 무료 스택 확보 가능성.
- 자산군 partition/다중소속 허용 범위와 `overlaps` 룩스루 데이터.
- 그래프 거버넌스: 편집 주체·검증(밴드 정합·순환 탐지)·버전 승격.
- 규칙 표현력 한계: 소속·집계·상한은 그래프가 처리하나 복합 조건부 규칙은 코드 잔존 가능(경계 문서화).
- FIBO 정렬 깊이: 경량 매핑 vs 전체 정렬(v3) 사이 어디까지 v2에서.

## 11. 한 줄 결론

> 지식그래프는 **compliance의 "무엇이 무엇인가"와 설명을 데이터로 내리는** 장치다(자리1 검증 = v2 Step 2, 자리2 grounding = v2 Step 3). 배분 숫자는 옵티마이저 몫, FIBO 전체·대규모 인프라는 v3.
