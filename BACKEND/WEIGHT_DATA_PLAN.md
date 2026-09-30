# 의류 무게 자료 현황 및 수집 계획

작성일: 2026-09-11. main.py의 CLOTHING_TYPE_OPTIONS를 읽어 확인했다. 전 항목은 근거 미확보 개발용 값이며 문헌값 또는 실측 평균이 아니다.

| ID | 대표 g | 하한 g | 상한 g |
| --- | ---: | ---: | ---: |
| short_sleeve_tshirt | 180 | 100 | 250 |
| shirt_blouse | 240 | 150 | 350 |
| long_sleeve_sweatshirt | 520 | 350 | 750 |
| knit | 620 | 400 | 900 |
| pants | 680 | 450 | 900 |
| skirt | 420 | 250 | 650 |
| dress | 560 | 350 | 850 |
| outer | 1200 | 800 | 1800 |

## 수집 방법

첫 수집은 단순 라벨의 반팔·셔츠·바지부터 품목당 20~30벌을 목표로 하는 예비 조사다. 표본 크기는 대표성을 보장하는 기준이 아니다. 동일한 건조 조건·저울로 주머니를 비우고 옷걸이를 제거한 뒤 총무게를 측정한다. 분리하지 않은 부자재는 포함 사실을 기록한다. 동일 의류의 재측정은 독립 표본으로 세지 않는다.

기록 필드: sample_id, clothing_type_id, size, season, materials, label_scope, has_lining, has_filling, accessory_note, weight_grams, scale_resolution_grams, measured_at, label_photo_reference, measurement_note.

라벨 사진은 동의받은 자료로 수집하고 사람·주소 등 불필요한 정보는 포함하지 않는다. 원자료에서 누락과 중복을 점검하고 품목별 표본 수·중앙값·최소·최대를 우선 보고한다. 소수 표본의 최소·최대를 전체 의류의 범위로 일반화하지 않는다. 평가용 의류는 카탈로그 산출에 사용하지 않고 무게 절대오차(g)를 별도 평가한다.

## 백엔드 전달 사항

카탈로그 버전과 evidence_type=placeholder를 우선 명시할 수 있도록 설계한다. 실제 자료 확보 후 derived로 변경하고 산출 근거를 기록한다. 대표값을 사용하는 새 계산 버전은 기존 범위 중간값 계산과 값이 달라질 수 있으므로 기존 이력을 보존한다. 물리적 측정 자료는 아직 수집하지 않았다.
