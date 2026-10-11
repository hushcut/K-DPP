# 실사진 정답지 두 건 정정 — 2026-09-28

기준 코드: `kyh/ai`의 `adddac4`. 이전 [실패 원인 감사](qa_failure_audit_20260923.md)에서 발견한 정답지 오류 2건을 사진의 대표 부위인 겉감 기준으로 정정했다. 파서·OCR 코드는 변경하지 않았다.

## 사진 확인과 정정값

| 사진 | 이전 정답 | 수정 정답 | 확인 근거 |
| --- | --- | --- | --- |
| QA001.jpg | 면 80%, 폴리에스터 20% | **면 98%, 폴리우레탄 2%** | 表布(겉감)의 綿 98%·ポリウレタン 2%. 별도 裏布(안감)의 폴리에스터 68%·나일론 17%·폴리우레탄 15%를 섞지 않음 |
| QA003.jpg | 폴리에스터 95%, 폴리우레탄 5% | **면 100%** | OUTSHELL 100% COTTON |

사진 원본을 직접 확인했으며 회전·확대는 메모리 미리보기에만 사용했다. 사진 파일은 변경하지 않았다. 두 사진의 SHA-256과 정정 전후 값은 [수정 기록 JSON](qa_answer_corrections_20260928.json)에 있다. 다른 PC에서 반영할 때에도 파일명뿐 아니라 사진 해시와 기존 정답을 대조한다.

## 변경·보존 범위

아래 경로는 모두 저장소 루트 기준이다.

- 실제 데이터셋 정답지 `QA_DATASET/real_qa_163/answer_key_legacy_partial.csv`의 두 행에서 `answer_materials`, `answer_ratios`만 수정했다.
- 수정 전 원본은 `.test-artifacts/qa-answer-corrections-20260928/source_answer_key.before.csv`에 바이트 그대로 백업했다.
- 과거 평가용 `.test-artifacts/vision-qa-20260923/real89_answer_key.csv`는 변경하지 않았다. 과거 결과 58/89를 그대로 재현할 수 있다.
- 과거 평가용 정답지의 촬영 조건 등 메타데이터를 유지하고 같은 두 정답만 바꾼 새 평가용 사본을 `.test-artifacts/qa-answer-corrections-20260928/real89_answer_key_corrected.csv`에 만들었다.
- 두 정답지 모두 89행이며 나머지 87행과 대상 행의 다른 필드는 동일하다. 원래 인코딩·인용·줄바꿈도 보존했다.
- 실제 사진·전체 정답지·OCR 캐시·출력 CSV는 기존 Git 제외 정책을 유지한다. 커밋에는 정정값·해시·근거 JSON과 감사 문서만 포함한다.

## 검증

- 수정한 두 정답지를 기존 `load_qa_answer_key`로 각각 읽어 89건 전체의 소재·비율 형식을 검증했다.
- 정답지 로딩·비교·오프라인 QA 관련 테스트 **14개 통과**. 런타임 코드 변경이 없어 전체 AI 테스트는 이번에 반복하지 않았다.
- 기존 파서 출력에 정답만 다시 대조한 독립 비교에서는 QA003만 실패→정답으로 바뀌고, 기대 정답 건수는 59/89다.
- 사진·캐시·과거 정답지·DB의 해시 보존과 실제 정답지 백업·변경 후 해시를 확인했다.
- 89건 오프라인 재실행: 정답 **59/89(66.3%)**, 파서 성공 **59건**, 인식 실패 **30건**, 정답지 대비 성공 불일치 **0/59건**.
- 캐시 hit/miss/write **135/0/0**, 외부 API 사용 이미지 **0**, 예외 **0**. 실패 코드는 `composition_not_found` 29건, `incomplete_part_composition` 1건이다.
- 직전 동일 코드의 재검증 결과와 89건 모두를 비교했다. 상태·오류 코드·소재·대표 부위·확신도·OCR 선택·경고·미리보기는 전부 동일하고, 정답 판정이 바뀐 것은 QA003뿐이다. 기존 정답 58건은 유지됐다.
- 실행 후에도 사진·캐시·과거 정답지·DB 해시가 동일하다.
- 결과: 루트 `.test-artifacts/qa-answer-corrections-20260928/results.csv`, `results.summary.json`.

## 재현

AI 폴더 `AI/kdpp_ai_ocr_integrated`에서 실행한다. 로컬 사진·캐시·수정 정답지 사본이 필요하다. 기존 결과를 덮어쓰지 않도록 새 출력 디렉터리를 사용한다.

```powershell
$env:KDPP_ENABLE_REFLECTION_OCR = "0"
.venv/Scripts/python.exe -m scripts.run_qa_batch --image-dir ../../QA_DATASET/real_qa_163/images --answer-key ../../.test-artifacts/qa-answer-corrections-20260928/real89_answer_key_corrected.csv --ocr-cache ../../.test-artifacts/vision-qa-20260923/new_vision_cache.json --offline --output ../../.test-artifacts/qa-answer-corrections-replay/results.csv
```

## 해석과 남은 작업

이번 변화는 정답지 정정으로 인한 평가 변화이며 OCR 인식률 향상이 아니다. QA001은 겉감 OCR 근거가 부족해 계속 인식 실패로 남는다. QA003은 파서가 이미 사진대로 읽었으므로 정답 판정만 바뀐다.

사진 89건 전체를 다시 주석 처리한 것은 아니다. 이 표본의 성공 불일치가 없어지더라도 실제 서비스 오답률 0%를 보장하지 않는다. 다음 작업은 기존 3번의 원인별 인식률 개선이며, 별칭·비율 선행 배치·다국어 반복 처리부터 검토한다.
