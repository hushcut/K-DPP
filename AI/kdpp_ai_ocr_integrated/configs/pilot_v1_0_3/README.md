# 사용자 합성 라벨 파일럿 v1.0.3 보존

이 설정은 사용자 pilot 브랜치의 20개 원본 × 4개 변형 생성 구성을 보존합니다.
팀원 `apps/synthetic/label_generator.py`와 별도로
`apps/synthetic/pilot_v1_0_3.py`를 사용하며, 중국어 소재 기준은
`pilot_material_policy_v2.py`에서 스판덱스(氨纶)와 폴리우레탄(聚氨酯)을 구분합니다.
두 생성기는 공유 운영 소재 파서로 검증합니다.

AI 프로젝트 루트에서 실행합니다.

```powershell
python scripts/generate_pilot_v1_0_3.py
python scripts/evaluate_pilot_parser_v1_0_3.py --manifest outputs/synthetic/pilot_v1_0_3/manifest.csv --output outputs/synthetic/pilot_v1_0_3/parser_report.json
```

출력은 `outputs/synthetic/pilot_v1_0_3`로 분리합니다. 생성기는 비어 있지 않은
출력 폴더를 덮어쓰지 않습니다. 이미 보존한 기존 80장과 원본 manifest는 그대로 유지하고,
파일 해시가 고정된 동일 자료로 통합 전후를 비교합니다. 폰트와 Pillow 환경이 달라지면
같은 seed라도 이미지 바이트가 달라질 수 있습니다.

문구 평가기는 이미지를 읽거나 OCR을 호출하지 않습니다. 80행은 원본 문구 20개의
반복이므로 행 단위와 원본 그룹 단위 수치를 함께 기록합니다. 생성 manifest의
`include_in_accuracy=false`, `split=unassigned`는 실사진 최종 평가와 섞이지 않게 하는
표시입니다. 실제 OCR 평가에는 원본을 보존한 별도 파생 정답표가 필요합니다.
기존 이미지나 외부 평가 CSV를 이 설정 폴더에 복사하거나 커밋하지 않습니다.
