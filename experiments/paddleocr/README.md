# PaddleOCR 1단계 학습 스모크 테스트 (2026-10-17, 로컬 PC)

> 저장소 보관용 사본: 실험 원본 폴더는 김승우 PC의 `바탕화면\실사진 데이터셋\paddleocr_실험`(실행 경로 `C:\kdpp_ocr_exp`)이다.
> 여기에는 스크립트·학습 설정·README·버전 기록만 있고, 사진·잘린 줄 이미지·라벨 파일·모델·학습 산출물은 올리지 않았다.
> 설정 파일의 `C:/kdpp_ocr_exp/...` 경로는 그 PC 기준이다. 서비스 OCR은 계속 Google Vision이며 이 실험은 별도 방향이다.


목적: 우리 사진 → 짧은 학습 → 저장 → 추론 모델로 내보내기 → 새 실행에서 다시 불러와 글자 읽기, 이 흐름이 이 PC에서 돌아가는지 확인.
정확도 향상은 목표가 아니다. 서비스 OCR(Google Vision) 경로와 K-DPP 코드는 건드리지 않았다.

## 결과 요약

| 단계 | 결과 |
|---|---|
| 별도 환경 | `venv/` (Python 3.11.9, paddlepaddle 3.0.0 CPU, paddleocr 3.1.1, paddlex 3.1.4) |
| 데이터 | 사진 01~05에서 줄 48개 자름 → 라벨 40개 확정 (학습 34, 검증 6), 8개 제외 |
| 학습 | 6 epoch, 30 step, CPU 약 10분, 오류 없음. 손실 97.8 → 10.6 |
| 가중치 변화 | 968개 파라미터 중 967개 값이 바뀜 |
| 내보내기 | `output/smoke_rec_infer/` (inference.json / .pdiparams / .yml) |
| 새 실행에서 다시 읽기 | 성공. 결과 `results/reload_read.json` |

정확히 일치한 줄 수 (같은 사진이라 성능 평가가 아님): 기본 모델 학습 17/34·검증 4/6, 학습 후 학습 13/34·검증 3/6.
아주 짧게, 적은 데이터로 학습해서 줄 끝에 `.`, `니` 같은 군더더기가 붙는 등 오히려 나빠진 부분이 있다. 흐름 확인용 결과로만 본다.

## 이 사진들은 이후 테스트에서 빼야 함

사진 **01, 02, 03, 04, 05** (학습에 사용). 같은 의류·라벨의 다른 사진도 같은 분할에 둘 것.

## 라벨

- `data/labels_reviewed.json`: 줄별 라벨, 확인 상태(ok/unsure), 학습/검증 구분, 제외 이유
- `unsure` 6개(01_03, 01_05, 01_06, 01_07, 01_09, 01_12)는 글자가 잘리거나 흐림 → 사람 확인 필요
- 라벨은 사진에 적힌 그대로 (예: `POLY 100%`는 POLY 그대로)
- `data/draft_labels.json`: 기본 모델이 처음 읽은 초안 (참고용)

## 알게 된 점 / 주의

1. **한글 경로 문제**: Paddle 내부(C++)가 `C:\Users\김승우\...` 같은 한글 경로의 모델 파일을 못 연다.
   그래서 `C:\kdpp_ocr_exp` 라는 영문 연결(junction, 바로가기 같은 것)을 만들어 그 경로로 실행했다. 실제 파일은 이 폴더에만 있다.
   지우려면 `cmd /c rmdir C:\kdpp_ocr_exp` (연결만 지워지고 이 폴더 내용은 남음).
2. **한국어 모델 사전에 한자가 없음**: `氨纶` 같은 중국어 글자는 korean_PP-OCRv5 문자 목록에 없어서 이 모델로는 학습할 수 없다.
   중국어 표기를 다루려면 사전을 바꾸거나 다른(다국어/중국어) 모델을 써야 한다. 이번에는 해당 줄(03_05)을 제외했다.
3. **패키지 버전**: paddleocr 3.0.3은 korean_PP-OCRv5를 모르고, 그냥 설치하면 함께 깔리는 paddlex 3.7.2는 paddleocr 3.0.3과 충돌했다.
   paddleocr 3.1.1 + paddlex 3.1.4 조합으로 해결.
4. **Windows 검증 버그**: PaddleOCR 학습 코드는 Windows에서 검증 마지막 묶음을 건너뛴다. 검증 6줄이 한 묶음이라 학습 중 검증값(acc 0)은 의미 없다.
   대신 `03_reload_and_read.py`로 직접 비교했다. 다음에는 Eval batch_size를 1로 둘 것.
5. 학습 코드는 PaddleOCR `release/3.0`, 한국어 v5 설정·사전은 `main` 브랜치 파일 (모델 구조 부분은 동일함을 확인).

## 다시 실행하는 법 (PowerShell)

