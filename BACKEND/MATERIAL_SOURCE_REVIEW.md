# K-DPP 소재별 탄소배출계수 출처 검토표

기준 파일: `BACKEND/init_data.py`

현재 DB 소재 수: 22개

## 계산 범위

K-DPP의 탄소배출량 계산은 의류 전체 생애주기 전체가 아니라, **원료/소재 생산 단계 중심 추정값**으로 정의한다.

포함 범위:

- 원료 생산
- 섬유/소재 생산
- 소재별 탄소배출계수 기반 계산

제외 범위:

- 봉제/제조 공정 전체
- 유통
- 사용 단계
- 세탁/관리 중 발생 배출
- 폐기/재활용

앱/발표 표기 문구:

```text
본 앱의 탄소배출량은 의류 소재의 원료/소재 생산 단계 중심 추정값입니다.
제조, 유통, 사용, 폐기 전 과정의 탄소배출량은 포함하지 않으며,
실제 제품의 생산 국가, 공정, 염색 방식, 운송 방식 등에 따라 달라질 수 있습니다.
```

## 출처 후보

### 1순위: Textile Exchange LCA / LCI

- Textile Exchange LCA Studies: https://textileexchange.org/life-cycle-assessment-studies/
- Textile Exchange LCI Library: https://textileexchange.org/lci-library/

사용 이유:

- 섬유 원료 및 소재 생산 단계 LCA와 직접 관련이 있다.
- Textile Exchange는 cotton LCA를 공개했고, polyester, cashmere, nylon, leather, wool, mohair 등 추가 LCA를 순차적으로 공개할 계획을 밝히고 있다.
- LCI Library는 raw material production 또는 initial processing 범위의 데이터를 다룬다.

### 2순위: Cascale / Higg MSI

- Cascale Higg MSI: https://cascale.org/topic/higg-msi/
- Higg Index brochure: https://cascale.org/wp-content/uploads/2021/09/Higg-Index-Brochure-.pdf

사용 이유:

- 패션/섬유 산업에서 소재별 환경영향 평가 체계로 널리 알려져 있다.
- cotton, polyester, nylon, leather 등 소재 데이터 업데이트가 지속되고 있다.
- 단, 공개 수치 접근이 제한될 수 있으므로 발표에서는 "보조 참고 체계"로 사용하는 것이 안전하다.

### 3순위: WRAP / 공개 LCA 논문

- WRAP Clothing Knowledge Hub: https://ckh.wrap.org.uk/clothingKnowledgeHub/impacts
- WRAP Textiles Footprint Tool: https://www.wrap.ngo/resources/report/wrap-textiles-footprint-tool

사용 이유:

- 의류 제품 탄소·물·폐기물 영향과 관련된 공개 자료가 있다.
- 특정 소재 수치가 부족할 때 보조 근거로 사용할 수 있다.

## 현재 DB 소재 목록

