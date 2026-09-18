# 소재 라벨 파일럿 수정 검토

2026-09-13. 생성기 v1.0.2로 **기존과 동일한 20개 기본 조성 × 4개 변형 = 80장**의
수정본을 생성했다. 파서와 백엔드는 변경하지 않았다. 이번 결과는 데이터의 표시·정답
일관성 검사이며, 이미지 OCR 정확도나 실제 사진의 일반화 성능이 아니다.

## 중국어 표시·정답 계약

프로젝트는 `spandex`와 `polyurethane`을 별도 API/DB 키로 유지한다. 기존 파서는
`SPANDEX`·`ELASTANE`를 `spandex`, `POLYURETHANE`·`氨纶`을 `polyurethane`으로 반환한다.
백엔드도 두 키를 별도로 저장하므로 이번 파일럿을 위해 키를 전역 통합하지 않았다.

`kdpp-fiber-labels-v1` 계약은 생성기의 중국어 섬유 라벨에 한해 적용한다.

| 단계 | 예: 기존 원본 0020 |
|---|---|
| 생성 전 조성 (`source_parts_json`) | acrylic 60, spandex 40 |
| 표시·정답 조성 (`parts_json`) | acrylic 60, polyurethane 40 |
| 실제 문구 | `60% 腈纶`, `40% 氨纶` |
| 기대 API 결과 | acrylic 60, polyurethane 40 |

계약은 **이미지와 정답을 생성하기 전에** 적용한다. 파서 예측을 보고 정답을 바꾸거나,
평가 중에 두 키를 동의어로 합치지 않는다. 같은 부위의 두 키가 같은 중국어 표기로
겹치면 비율을 합산하며, 다른 부위는 독립적으로 유지한다. 영어·한국어·일본어에서는
두 키를 그대로 구분한다. manifest에는 원시 조성과 적용 계약 버전을 모두 기록한다.
평가기 역시 계약에 따른 원시 조성→표시 조성 관계를 확인하며, 불일치하면 평가 전에 거부한다.

