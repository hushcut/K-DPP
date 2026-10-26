# PR 88 리뷰 보완 및 전환 기준

기록일: 2026-10-19. 독립 검토자의 최종 승인 기록이 아니라 구현 대응 기록이다.

1. V1/V2 공통 입력 제한: 소재 최대 20칸, 이름 64자, OCR 4,000자.
   칸별 Decimal 검증 전에 개수를 거절한다. V2는 Decimal 정밀도를 유지한다.
2. TE 폴리에스터 4.55의 표 67 지표와 EF 3.1 호환성을 단정하지 않는다.
   [원문](https://textileexchange.org/app/uploads/2026/06/Polyester-LCA-Technical-Report.pdf)의
   인쇄 147~148쪽 표 71~73에서 EF 3.1 총값 SF1=4.74, SF2=4.93, SF3=3.96을 확인했다.
   새 연구 매니페스트 v3은 이 표시값의 단순 평균 4.543333…을 별도 파생 시나리오로 쓴다.
   보고서 공표 평균 4.55의 재현값이라고 주장하지 않는다. 표 67은 산출에서 제외한다.
   과거 검토 기록은 보존하되 현재 매니페스트로 소급 승인하지 않는다.
   공개값으로 재사용하거나 홍보하지 않는다.
   공개용은 별도 IDEMAT 선택이며 TE 연구값을 보충값으로 쓰지 않는다.
3. 이전 CARBON_FACTOR_REVIEW_V1 / CARBON_FACTOR_COMPATIBILITY_V2 기록을 보존했다.
   evidence_reviewed_at은 실제 문헌 확인일, created_at은 등록 시각이다.
   technical_selector와 approval_reviewer/approval_date는 별개다.
   사용자 위임에 따른 Codex 기술 선정이지 외부 검증이나 팀 승인 완료가 아니다.
   이 PR은 기존 V1 계수 출처 확정 과제 R3를 완료하지 않는다.
4. 공개 등록은 코드가 생성하는 검토된 IDEMAT 매니페스트와 정확히 일치해야 한다.
   --free-public-release 확인도 필요하다. 유료 서비스 허가를 부여하는 옵션이 아니다.
   계수는 유한 양수, 최대 40자리/1e12까지의 계산 표현 범위를 검사한다.
   --replace-active는 관리자 잠금과 하나의 트랜잭션으로 이전 정책 은퇴/신규 활성화를 묶는다.
   실패하면 CLI 세션이 롤백되어 기존 정책을 유지한다. 변경 이력은 삭제하지 않는다.
5. V1 중앙 무게와 V2 대표 무게는 뜻이 다르다. average_carbon_footprint는
   V2에서 대표 추정값의 호환 별칭이며 통계적 평균이 아니다. value_basis로 명시한다.
   앱은 아직 V1이다. V2 전환 전 버전별 표시/합계 분리 및 출처·가정 표시가 필요하다.
   기존 V1 값을 덮어쓰거나 버전 차이를 감축량으로 표시하지 않는다.
6. 일반 이력은 스냅샷을 생략하고 소유자 전용 상세 URL을 제공한다.
   원본 증거는 DB에 보존한다. 소재 오류에는 unknown_materials를 제공한다.
7. 트리거 헬퍼의 정규화된 SHA256을 회귀시험으로 고정한다.
   변경이 필요하면 기존 DDL 수정이 아니라 새 마이그레이션을 작성한다.
8. 배포/시연은 아래 별도 절차로 등록한다. 병합만으로 정책이 활성화되거나 앱이 바뀌지 않는다.

## Linux / Docker Compose 배포 담당자 절차

배포 담당자가 deploy/README.md의 환경·비밀값을 준비한 서버에서 실행한다.
작업 폴더는 저장소의 deploy/다(BACKEND/compose.yaml은 DB 전용 개발 환경이다).
연구용 환경변수를 공개 서버에 설정하지 않는다.

```sh
docker compose up -d --build --wait
# 기존 pre-migrate-backup → migrate → app 절차 성공 후, 등록 없이 JSON 확인
docker compose run --rm --no-deps migrate python -m carbon.public_policy
```

동일 이미지에서 JSON을 생성해 컨테이너에 읽기 전용으로 마운트한다.
--no-deps는 이미 성공한 백업·마이그레이션 서비스를 다시 시작하지 않기 위한 것이다.

```sh
docker compose run --rm --no-deps migrate python -m carbon.public_policy > /tmp/kdpp-public-manifest.json
docker compose run --rm --no-deps -v /tmp/kdpp-public-manifest.json:/tmp/manifest.json:ro migrate python -m carbon.policy_admin publish /tmp/manifest.json --free-public-release
# 출처·무료 공개 조건·UI 가정 표시 확인 후에만 실제 적용
docker compose run --rm --no-deps -v /tmp/kdpp-public-manifest.json:/tmp/manifest.json:ro migrate python -m carbon.policy_admin publish /tmp/manifest.json --free-public-release --apply
```

호스트 Python 사용 시 BACKEND 작업 폴더에서 동일 명령을 실행하고 배포 DB URL을 제공한다.
호스트 실행은 requirements 설치가 필요하다. 등록 후 인증된 V2 요청으로
면60/폴리40, 500g → 0.85 kg CO2eq를 확인한다. 미지원 양수 소재는 전체 계산을 거부한다.
다음 버전의 검토된 정책 교체는 publish에 --replace-active를 추가한다.
새 공개 버전은 코드의 승인 선택과 함께 재검토해야 한다.

무료 교육용 공개 조건과 출처 표기(data from www.ecocostsvalue.com)를 앱에서도 지켜야 한다.
유료 기업 판매는 별도 라이선스 검토 전 차단한다. 본 작업은 배포 DB를 변경하지 않는다.
