# 소재·혼용률 근거 검증과 소수점 처리

2026-09-13. 기준 커밋 `20419359b9ba776058177903c7f3dc20c1264fdc` 이후 작업이다.
소재명이나 비율을 만들어 내던 경로를 제거하고, 명시된 조성을 검증한 뒤 반환하도록
파서를 수정했다. 파일럿 이미지·정답·생성기는 변경하지 않았다.

## 동작 변경

| 입력 예 | 이전 결과 | 수정 결과 |
|---|---|---|
| `RAYON 60% UNKNOWN 40%` | 레이온 100%, success | failed, 빈 소재 |
| `섬유 혼용률 100%` | 면 100%, success | failed, 빈 소재 |
| `COTTON 80% POLYESTER 80%` | 면 50%, 폴리에스터 50% | failed, 빈 소재 |
| `COTTON SIZE 100` | 면 100% | failed, 빈 소재 |
| `COTTON 92.5% SPANDEX 7.5%` | 면 95%, 스판덱스 5% | 면 92.5%, 스판덱스 7.5% |
| `COTTON 33.33% POLYESTER 33.33% NYLON 33.34%` | 소수 비율 오독 | 입력한 세 비율 유지 |
| 불완전한 겉감 + 안감 100% | 일부 조성 확정 또는 안감 대체 가능 | failed, 빈 소재 |

공개 함수 `parse_materials`와 `parse_label`은 같은 부위 파싱·검증·선택 경로를 사용한다.
실패 응답은 기존 `status: failed`, `materials: {}` 형식을 유지한다.

## 적용한 판정 기준

1. 소재와 수치가 같은 행 또는 같은 부위의 인접한 열 배치에서 대응해야 한다.
   관계없는 행이나 부위를 건너뛰어 숫자를 가져오지 않는다.
2. `100%`만 보고 면을 추가하거나, 빠진 소재명을 면·폴리에스터로 추정하지 않는다.
   단일 소재 60→100, 작은 부분합의 누락 숫자 보충, 80+80→50+50 등의 보정도 하지 않는다.
3. 수치는 전체 토큰으로 검사한다. 음수, 100 초과, 손상된 소수점, 중복 `%`,
   유니코드 부호·근사·비교 기호, 무게·길이·온도 단위가 있는 값은 비율로 확정하지 않는다.
   `10086`이나 `2000`을 100으로 복구하던 처리를 제거했다.
4. 내부 합계는 `Decimal`로 계산하고 정확히 100인 완성 조성만 채택한다.
   99, 101, 99.9 등은 재정규화하지 않고 실패한다. 소수점(`.`)과 소수 쉼표(`,`),
   전각 숫자를 읽고, API와 한국어 표시에서 지원한 소수 비율을 한 자리로 잘라 내지 않는다.
5. `%`가 없더라도 `COTTON 60 POLYESTER 40`이나 명확한 숫자 열은 처리한다.
   `SIZE 100`, `100 g`, `100 cm`, `100℃` 등으로 누락된 혼용률을 채우지 않는다.
6. 다른 언어로 반복된 **완성 조성**은 소재 키와 원래 비율이 정확히 같은 경우만 중복 제거한다.
   `60/40` 뒤의 `70/30`을 비슷하다고 합치거나 평균 내지 않는다.
7. 원문에 언급된 대표 부위를 먼저 선택한다. 최우선 겉감이 불완전하면 정상 안감으로 대체하지 않는다.
   성공 응답의 `parts`에서도 불완전한 부위는 빈 사전으로 남는다.

## API 호환성

백엔드 제품 코드와 프런트 코드는 변경하지 않았다. 백엔드는 파서의 빈 소재 결과를
기존 HTTP **422 / MATERIAL_EXTRACTION_FAILED**로 처리하고, 앱은 기존 직접 입력 흐름을 사용한다.
소재 사전은 오류 JSON의 최상위가 아니라 `detail.materials`와 `detail.partial_materials`에 있다.

의도된 변화: 이전에 합계 80%를 HTTP 200 부분 인식으로 반환하던 경우가 이제 422가 된다.
`BACKEND/tests/test_hardening.py`의 해당 기대값을 변경했고, 소수점 API 전달과
미확인 소재·모순된 비율·불완전 겉감 거부도 검증했다. OCR 후보 선택 역시 같은
`parse_materials`를 사용하므로 불완전한 조성이 정상 100% 후보로 가산되지 않는다.

## 검증 결과

