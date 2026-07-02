# S&P 500 유니버스 페이지 생성기

최근 N개년(기본 5년) 동안 S&P 500에 **한 번이라도 편입된 모든 종목**을 수집해
**섹터별 HTML 페이지**로 출력한다.

## 데이터 출처 (모두 무료, D7 정합)

- **Wikipedia — "List of S&P 500 companies"**
  - 현재 구성종목 표: 티커·기업명·GICS 섹터·서브인더스트리·편입일
  - "Selected changes" 표: 편입/편출 이력(날짜·티커·사유)
- **yfinance** (선택): 편출된 종목의 섹터 보강. 실패 시 `미분류 (편출)`로 표기.

> 합집합 = **현재 구성종목 ∪ 기간 내 편출 종목**. 재편입(편출됐다가 복귀)은 '현재'로 취급.

## 설치

```bash
pip install -r requirements.txt
```

## 실행

```bash
python build_sp500_universe.py                # 최근 5년, sp500_by_sector.html 생성
python build_sp500_universe.py --years 3      # 기간 변경
python build_sp500_universe.py --no-enrich    # yfinance 섹터 보강 생략(빠름)
python build_sp500_universe.py -o docs/sp500.html
```

## 출력

단일 HTML 파일(오프라인 열람 가능). 섹터별 섹션 + 검색창 + 현재/편출 배지 + 요약 통계.

## 주의

- Wikipedia 표 구조가 바뀌면 파싱이 실패할 수 있다(에러 메시지로 안내).
- 편출 종목 다수는 피인수·상장폐지로 yfinance 조회가 안 될 수 있어 `미분류 (편출)`로 분류된다.
- 섹터 분류 기준은 **GICS**(Wikipedia 표기)를 따른다. yfinance 섹터명은 GICS로 매핑해 정합을 맞춘다.
