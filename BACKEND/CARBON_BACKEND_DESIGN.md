# 탄소 계산 백엔드 개편 설계

작성일: 2026-09-11 / 버전: 0.1 / 상태: 구현 전 명세

기준: [계산 기준서 v0.2](CARBON_CALCULATION_STANDARD.md), [계수 호환성 검토](CARBON_FACTOR_COMPATIBILITY_V2.md).
현재 통합 작업본의 database.py, init_data.py, main.py와 Flutter carbon_api_service.dart를 읽어 작성했다. 실제 사용자 DB는 조회하거나 변경하지 않았다.

## 1. 설계 결정

소재 사전, 계수 버전, 적용 정책, 계산 결과를 분리한다. 현재 materials.carbon_factor는 구형 경로 호환용으로 유지하고 새 계산에서는 직접 참조하지 않는다. 후보 계수가 존재한다는 이유로 자동 사용하지 않는다.

```text
materials ──< material_factors
                  ↑
calculation_profiles ──< profile_factors
                  │
입력 → 소재 정규화 → 정책에 지정된 계수 선택 → 무게 결정 → 계산
                                                       │
                                      analysis_results + 근거 스냅샷
```

계수 최종 선정 전에도 저장 구조와 독립 계산 모듈을 구현·시험할 수 있다. 사용자용 정책 활성화는 선정 계수가 준비된 후 수행한다.

## 2. 데이터 구조

### materials: 기존 소재 사전 유지

id, name_ko, name_en, aliases를 유지한다. 기존 carbon_factor와 unit은 구형 호환 컬럼이다. 같은 소재에 단섬유·필라멘트·재생 등 여러 계수를 연결한다. 기존 별칭을 일괄 재작성하지 않는다.

### material_factors: 계수별 불변 버전

| 필드 | 형식·제약 | 역할 |
| --- | --- | --- |
| id | 정수 PK | 내부 식별자 |
| factor_key, version | 문자열, 조합 UNIQUE | 영구 계수 식별자와 버전 |
| material_id | materials FK, 삭제 제한 | 소재 연결 |
| value_decimal | TEXT, 유한한 Decimal 검증 | 원문 유효숫자를 보존한 값 |
| unit, method, scope | 필수 문자열 | 단위·산정 지표·경계 |
| product_form, production_system | 필수 문자열 | 단섬유/실 등, 버진/재생/미상 |
| geography | 문자열 | 자료 대상 지역; unknown 명시 가능 |
| publication_year | 정수 또는 null | 발행연도 |
| data_years_json | TEXT JSON | 원자료 연도 목록; 미확인은 빈 목록 |
| source_name, source_url, source_locator | 필수 문자열 | 문헌명·주소·표/페이지 |
| evidence_type | literature/derived/placeholder | 근거 종류 |
| review_status | candidate/selected/rejected | 검토 상태 |
| usage_scope, limitations_json | 문자열 / TEXT JSON | 허용한 용도와 한계 |
| carbon_accounting_json | TEXT JSON | 저장 탄소·토지이용 등 처리 설명 |
| components_json | TEXT JSON 또는 null | 보고된 biogenic/fossil/land_use 값 |
| reviewed_at, review_note | 시각 / 문자열 | 선정·보류 근거 |
| created_at | 시각 | 생성 기록 |

후보 단계의 상태 변경은 이력으로 기록한다. 정책에 편입해 사용한 계수의 값·단위·출처·조건은 수정하지 않고 새 버전을 추가한다. 철회 시 기존 기록을 삭제하지 않고 새 정책에서 제외한다. components 합산으로 value_decimal을 대체하지 않는다. 서버 시작 시 문헌 다운로드나 후보 선정은 수행하지 않는다.

### calculation_profiles 및 profile_factors: 재현 가능한 선택 정책

calculation_profiles: id, key, version(조합 UNIQUE), status(draft/active/retired), formula_version, method, scope, usage_scope, created_at.

profile_factors: profile_id, material_id, factor_id, selection_assumption. 초기에는 (profile_id, material_id) UNIQUE로 한 소재당 하나의 명시적 선택을 허용한다. 정책 활성화 검증은 계수의 material_id 일치·selected 상태·method/scope 호환·usage_scope 적합성을 확인한다.

계수의 가장 큰 id나 최신 날짜로 자동 선택하지 않는다. 정책은 활성화 후 불변으로 두고 교체 시 새 버전을 만든다. 한 요청에서 정책 ID를 한 번 고정하여 중간 갱신이 계산과 저장을 갈라놓지 않게 한다. 초기 설정에 활성 정책이 없으면 새 계산 API는 준비되지 않음을 명시한다.

### analysis_results: 기존 컬럼 + 추가 컬럼