- AI unittest **48개 통과**. 기존 29개와 새 근거·수치 검증 19개 메서드가 포함된다.
  새 테스트는 정상·실패 입력 **77건**을 public API의 고정 기대값으로 검증한다.
- 백엔드 `test_hardening.py` **29개 통과**. 실제 DB와 분리된 복제 폴더 및 테스트 DB에서 실행했다.
  AnyIO의 기존 deprecation 경고 1건은 기능 실패가 아니다.
- 수정 파일럿: `parse_label`·`parse_materials` 소재/비율 **80/80**, 문구 **20/20**, 대표 부위 **80/80 유지**.
- 오타가 있는 원본 파일럿: 소재/비율 **72/80 유지**. 실패 8건은 이제 `failed`, 빈 소재로 반환한다.
  실패 응답에는 대표 부위가 없으므로 원본의 부위 지표는 80/80에서 72/80으로 변한다.
  잘못된 조성을 유지하며 부위 점수만 보존하지 않았다.
- 두 파일럿의 이미지·manifest·설정·요약·미리보기 **168개 파일의 해시를 보존**했다.
- 상세 결과는 `outputs/parser_validation_review/`의 `original_pilot_after.json`,
  `corrected_pilot_after.json`, `examples_before.json`, `examples_after.json`에 기록했다.
  예시 13건은 문제를 설명하기 위해 고른 텍스트 회귀 사례이며, 실사용 정확도 표본이 아니다.

AI 검증 환경: Python 3.12.14, Pillow 12.3.0.
백엔드는 별도 venv에서 저장소에 맞는 FastAPI 0.135.1, SQLAlchemy 2.0.48,
Pydantic 2.12.5, Starlette 1.0.0, pytest 9.0.2, httpx 0.28.1 등을 사용했다.

```powershell
# AI 프로젝트 루트
python -B -m unittest discover -s tests -v
python -B scripts/evaluate_synthetic_parser.py --manifest outputs/synthetic/synthetic_v1_pilot_corrected_v1_0_2/manifest.csv --output outputs/parser_validation_review/corrected_pilot_after.json

# 별도 테스트 DB를 쓰는 격리 BACKEND 폴더
python -B -m pytest -q tests/test_hardening.py -p no:cacheprovider
```

## 범위와 다음 검증

이번 검증은 텍스트 파서와 `raw_ocr_text`를 주입한 백엔드 경로를 대상으로 한다.
Google Vision 호출, 실제 사진 163장 재평가, 새 사진 수집·모델 학습은 하지 않았다.

명확한 근거가 부족하면 실패시키는 정책이므로 성공률과 오답 확정률을 구분해서 봐야 한다.
반올림 때문에 합계가 100이 아닌 실제 라벨이나, 소재·세탁 지시·품번이 한 행에 섞인
복잡한 OCR 출력은 보수적으로 실패할 수 있다. 별도 행의 사이즈·전화번호·제품 번호는
완성된 조성을 방해하지 않지만, 누락된 비율을 보충하는 근거로 사용하지 않는다.
기존 소재 별칭의 범위와 중국어 소재 키 호환 정책은 이번 작업에서 전역 재정의하지 않았다.

다음은 실제 이미지에서 OCR 오류와 파싱 실패를 나누어 측정하는 단계다.
현재 수정 파일럿의 80/80이나 텍스트 테스트 통과를 OCR 정확도로 해석하면 안 된다.

## 2026-09-18 중국어 탄성섬유 계약 후속 검증

위의 수정 파일럿 80/80은 당시 v1.0.2의 `氨纶 → polyurethane` 계약에 따른 역사적
결과다. 프로젝트 공통 기준을 `氨纶 → spandex`로 확정하면서 생성기 v1.0.3과
`kdpp-fiber-labels-v2` manifest를 새 출력 폴더에 생성했다. v1.0.2 산출물은 그대로
보존하며 평가기는 v1과 v2를 모두 검증한다.

v1.0.3은 이미지 80장 해시를 유지하고 `SYN_SOURCE_0020` 네 행의 정답만 현재 키에
맞췄다. 전체 unittest 51개와 파서 단독 평가의 소재·비율 80/80, 대표 부위 80/80을
통과했다. 재평가 명령은 다음과 같다.

```powershell
python -B scripts/evaluate_synthetic_parser.py --manifest outputs/synthetic/synthetic_v1_pilot_corrected_v1_0_3/manifest.csv --output outputs/synthetic/synthetic_v1_pilot_corrected_v1_0_3/parser_report.json
```
