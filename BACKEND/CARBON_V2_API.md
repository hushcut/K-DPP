# 탄소 계산 v2 API 구현

2026-09-12. 기존 v1 계산과 분리된 신규 경로다. 실제 사용자 DB에 정책이나 문헌 계수를 추가하지 않았다.

## 요청

`POST /api/v2/carbon/calculate`

Bearer 인증 필수. 선택적 `Idempotency-Key` 헤더(1~128자)를 제공하면 계정별 재요청 중복 저장을 방지한다.

```json
{
  "materials": {"cotton": 100},
  "weight_grams": 200,
  "composition_scope": "single"
}
```

무게 대신 clothing_type_id를 전달하면 서버 카탈로그의 대표/하한/상한을 사용한다. 현재 카탈로그는 placeholder이며 결과에도 표시한다. 무게와 타입을 함께 보내면 무게가 우선한다. 유효하지 않은 타입은 거부한다. multiple/unknown 부위는 계산하지 않는다. raw_ocr_text는 선택적이며 기존 OCR 컬럼에만 저장한다.

## 활성 정책

status=active, usage_scope=public_estimate인 정책이 정확히 하나 있어야 한다. 범위는 fiber_production_estimate, 공식은 fiber_mass_v2다. 없음 또는 여러 개이면 503 CALCULATION_PROFILE_UNAVAILABLE이다. 서버가 임의로 최신 정책을 고르지 않는다.

정책에 연결된 계수는 selected이고 literature/derived여야 하며 소재 연결·단위·방법·범위·용도가 일치해야 한다. 현재 문헌 후보를 자동으로 선정하거나 활성화하지 않는다. 실제 자료 선정과 정책 관리 기능은 후속 작업이다.

## 응답 및 근거

기존 Flutter가 요구하는 carbon_factor, carbon_footprint, carbon_footprint_min/max, min/max_weight_grams, unit, saved_result_id를 제공한다. 대표 무게, 계산 버전, 정책 버전, 적용 가정, 계수 출처와 버전도 반환한다. 평균 필드는 대표값의 호환 별칭이다.

한 DB 커밋으로 결과 숫자와 스냅샷을 함께 저장한다. 스냅샷에는 원본 소재 입력·정규화 비율·계수의 조건과 출처·정책·무게·반올림 전후 결과를 담는다. /me/history와 /history에서 calculation_snapshot으로 반환한다. 기존 스냅샷 없는 이력은 provenance_status=unavailable로 표시한다.

스냅샷 JSON이 손상된 이력은 전체 조회를 실패시키지 않고 provenance_status=invalid와 빈 스냅샷으로 표시한다. 손상된 저장 결과는 같은 Idempotency-Key로 재생하지 않고 500 SAVED_RESULT_INVALID로 중단해 잘못된 근거를 정상 결과처럼 반환하지 않는다.

동일 계정·동일 키·동일 입력은 저장된 응답을 돌려준다. 정책 비활성화 후에도 동일 키 재요청은 기존 결과를 반환한다. 동일 키의 다른 입력은 409 IDEMPOTENCY_CONFLICT다. 키를 생략하면 매 요청 새 이력을 생성한다. 숫자 200과 문자열 200.0은 같은 입력으로 취급하되 별칭 교체나 OCR 텍스트 변경은 다른 요청으로 처리한다.

유일 인덱스 충돌 시 롤백 후 기존 결과를 조회한다. 일반 저장 실패도 롤백하며 성공으로 응답하지 않는다. 실운영 부하·동시 요청 스트레스 테스트는 아직 수행하지 않았다.

## 검증 범위 및 미완료

테스트용 가상 계수로 손계산·카탈로그·실측 우선·후보 거부·계정 격리·재요청·과거 근거 보존·저장 실패 롤백·잘못된 숫자를 검증한다. 검증 오류 응답은 JSON 변환이 불가능한 예외 객체 및 입력 원문을 제외하고 type/loc/msg만 반환하도록 수정했다.

선정된 계수와 공개된 정책은 DB 단계에서 수정·삭제를 차단한다. 정책은 draft로 만든 뒤 호환되는 selected 계수를 연결해야 active로 전환할 수 있으며, 변경 시 기존 값을 덮어쓰지 않고 새 버전을 만들어야 한다.

새 정책 버전의 검증·등록·종료는 `python -m carbon.policy_admin` 관리 명령으로 수행한다. 기본 실행은 검증만 하고 `--apply`를 붙인 경우에만 한 트랜잭션으로 반영한다. 사용법과 manifest 형식은 `POLICY_ADMIN.md`에 정리했다.

면 2.88과 폴리에스터 4.55는 `research_scenario` 정책으로만 로컬 DB에 등록했다. 공개용 `public_estimate` 정책으로 승격하지 않았으므로 현재 v2 공개 계산 엔드포인트가 이 연구값을 자동 사용하지 않는다.

프런트의 v2 전환, 미계산 상태 UI와 공개 서비스용 계수의 별도 승인은 아직 남아 있다. 관리 명령이 연구값을 공개값으로 자동 승격하지는 않는다. v1은 기존 경로를 계속 사용한다. 서버 시작 시 기존 additive 스키마 준비 흐름도 유지된다.
