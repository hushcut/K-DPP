# 탄소 V2 앱 적용·출처 표시 배포 확인

이 변경은 앱을 `/api/v2/carbon/calculate`에 연결한다. PR 병합과 앱 빌드만으로
배포 DB의 공개 정책이 등록되지는 않는다. 실제 서버 작업은 배포 담당자가 수행한다.
서버의 비밀값/DB 접속 정보를 저장소에 추가하지 않는다.

## 적용 순서

1. 기존 `deploy/README.md` 절차대로 백업·복원 검사 → 마이그레이션 → 서버 시작을 완료한다.
2. deploy/ 폴더에서 아래의 무료 교육용 IDEMAT 선택을 검증·등록한다.
   연구용 `K_DPP_CARBON_USAGE_SCOPE=research_scenario` 설정은 공개 서버에 사용하지 않는다.
3. 인증된 V2 계산과 이력의 출처를 확인한 뒤 새 앱을 배포한다.
4. 앱의 사용자 정의 `CARBON_API_ENDPOINT`가 남아 있으면 V2 경로로 변경한다.
   일반적으로 `API_BASE_URL`만 설정하면 된다. 구버전 서버 응답/연구용 응답은 새 앱이 거부한다.

```sh
# 작업 폴더 deploy/, 기존 배포 환경 준비 및 서버 시작 완료 후
docker compose run --rm --no-deps migrate python -m carbon.public_policy > /tmp/kdpp-public-manifest.json
docker compose run --rm --no-deps -v /tmp/kdpp-public-manifest.json:/tmp/manifest.json:ro migrate python -m carbon.policy_admin publish /tmp/manifest.json --free-public-release
# 검증 성공 및 무료 교육용 공개 조건 확인 후 실제 등록
docker compose run --rm --no-deps -v /tmp/kdpp-public-manifest.json:/tmp/manifest.json:ro migrate python -m carbon.policy_admin publish /tmp/manifest.json --free-public-release --apply
```

이미 같은 정책이 등록되어 있으면 중복 등록 오류가 정상이다. DB 행을 지우거나
retire하여 다시 넣지 않는다. 기존 정책 상태를 배포 담당자가 확인하고 V2 요청으로 검증한다.
다른 활성 정책을 교체할 때는 대상과 승인된 새 버전을 확인한 후 `--replace-active`로
한 트랜잭션에서 교체한다. 무료 교육용 옵션은 유료 판매 라이선스를 부여하지 않는다.

## 배포 확인표

- 면 60% + 폴리에스터 40%, 실측 500g: 대표 추정값 0.85 kg CO2eq.
- 유형 선택: `clothing_type_id` 전달. 임의의 무게 범위나 범위 중간값을 실측값으로 보내지 않는다.
- 응답: `formula_version=fiber_mass_v2`, `usage_scope=public_estimate`, `research_only=false`,
  `calculation_scope=fiber_production_estimate`, 실제 계수의 `calculation_source` 존재.
- 리포트의 출처 두 곳에 IDEMAT 이름, `data from www.ecocostsvalue.com`, 정책 버전 표시.
  폴리에스터 대체 공정·무료 교육용 제약과 전체 무게를 섬유 무게로 가정함을 표시.
- 캐시미어/울/스판 등 현재 미지원 양수 소재: 422, 소재명 안내, 새 계산 이력/옷장 저장 없음.
- 정책 미등록: 503 및 저장하지 못했다는 안내. V1 임시값으로 우회하지 않음.
- 로그인 후 이력 복원 및 옷장 백업 복원 후에도 해당 결과의 출처 유지.
- 기존 V1·앱 임시값은 그대로 보존하며 IDEMAT 출처를 덧씌우지 않음.
  홈의 서로 다른 기준은 나눠 표시하고 그 차이를 감축량으로 표시하지 않음.

네트워크 장애·세션 만료 때 기존 앱 임시 추정 저장 기능은 유지하지만,
리포트에 문헌 출처 미확정인 임시값으로 명시하고 V2 합계와 분리한다.
캐시미어 등 미지원 소재의 새 문헌계수 확보는 이번 변경의 범위가 아니다.

## 되돌리기

문제가 생기면 앱을 이전 배포본으로 되돌리고 V1 API를 사용한다(서버 V1은 유지).
기존 V2 결과·스냅샷·계수를 수정/삭제하거나 V2 근거가 있는 DB를 강제 downgrade하지 않는다.
자세한 조건은 BACKEND/PUBLIC_FACTOR_DECISION.md 및 CARBON_V2_REVIEW_RESOLUTION.md를 따른다.