| 추가 필드 | 형식 | 의미 |
| --- | --- | --- |
| result_kind | nullable 문자열 | garment_estimate / legacy_factor / legacy_unknown |
| formula_version | nullable 문자열 | 실제 사용 공식 |
| profile_id | nullable FK | 신규 정책 참조 |
| snapshot_schema_version | nullable 정수 | 스냅샷 해석 규격 |
| calculation_snapshot_json | nullable TEXT | 계산 당시 입력·계수·가정·결과 |
| client_request_id | nullable 문자열 | 선택적 요청 중복 방지 키 |
| request_hash | nullable 문자열 | 키 재사용 충돌 판정 |

(user_id, client_request_id)에 UNIQUE 제약을 두되 null 키는 중복 방지 대상에서 제외한다. 새 결과는 기존 숫자 컬럼과 스냅샷을 한 트랜잭션에서 저장한다. 기존 숫자 컬럼은 화면 호환용이며 새 계산의 정확한 값은 Decimal 문자열 스냅샷에 보존한다.

## 3. 스냅샷 규격

```json
{
  "schema_version": 1,
  "formula_version": "fiber_mass_v2",
  "profile": {"key": "example", "version": "1"},
  "scope": "fiber_production_estimate",
  "method": "EF3.1_climate_change_total",
  "input": {"materials": {"cotton": "100"}, "clothing_type_id": null},
  "normalized_materials": [{"standard_name": "cotton", "ratio": "1"}],
  "weight": {
    "source": "direct", "representative_g": "200", "min_g": "200", "max_g": "200",
    "catalog_version": null, "mass_basis": "total_garment_mass_as_fiber_proxy"
  },
  "factors": [],
  "assumptions": ["total_garment_mass_as_fiber_proxy"],
  "rounding": {"mode": "ROUND_HALF_UP", "decimal_places": 2},
  "results": {"unit": "kg CO2eq"}
}
```

위 예시는 구조 설명용이며 factors와 results를 채워야 유효하다. factors에는 적용값·단위·소재 비율·계수 key/version·출처·방법·경계·선택 가정을 복사한다. results에는 반올림 전 대표/하한/상한과 표시값을 모두 문자열로 저장한다. raw OCR 텍스트는 기존 컬럼으로 관리하며 스냅샷에 중복하지 않는다.

이력은 현재 계수 테이블을 다시 조회해 근거를 만드는 대신 이 스냅샷을 읽는다. 과거 스냅샷이 없으면 null과 provenance_status=unavailable을 반환한다. 현재 계수로 과거 근거를 추정 생성하지 않는다.

## 4. API 전환

기존 `/api/carbon/calculate`와 기존 숫자 계산 의미를 우선 유지한다. 새 정책·대표 무게·반올림이 결과를 바꾸므로 `/api/v2/carbon/calculate`로 분리한다. 새 엔드포인트에도 Bearer 인증을 요구한다.

새 요청: materials, weight_grams 또는 clothing_type_id, composition_scope(single/unknown/multiple), raw_ocr_text(선택). composition_scope는 필수이며 사용자 확인 결과를 뜻한다. unknown/multiple은 초기 버전에서 계산 보류한다. 실측과 타입이 함께 있으면 실측이 우선하고 잘못된 타입 ID는 입력 오류로 알린다. 클라이언트가 임의의 factor_id를 지정하지 않으며 서버 활성 정책을 사용한다.

새 응답에서도 carbon_factor, carbon_footprint, carbon_footprint_min/max, min/max_weight_grams, unit, saved_result_id를 유지한다. representative_weight_grams, formula_version, result_kind, profile_version, provenance_status, assumptions, emission_factors를 추가한다. average_carbon_footprint는 대표값의 호환 별칭이며 통계 평균이 아니다. 신규 클라이언트는 carbon_footprint를 표시한다.

| 조건 | HTTP / error_code | 저장 |
| --- | --- | --- |
| 등록되지 않은 소재 | 400 / MATERIAL_NOT_FOUND | 없음 |
| 등록 소재에 선정 계수 없음 | 422 / FACTOR_UNAVAILABLE | 없음 |
| 활성 정책 미설정 | 503 / CALCULATION_PROFILE_UNAVAILABLE | 없음 |
| 복합/미확인 부위 | 422 / COMPOSITION_SCOPE_UNSUPPORTED | 없음 |
| 무게 없음·오류 | 기존 WEIGHT_* 코드 유지 | 없음 |
| 같은 중복 방지 키로 다른 요청 | 409 / IDEMPOTENCY_CONFLICT | 추가 없음 |