| 우선순위 | 한글명 | 영문 표준명 | 현재 계수 | 단위 | 별칭 | 출처 후보 | 확정 상태 | 비고 |
|---|---|---|---:|---|---|---|---|---|
| A | 면 | cotton | 8.3 | kg CO2eq/kg textile | 면, 코튼, cotton, COTTON | Textile Exchange Cotton LCA / LCI | 검토 필요 | 사용 빈도 높음. 최우선 확정 |
| A | 폴리에스터 | polyester | 9.5 | kg CO2eq/kg textile | 폴리에스터, polyester, POLYESTER, poly | Textile Exchange 예정 LCA / Higg MSI / 공개 LCA | 검토 필요 | 버진/재생 구분 필요 |
| A | 나일론 | nylon | 11.0 | kg CO2eq/kg textile | 나일론, nylon, NYLON, polyamide | Textile Exchange 예정 LCA / Higg MSI | 검토 필요 | polyamide와 동일 매핑 |
| A | 레이온 | rayon | 6.4 | kg CO2eq/kg textile | 레이온, rayon, RAYON | 공개 LCA / man-made cellulosic fiber 자료 | 검토 필요 | viscose와 구분 또는 통합 기준 필요 |
| A | 비스코스 | viscose | 6.4 | kg CO2eq/kg textile | 비스코스, viscose, VISCOSE, viskose | 공개 LCA / Textile Exchange materials 자료 | 검토 필요 | rayon과 같은 계수 사용 중 |
| A | 스판덱스 | spandex | 12.0 | kg CO2eq/kg textile | 스판덱스, 엘라스테인, spandex, elastane, lycra | Higg MSI / 공개 LCA | 검토 필요 | 혼용률은 낮지만 자주 등장 |
| A | 폴리우레탄 | polyurethane | 12.0 | kg CO2eq/kg textile | 폴리우레탄, polyurethane, PU, pu | Higg MSI / 공개 LCA | 검토 필요 | 스판덱스와 구분 필요 |
| B | 울 | wool | 13.9 | kg CO2eq/kg textile | 울, 모, wool, WOOL | Textile Exchange 예정 RWS Wool LCA / Higg MSI | 검토 필요 | 동물성 섬유라 생산 방식 영향 큼 |
| B | 아크릴 | acrylic | 10.0 | kg CO2eq/kg textile | 아크릴, acrylic, ACRYLIC, polyacryl | 공개 LCA / Higg MSI | 검토 필요 | synthetic 계열 |
| B | 린넨 | linen | 4.5 | kg CO2eq/kg textile | 린넨, 리넨, 마, linen, LINEN | 공개 LCA / WRAP | 검토 필요 | flax/linen 표기 통합 필요 |
| B | 모달 | modal | 6.0 | kg CO2eq/kg textile | 모달, modal, MODAL | man-made cellulosic fiber 공개 LCA | 검토 필요 | viscose/lyocell과 비교 필요 |
| B | 리오셀 | lyocell | 5.5 | kg CO2eq/kg textile | 리오셀, 텐셀, lyocell, tencel | 공개 LCA / Tencel 관련 자료 | 검토 필요 | 브랜드명 Tencel 별칭 포함 |
| B | 실크 | silk | 15.0 | kg CO2eq/kg textile | 실크, 견, silk, SILK | 공개 LCA / Higg MSI | 검토 필요 | 데이터 편차 가능 |
| B | 캐시미어 | cashmere | 30.0 | kg CO2eq/kg textile | 캐시미어, cashmere, CASHMERE, kashmir | Textile Exchange 예정 LCA / Higg MSI | 검토 필요 | 고배출 소재 후보 |
| B | 가죽 | leather | 20.0 | kg CO2eq/kg textile | 가죽, leather, LEATHER | Textile Exchange 예정 leather hide LCA / Higg MSI | 검토 필요 | 의류 소재 라벨에서 빈도 낮을 수 있음 |
| C | 라미 | ramie | 4.5 | kg CO2eq/kg textile | 라미, ramie, RAMIE | 공개 LCA / 보조 자료 | 검토 필요 | 사용 빈도 낮음 |
| C | 다운 | down | 18.0 | kg CO2eq/kg textile | 다운, 우모, 오리솜털, 거위솜털, down | 공개 LCA / 동물성 소재 자료 | 검토 필요 | 충전재로 별도 기준 필요 |
| C | 깃털 | feather | 12.0 | kg CO2eq/kg textile | 깃털, 오리깃털, 거위깃털, feather | 공개 LCA / 동물성 소재 자료 | 검토 필요 | down과 구분 필요 |
| C | 야크 | yak | 18.0 | kg CO2eq/kg textile | 야크, yak, YAK | 공개 LCA / 보조 자료 | 검토 필요 | 사용 빈도 낮음 |
| C | 모헤어 | mohair | 18.0 | kg CO2eq/kg textile | 모헤어, mohair, MOHAIR | Textile Exchange 예정 RMS Mohair LCA | 검토 필요 | 예정 LCA 확인 필요 |
| C | 대나무 | bamboo | 5.0 | kg CO2eq/kg textile | 대나무, bamboo, BAMBOO | 공개 LCA / viscose 계열 자료 | 검토 필요 | bamboo viscose인지 천연 bamboo인지 구분 필요 |
| C | 큐프로 | cupro | 6.0 | kg CO2eq/kg textile | 큐프로, cupro, CUPRO | 공개 LCA / 보조 자료 | 검토 필요 | 사용 빈도 낮음 |

## 우선 확정해야 할 소재

발표와 앱 시연 기준으로는 아래 소재부터 확정하는 것이 좋다.

1. 면 / cotton
2. 폴리에스터 / polyester
3. 나일론 / nylon
4. 레이온·비스코스 / rayon, viscose
5. 스판덱스·폴리우레탄 / spandex, polyurethane
6. 울 / wool

이 6개 그룹은 실제 의류 라벨에서 자주 나오고, QA 테스트에서도 등장 가능성이 높다.

## 백엔드 반영 방식 제안

최종 출처가 확정되면 `materials` 테이블에 아래 컬럼을 다시 추가하는 것을 권장한다.

```text
factor_source_name
factor_source_url
factor_scope
factor_status
factor_note
```

예시:

```text
factor_source_name: Textile Exchange Cotton LCA
factor_source_url: https://textileexchange.org/life-cycle-assessment-studies/
factor_scope: cradle-to-gate / material production estimate
factor_status: confirmed
factor_note: 팀 검토 후 최종 발표용 계수로 확정
```

현재 `database.py`는 과거의 `source`, `description` 컬럼을 제거하도록 되어 있으므로, 출처 컬럼을 추가하려면 새 컬럼명을 명확히 정해서 마이그레이션해야 한다.

## 팀 작업 순서

1. 위 표에서 A 우선순위 소재 7개를 먼저 검토한다.
2. 각 소재별로 사용할 출처 URL과 실제 계수를 확정한다.
3. 기존 개발용 계수와 최종 계수의 차이를 기록한다.
4. 최종 확정된 계수만 `BACKEND/init_data.py`와 DB에 반영한다.
5. `BACKEND/API_CONTRACT.md`의 `calculation_source`, `calculation_note`를 개발용 추정값에서 최종 출처명으로 교체한다.
6. 발표 자료에는 "원료/소재 생산 단계 중심 추정" 범위를 명시한다.

