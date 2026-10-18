# 탄소 V2 develop 통합 — 2026-10-18

2026-10-19 리뷰 보완 및 무료 공개용 IDEMAT 절차는
[CARBON_V2_REVIEW_RESOLUTION.md](CARBON_V2_REVIEW_RESOLUTION.md)를 우선 따른다.

기준: develop 1cb3684. 로그인·카카오·옷장 백업·V1 API를 유지하고
jw/carbon-v2-postgres의 계산·계수 정책·스냅샷을 편입했다.
앱은 아직 V1을 사용하며 전환은 별도 작업이다.

## DB 준비

```powershell
docker compose up -d --wait
python -m alembic upgrade head
python -m alembic check
```

새 리비전 c7d2e0180001은 옷장 리비전 a28c2a50b363 뒤에 연결된다.
소재 계수·계산 정책·정책별 계수 테이블과 결과의 nullable 컬럼 7개를 추가한다.
기존 데이터와 출처 미확인 상태를 유지한다. 자체 ensure_schema는 사용하지 않는다.
트리거 10개, 용도별 활성 정책 1개만 허용하는 부분 고유 인덱스를 생성한다.
V2 근거가 있으면 downgrade를 중단한다. 복원은 기존 배포 백업 절차를 따른다.

## 계수 결정

- 면: 2.88 kg CO2eq/kg fiber. Cotton 2026 인쇄 p.250 표 G-14,
  GLO country averages의 EF 3.1 climate-change total.
- 폴리에스터 연구 v3: EF 3.1 표 71~73 표시 총값의 단순 평균 4.543333… kg CO2eq/kg fiber.
  표 67 공표 평균 4.55와 구분한다. 필라멘트·재생 폴리에스터의 대표값이 아니다.
- 총 의류 무게를 섬유 무게로 가정한 소재 생산 단계 추정. 제조·운송·사용·폐기는 제외한다.
- 나머지 소재는 근거 확보 전 V2 계산 거부. 개발용 계수로 보충하지 않는다.

두 보고서는 공개·홍보 주장과 소재 간 비교에 사용하지 않도록 명시한다.
선정값은 연구·캡스톤 시나리오에만 사용한다. public_estimate로 승격하지 않는다.
외부 공개·기업 서비스 적용에는 사용 조건과 대표성을 만족하는 별도 데이터가 필요하다.

연구용 manifest 등록은 마이그레이션과 분리하여 명시적으로 실행한다.

```powershell
python -m carbon.policy_admin publish policies/textile_exchange_2026_research.json
python -m carbon.policy_admin publish policies/textile_exchange_2026_research.json --apply
$env:K_DPP_CARBON_USAGE_SCOPE = "research_scenario"
python -m uvicorn main:app
```

기본은 public_estimate. 승인된 공개 정책이 없으면 V2는 503이다.
연구 설정은 응답에 research_only=true, usage_scope와 한계를 표시한다.
이는 환경 전체의 용도를 선택하는 설정이다. 공개 서버에서 연구용 우회 설정으로 사용하지 않는다.
같은 Idempotency-Key 재요청은 정책·환경 변경 후에도 원래 저장 응답을 재사용한다.

## 앱 연결

POST /api/v2/carbon/calculate, Bearer 인증.
materials, weight_grams 또는 clothing_type_id, composition_scope=single이 필요하다.
직접 입력 무게는 1~100000g. 카탈로그 무게는 placeholder로 표시한다.
혼합 부위·미확인 부위는 거부한다. Idempotency-Key로 중복 저장을 방지한다.
이력에는 당시 정책·소재별 계수와 출처·반올림 전 결과를 보존한다.
현재 앱의 V1 호출과 기존 계수표는 변경하지 않았다.

## 검증 방법

_test로 끝나는 별도 PostgreSQL DB에서 pytest를 실행한다.
기존 데이터 보존·모델 일치·빈 DB 왕복 migration, 정책 불변성,
계산·재요청·계정 격리·탈퇴·연구 정책·미지원 소재를 검증한다.

2026-10-18 Windows/Python 3.12, PostgreSQL 18.6 검증:
전체 회귀 실행 525 passed / 1 failed. 실패는 기존 옷장 테스트
test_very_deep_json_is_rejected_before_saving[5000]이며,
수정 없는 develop 1cb3684에서도 동일하게 400(예상 422)으로 재현했다.
Linux CI 결과는 별도로 확인해야 한다. Docker 이미지 빌드는 이 PC에 Docker가 없어 실행하지 않았다.
AI 모듈 결합 검사는 통과했다.
최종 V2·마이그레이션 대상 검증은 실제 탈퇴 동시성 2건과 정책 연결 우회 방지까지 포함해 74 passed다.

## 출처

- [Cotton LCA 2026](https://textileexchange.org/app/uploads/2026/03/Cotton-LCA-Technical-Report.pdf)
- [Polyester LCA 2026](https://textileexchange.org/app/uploads/2026/06/Polyester-LCA-Technical-Report.pdf)