```
cd C:\kdpp_ocr_exp
$env:PYTHONIOENCODING="utf-8"
.\venv\Scripts\python.exe scripts\01_make_crops.py 01 02 03 04 05   # 줄 자르기 + 초안 라벨
.\venv\Scripts\python.exe scripts\02_build_dataset.py              # 확인한 라벨로 학습/검증 목록
cd PaddleOCR
..\venv\Scripts\python.exe tools\train.py -c C:\kdpp_ocr_exp\configs\smoke_korean_PP-OCRv5_mobile_rec.yml
..\venv\Scripts\python.exe tools\export_model.py -c C:\kdpp_ocr_exp\configs\smoke_korean_PP-OCRv5_mobile_rec.yml -o Global.pretrained_model=C:/kdpp_ocr_exp/output/smoke_rec/latest Global.save_inference_dir=C:/kdpp_ocr_exp/output/smoke_rec_infer
cd ..
.\venv\Scripts\python.exe scripts\03_reload_and_read.py            # 새 실행에서 불러와 읽기
```

## 폴더

- `scripts/` 실행 코드, `configs/` 학습 설정, `data/` 잘린 줄·라벨, `logs/` 학습·내보내기 로그
- `output/smoke_rec/` 학습 체크포인트, `output/smoke_rec_infer/` 내보낸 추론 모델, `results/` 비교 결과
- `downloads/` 공식 사전학습 가중치·설정·사전, `models/base/` 기존 추론 모델 압축 해제본, `PaddleOCR/` 공식 학습 코드
- `versions.txt`, `versions_pip_freeze.txt` 버전 기록

---

# 2단계: 학습 전 기준 측정 + 줄 라벨 만들기 (2026-10-17, 로컬 PC)

목적: 학습하기 전 기본 모델이 우리 사진의 글자 줄을 얼마나 읽는지 기록하고, 학습용 줄 이미지·정답을 만든다.
서비스 OCR(Google Vision)과 K-DPP 코드는 건드리지 않았다. 사진 01~05(1단계 학습용)는 제외했다.

## 대상과 실행

- 사진 208장: 실사진 06~50(45장) + 1학기 QA001~QA163(163장)
- 모델: PP-OCRv5_server_det(검출) + korean_PP-OCRv5_mobile_rec(인식), 학습 안 한 기본 모델
- 설정: 긴 변 1600px로 축소, enable_mkldnn=False, 줄 방향 보정 없음, 12×24px보다 작은 조각 제외
- CPU 시간: 사진당 약 28초(총 5,849초), 검출 3,347줄 → 잘라낸 줄 3,328개

## 라벨 (사진에 적힌 글자 그대로, POLY는 POLY)

기본 모델 읽기를 초안으로 두고, 208장 전부 잘라낸 줄을 눈으로 보고 고쳤다.

| 상태 | 줄 수 | 뜻 |
|---|---|---|
| ok | 2,080 | 확정 |
| unsure(확인 필요) | 694 | 흐림·잘림·겹침. 최선의 읽기를 적어 둠. 사람 확인 필요 |
| exclude | 554 | 세탁기호, 로고, 뒷면 비침 반전 글자, 판독 불가, 아랍어 등 |

## 학습 전 기준 (줄 단위, 검출된 줄만 분모)

| 범위 | 줄 수 | 글자 그대로 일치 | 띄어쓰기 무시 일치 | 글자 오류율(CER) |
|---|---|---|---|---|
| 확정 줄 전체 | 2,080 | 50.7% | 63.4% | 17.9% |
| └ 실사진 06~50 | 506 | 55.3% | 63.4% | 18.0% |
| └ 1학기 QA | 1,574 | 49.2% | 63.4% | 17.9% |
| 검증 묶음 확정 줄 | 408 | 52.0% | 61.3% | 20.1% |
| 확정+확인필요 | 2,774 | 41.7% | 51.9% | 23.4% |

- 검출 자체를 놓친 글자는 분모에 없다. 소재·혼용률 판정 정확도가 아니라 줄 글자 인식 기준이다.
- 확정 줄 중 199줄은 일본어·중국어 등 한국어 모델 사전에 없는 글자가 들어 있어, 이 모델로는 원래 맞힐 수 없다.

## 옷 단위 학습/검증 나누기

- 같은 옷의 다른 사진은 한 묶음: 검토 중 판단(`#same` 줄) + 알려 준 겹침(QA125=20·26, QA038·QA129=38, QA136=24·29, QA122=25, QA127=21)
- 다른 옷이라도 라벨 문구가 거의 같은 경우(같은 브랜드 양식)도 한 묶음으로 보수적으로 묶음 (`13_make_split.py`의 TEMPLATE)
- 109묶음 중 18묶음을 검증으로(seed 20261017): 사진 학습 172장 / 검증 36장
- 학습 목록(한국어 사전 안 글자만): 학습 1,516줄, 검증 365줄 → `train_list.txt`, `val_list.txt`
- 사전 밖 글자 포함 목록: 1,672 / 408줄 → `*_list_all_chars.txt` (다국어 모델용)
- 사진이 거꾸로 찍힌 줄 47개는 학습용으로 바로 세운 사본 사용(`crops_upright/`)
- 남은 한계: 무신사 주소처럼 여러 브랜드가 함께 쓰는 짧은 문구 몇 줄은 학습·검증 양쪽에 있을 수 있다.