이는 현재 K-DPP의 중국어 의류 라벨 API 호환 규칙이다. 중국 국가표준 플랫폼은
[`氨纶`을 elastane과 대응](https://std.samr.gov.cn/gb/search/gbDetailed?id=5DDA8B9DA7C018DEE05397BE0A0A95A7)시키며,
아크릴 표기는 중국 상무부 자료의
[`腈纶`](https://www.mofcom.gov.cn/zcfb/zgdwjjmywg/art/2016/art_e99d9c49cf81478f932ae1621d5496a5.html)을 사용한다.
모든 폴리우레탄 재료가 스판덱스라는 의미가 아니며, 이번 중국어 파일럿은 `氨纶`만 보고
두 내부 키를 구별하는 능력을 평가하지 않는다. 언어 전체의 의미 체계 통합은 별도 작업이다.

## 보존 및 변경 내역

- 원본: `outputs/synthetic/synthetic_v1_pilot` (v1.0.0).
- 수정본: `outputs/synthetic/synthetic_v1_pilot_corrected_v1_0_2`.
- 원본 이미지 80개와 manifest·설정·요약·미리보기까지 **84개 파일의 SHA-256을 유지**했다.
- 모든 행의 ID, source_group, 시드, 언어, 배치, 조건, 변형 값, 선택 부위, 원시 조성이 동일하다.
- `SYN_SOURCE_0004` 및 `SYN_SOURCE_0020`: 중국어 아크릴 오타 `腨纶 → 腈纶` 수정.
  따라서 문구·이미지가 바뀐 것은 **8장**이며 나머지 **72장 이미지 해시는 동일**하다.
- `SYN_SOURCE_0020`: 중국어 `氨纶`의 정답 키를 위 계약에 맞춰 `polyurethane`으로 기록한 **4행**.
  비율 40%는 유지했다.
- 수정본의 모든 이미지 파일을 열어 손상 여부와 해시를 검사했다. 80장 전체 배치와
  기본 문구 20종의 대표 이미지를 확인했고, 수정된 중국어 문구도 개별 이미지로 검수했다.
- 원시 조성, 표시 조성, 답안, 비율 합계 및 부위 선택의 관계를 80행 전체에서 확인했다.

원본 manifest SHA-256:
`eb5dffbbf1972cc42e478f729ee7814fe8e23a03c7cd1680fc7771cc6817ea42`

수정본 manifest SHA-256:
`1ed53cc3bd016687283087ebc2df2c6fc43954d28478d339a048dd894a5566d8`

## 같은 파서로 평가한 결과

| 지표 | 보존된 원본 | 수정본 |
|---|---:|---:|
| 소재·비율 일치 (이미지 행) | 72/80 (90%) | 80/80 (100%) |
| 소재·비율 일치 (독립 문구) | 18/20 | 20/20 |
| 대표 부위 일치 | 80/80 | 80/80 |
| 한국어 / 영어 / 일본어 | 각각 20/20 | 각각 20/20 |
| 중국어 | 12/20 | 20/20 |

`parse_label`과 `parse_materials` 결과가 위 소재·비율 지표에서 일치한다.
두 평가에 사용한 파서·별칭 파일의 해시는 같다. **90%→100%를 새 파서 성능 향상으로
보고하면 안 된다.** 입력 문구와 정답 계약을 바로잡은 수정 데이터에서의 일치 결과다.
같은 문구를 공유하는 네 이미지는 독립 텍스트 사례 네 개가 아니다.

## 재실행 및 검증

AI 프로젝트 루트에서 실행한다. 생성·이미지 검수에는 Pillow가 필요하며,
평가 CLI 자체는 Python 표준 라이브러리만 사용한다.

```powershell
python -B -m unittest discover -s tests -v
python -B scripts/generate_synthetic_labels.py
python -B scripts/evaluate_synthetic_parser.py --manifest outputs/synthetic/synthetic_v1_pilot/manifest.csv --output outputs/synthetic/pilot_correction_review/original.json
python -B scripts/evaluate_synthetic_parser.py --manifest outputs/synthetic/synthetic_v1_pilot_corrected_v1_0_2/manifest.csv --output outputs/synthetic/pilot_correction_review/corrected.json
```

생성기는 비어 있지 않은 폴더 덮어쓰기를 거부한다. 다시 생성하려면 `--output`으로
새 폴더를 지정한다. 동일 이미지 해시는 같은 코드·설정·폰트·Pillow 환경을 전제로 한다.
Python 3.12.14 / Pillow 12.3.0에서 unittest **29개**를 통과했다. 중국어 충돌 합산,
부위 독립성, 원시 조성 보존, 4개 언어의 고정 정답 계약, 실제 그리기 텍스트와 답안의
일치, 미지원 계약 거부, 평가 중 정답 재매핑 금지를 검증한다.

생성물과 상세 평가 JSON은 Git의 `outputs/` 제외 규칙을 따른다.
`pilot_correction_review/comparison.json`에는 행별 변경과 원본 보존 확인을 기록했고,
`source_review.jpg`는 문구 20종의 대표 이미지 모음이다.

## 현재 완료 범위와 다음 단계

완료: 생성 오타·정답 계약 정리, 수정본 80장 생성, 이미지 검수, 텍스트 파서 재평가.

아직 수행하지 않음: **사진→Google Vision OCR→파서** 평가, 실제 사진 성능 재측정.
다음은 수정본 또는 기존 실제 사진에서 OCR 인식 오류와 파싱 오류를 나눠 측정하는 작업이다.
사진 추가 수집이나 400장 확대는 필수가 아니다. 기존 163장을 개발에 활용했다면 회귀
자료로 사용하고, 최종 성능 확인에는 개발에 사용하지 않은 실제 사진을 별도로 사용한다.

## 후속 계약 정리 — 2026-09-18

통합 브랜치와의 소재 키 충돌을 없애기 위해 현재 계약을 다음과 같이 확정했다.

- `氨纶`·`氨綸`과 해당 탄성섬유 표기 → `spandex`
- `聚氨酯`·`聚氨脂` → `polyurethane`
- 생성기의 중국어 표기도 `氨纶`과 `聚氨酯`로 분리

위 본문의 v1.0.2 결과와 해시는 2026-09-13 당시의 역사적 검증 기록으로 보존한다.
새 기본 생성기는 v1.0.3, 정답 계약은 `kdpp-fiber-labels-v2`로 올렸다. 평가기는
기존 v1 manifest의 `spandex → polyurethane` 계약도 계속 검증하므로 과거 결과를
소급 변경하지 않는다.

동일한 시드로 v1.0.3 80장을 생성한 결과 이미지 해시는 v1.0.2와 80장 모두 같았다.
`SYN_SOURCE_0020` 네 행의 정답과 `parts_json`만 `polyurethane 40`에서
`spandex 40`으로 바뀌며, 모든 행에 v2 정책과 v1.0.3 버전이 기록된다. 새 manifest
SHA-256은 `3cd12efb452ccf494282c333b409b5cbbf15520c8e34336cf2f1585f372fb05d`이다.
파서 단독 평가는 소재·비율, 공개 파서 함수, 대표 부위가 모두 80/80이며 실패 원본은 없다.