Idempotency-Key는 선택적 헤더로 받고 사용자별로 분리한다. 인증 후 기존 키를 먼저 조회한다. 같은 정규 요청이면 당시 결과를 반환하며 정책이 변경되어도 재계산하지 않는다. 요청 해시는 필드 순서를 정규화한 요청 전체로 만든다. 새 키 동시 요청 충돌은 DB UNIQUE로 해결하고 실패 트랜잭션 롤백 후 기존 결과를 조회한다. 저장 실패 시 성공 응답을 반환하지 않는다.

`/me/history`와 `/history`는 기존 필드에 신규 필드를 추가한다. 사용자 필터를 유지한다. `/materials`의 기존 배열 응답은 유지하고 신규 정책의 계산 가능 여부는 별도 버전 카탈로그로 제공한다. 소재 인식 가능과 탄소 계산 가능은 별도 상태다.

## 5. 마이그레이션 순서

1. 서버를 쓰기 중지 상태로 만들고 SQLite backup API로 일관된 백업을 생성한다. WAL 환경에서 DB 본체만 복사하지 않는다. 복원 시험은 복제본으로 한다.
2. database.py import 시 schema를 변경하는 호출을 제거하고 명시적 버전 마이그레이션 명령으로 전환한다. 앱 시작은 스키마 버전을 확인하고 불일치하면 실행 안내와 함께 실패한다.
3. source/description 제거용 테이블 재구성 경로를 없앤다. 기존 출처 컬럼과 값을 보존한다.
4. 새 테이블과 nullable 결과 컬럼을 추가한다. 기존 계정·토큰·분석 ID·숫자는 유지한다. schema_migrations로 적용 버전을 기록한다.
5. seed는 없는 소재만 삽입하도록 바꾼다. 기존 값·별칭 수정은 별도 명시적 작업으로 수행한다. 새 계수 seed는 key/version이 있으면 덮어쓰지 않는다.
6. 기존 이력은 provenance_status=unavailable로 조회한다. 무게 컬럼의 유무만으로 `/analyze` 발생 여부를 확정하지 않는다. 확실한 증거 없는 기록은 legacy_unknown으로 둔다.
7. 앞으로 구형 `/analyze`가 만든 기록은 legacy_factor로 식별하고 응답·이력에서 계수 단위를 명확히 하는 별도 호환 변경을 수행한다. 과거 수치를 일괄 단위 변환하지 않는다.
8. 복제 DB에서 마이그레이션 재실행·데이터 보존 검증 후 배포한다. reset_db.py는 사용하지 않는다.

장애 시 구형 API 경로로 전환할 수 있게 유지한다. 신규 데이터 발생 후에는 백업 복원으로 무조건 되돌리지 않는다. 추가 데이터 보존과 복원 범위를 확인한다. 이번 설계 단계에서 백업 또는 마이그레이션은 실행하지 않았다.

## 6. 모듈 경계와 검증

- carbon/domain.py: Decimal 기반 정규화·계산·최종 ROUND_HALF_UP. DB 및 HTTP 의존성 없음.
- carbon/factors.py: 정책 고정·계수 조회·사용 적합성 검증.
- carbon/weights.py: 실측/버전 카탈로그 결정.
- carbon/service.py: 요청 중복 방지·스냅샷 작성·결과 저장 트랜잭션.
- main.py: 인증·요청/응답 변환. 기존 OCR 변경을 보존한다.
- migrations/: 스키마 버전 전환과 보존 검증.

검증은 (1) 순수 계산 경계와 반올림, (2) candidate 거부 및 잘못된 소재/정책 연결, (3) 계수 교체 후 이력 불변, (4) 동시 중복 요청과 계정 격리, (5) 출처 컬럼이 있는 구형 DB 및 재실행 보존, (6) Flutter 구형/신규 응답 파싱과 보류 표시를 포함한다. 계산 시험은 합성 fixture를 사용해 문헌 후보가 선정된 것처럼 만들지 않는다.

## 7. 프런트 연동 주의

현재 Flutter는 실패 메시지에서 로컬 추정 저장을 안내한다. 신규 계산 보류를 로컬 탄소값으로 대체하면 지원 조건이 무효화된다. v2 전환 시 미계산 의류 저장은 허용하되 carbon 상태를 unavailable로 구분하고 0 배출이나 성공으로 표시하지 않도록 함께 변경한다. 실제 로컬 저장 경로 추적은 구현 전 추가 확인 대상이다.

## 8. 구현 단위

1. 불변 계수·정책·스냅샷 구조와 복제 DB 마이그레이션 시험.
2. 순수 계산 모듈과 단위 시험.
3. v2 서비스·저장·이력·중복 방지 통합 시험.
4. 프런트 보류 상태와 상세 근거 연동.
5. 선정 계수 정책 활성화 및 실제 시연 검증.

계수 미선정은 1~4의 설계·시험을 막지 않는다. 운영 활성화와 계수 자동 매핑은 5단계에서 수행한다.