## 1학기 정답표와 다르게 보인 사진 (`data/stage2/answer_key_flags.tsv`)

정답표는 팀원이 눈으로 작성한 것이라 틀릴 수 있다. 사진과 다르게 보인 곳만 표시했고 정답표는 고치지 않았다.
QA003(98 vs 사진 100%), QA041(cotton50 nylon50 vs COTTON만 보임), QA077(검출 실패로 확인 못함), QA119(겉감2 누락),
QA127(사진 파일이 상하 거울상으로 저장됨), QA139(PU 15 vs 사진 PU14+제전사1). 정답표의 `arylic` 오타도 그대로 있음.

## 다시 실행하는 법

```
cd C:\kdpp_ocr_exp
$env:PYTHONIOENCODING="utf-8"
.\venv\Scripts\python.exe scripts\10_stage2_baseline_run.py     # 기본 모델 실행(끝난 사진은 건너뜀, 이어하기 가능)
.\venv\Scripts\python.exe scripts\11_make_review_sheets.py     # 검토용 그림
.\venv\Scripts\python.exe scripts\12_labels_and_baseline.py    # 라벨 합치기 + 기준 성능
.\venv\Scripts\python.exe scripts\13_make_split.py             # 옷 단위 나누기 + 학습 목록
.\venv\Scripts\python.exe scripts\14_unsure_page.py            # 확인 필요 줄 HTML
```
라벨을 고치려면 `data/stage2/labels_corrections.tsv` 끝에 `줄ID<TAB>상태<TAB>글자<TAB>메모`를 덧붙이고 12→13을 다시 돌린다(뒤에 적은 줄이 우선). 사진이 거꾸로 찍힌 줄의 회전 정보(메모 `rot180`)는 메모를 바꿔 적어도 유지되고, 풀려면 메모를 `rot0`으로 시작한다.

## 2단계 파일

- `data/stage2/photos/` 사진별 검출 좌표·초안·점수·시간, `crops/` 잘라낸 줄, `review/` 검토용 그림
- `data/stage2/labels_corrections.tsv` 검토 기록, `labels_stage2.json` 줄별 최종 라벨
- `data/stage2/garment_groups.json` 묶음·분할, `unsure_list.tsv` / `unsure_review.html` 확인 필요 줄
- `results/stage2_baseline.json` 기준 성능, `logs/stage2_baseline.log` 실행 기록

---

# 5단계: 첫 본 학습 (2026-10-24 14:52 ~ 10-25 03:27, 로컬 PC CPU)

- 설정 `configs/stage5_korean_PP-OCRv5_mobile_rec.yml`: 스모크 설정에서 epoch 10, 매 epoch 저장, 270 step마다 검증, 목록 `data/stage2/train_list.txt`(1,516줄)·`val_list.txt`(365줄), 검증 batch 1만 바꿈. 학습률 1e-4(Cosine, warmup 1), 공식 한국어 사전학습 가중치, 최대 글자 수 25(25자 이상 줄은 학습에서 빠짐: 학습 61줄, 검증 23줄).
- 소요: 약 12시간 35분, 초당 약 0.3~0.38줄, 오류 없음. 로그 `logs/stage5_train.log`.
- 학습 중 검증(폭 320 고정) acc: 학습 전 0.632 → epoch 1 0.464 → 2 0.657 → … → **7 0.799(최고)** → 9 0.755. 7 epoch 모델을 `output/stage5_rec_infer_best`로 내보냄.
- 같은 잘린 이미지·같은 읽기 방식 비교(`scripts/15_stage5_compare.py`, `results/stage5_compare.json`): 검증 365줄 정확 일치 **57.5% → 75.9%**, 띄어쓰기 무시 69.9% → 79.2%, CER **11.2% → 3.9%**. 소재 관련 90줄 65.6% → 80.0%.
- 새로 틀린 18줄 중 일부는 정답 라벨 쪽이 의심스럽다(`12_005` 결감/겉감, `47_020` 1OO%/100% 등). 사람 확인 전이다.
- 범위: 검증 사진은 옷 단위로 나뉜 개발용 사진이다. 줄 글자 인식 기준이며 소재·혼용률 판정 정확도가 아니다. 최종 판단은 새 사진으로 한다.

```
cd C:\kdpp_ocr_exp\PaddleOCR
..\venv\Scripts\python.exe tools\train.py -c C:\kdpp_ocr_exp\configs\stage5_korean_PP-OCRv5_mobile_rec.yml
..\venv\Scripts\python.exe tools\export_model.py -c C:\kdpp_ocr_exp\configs\stage5_korean_PP-OCRv5_mobile_rec.yml -o Global.pretrained_model=C:/kdpp_ocr_exp/output/stage5_rec/best_accuracy Global.save_inference_dir=C:/kdpp_ocr_exp/output/stage5_rec_infer_best
cd ..
.\venv\Scripts\python.exe scripts\15_stage5_compare.py
```
