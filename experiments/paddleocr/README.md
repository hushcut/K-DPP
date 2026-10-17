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
