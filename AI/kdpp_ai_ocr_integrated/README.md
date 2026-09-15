# K-DPP AI OCR 통합 모듈

K-DPP의 OCR 소재 분석과 세탁기호 실험 기능을 모은 AI 모듈입니다.

## 팀 공통 규칙

- 개발 환경은 `.venv`와 `requirements-dev.txt`를 사용합니다.
- 코드 변경 후에는 Ruff와 pytest를 모두 통과해야 합니다.
- AI 폴더 변경의 push·PR에서는 GitHub Actions가 Ruff와 pytest를 실행합니다.
- 서비스 계정 JSON, 실제 데이터셋, 모델, OCR 캐시·출력물은 커밋하지 않습니다.
- `ruff check --fix`나 `ruff format`으로 기존 코드를 일괄 변경하지 않습니다. 검사
  결과를 검토해 필요한 변경만 적용합니다.
- 의존성 잠금 파일과 환경별 설치 정책은 별도 합의 후 도입합니다.

## 현재 서비스 범위

현재 DPP 서비스 흐름에서 사용하는 기능은 의류 라벨의 **소재명과 혼용률
추출**입니다.

```text
라벨 이미지 -> Google Vision OCR -> 소재/혼용률 파서 -> 소재 분석 결과
```

`apps/symbol/`의 ResNet18 세탁기호 분류기는 별도 실험 기능입니다. 이 모델은
전체 라벨에서 세탁기호 위치를 찾지 못하며, 이미 잘라낸 단일 세탁기호 이미지만
입력으로 받습니다. 따라서 현재 탄소배출량 계산 흐름에는 연결되어 있지 않습니다.

### OCR과 세탁기호 경로를 분리하는 이유

OCR 소재 분석은 전체 의류 라벨 이미지에서 텍스트를 읽고 혼용률을 구조화하는
서비스 경로입니다. 반면 세탁기호 분류는 잘라낸 기호 이미지와 별도 모델 가중치가
필요한 실험 경로입니다. 두 입력 조건과 배포 준비 수준이 다르므로, OCR 요청에서
세탁기호 모델을 미리 불러오거나 그 오류가 OCR을 막지 않도록 분리합니다.

## 폴더 구조

```text
kdpp_ai_ocr_integrated/
  apps/
    service/                 # FastAPI 서비스 경계와 응답 형식
    text/                    # 이미지 검증, OCR, 소재/혼용률 파싱, OCR QA 계약
    symbol/                  # 세탁기호 ResNet18 실험 코드
  scripts/
    audit_ocr_qa_dataset.py  # OCR QA 정답지 품질 감사
    audit_symbol_dataset.py  # 세탁기호 데이터셋 품질 감사
    check_split_leakage.py   # train/valid/test 누수 검사
    run_ai_checks.py         # 문법, 테스트, 데이터 검사 실행 도구
    run_combined_batch.py    # 이미지 폴더 일괄 분석 도구
    run_qa_batch.py          # OCR/파서 단위 QA 도구
  data/                      # 로컬 세탁기호 학습 데이터 위치, Git 추적 제외
  models/                    # 로컬 모델 가중치 위치, Git 추적 제외
  outputs/                   # QA·평가 결과와 OCR 캐시 위치, Git 추적 제외
```

## 설치와 로컬 검증

가상환경을 만든 뒤 의존성을 설치합니다. 자격증명 파일, 모델 가중치, 실제
데이터셋은 저장소에 포함하지 않습니다.

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m pytest -q
```

`GOOGLE_APPLICATION_CREDENTIALS` 또는 `--credentials`에 지정하는 Google Vision
서비스 계정 JSON은 개인 로컬 경로에서만 사용해야 하며, 저장소에 추가하면 안 됩니다.

## OCR 소재 분석

### 처리 방식

1. 업로드 이미지의 형식, 크기, 해상도를 먼저 검증합니다.
2. 원본 이미지를 Google Vision OCR로 읽습니다.
3. 파서 신뢰도가 낮을 때만 회전 보정·대비 보정·선명화한 전처리 후보를 추가로 OCR합니다.
4. 후보별 소재 구성, 혼용률 합계, 경고 수를 비교해 더 신뢰할 만한 결과를 선택합니다.
5. 파서는 소재명·혼용률·의류 부위·세탁 지침을 구조화된 응답으로 반환합니다.

원본 OCR 결과가 충분히 신뢰할 만하면 전처리 OCR을 생략합니다. 불필요한 외부 API
호출 비용과 지연을 줄이기 위한 정책입니다.

### 응답 예시

```json
{
  "api_version": "1.0",
  "status": "success",
  "materials": {
    "cotton": 80,
    "polyester": 20
  },
  "materials_korean": "면 80%, 폴리에스터 20%",
  "raw_ocr_preview": "COTTON 80% POLYESTER 20%",
  "confidence": {
    "ocr": "high",
    "parser": "high"
  },
  "selected_part": "outer",
  "parts": {
    "outer": {
      "cotton": 80,
      "polyester": 20
    }
  }
}
```

소재 구성을 신뢰할 수 없으면 임의의 100% 소재를 만들지 않고 `status: "failed"`와
오류 코드를 반환합니다. 프론트엔드는 이 경우 사용자 수동 입력 흐름을 제공해야 합니다.

## OCR QA 정답지 형식

`scripts/run_qa_batch.py`는 OCR과 소재 파서 자체를 측정한다. 백엔드
`/api/scan`까지 포함한 통합 QA는 저장소 루트의 `QA/run_qa_batch.py`를
사용한다. 두 도구는 정답 CSV의 핵심 열, 소재 별칭 표준화, 실패 코드를
공유하지만 기본 허용 오차가 각각 `±3%p`, `±5%p`이므로 점수를 합치거나
직접 비교하지 않는다.

파서 규칙이나 OCR 전처리의 회귀만 확인할 때는 `scripts/run_qa_batch.py`를
사용합니다. 실제 백엔드 요청 형식과 응답 계약까지 확인할 때는 저장소 루트의
`QA/run_qa_batch.py`를 사용합니다. 두 결과는 측정 범위가 달라 각각 기록합니다.

OCR QA 정답 CSV의 필수 열은 다음과 같습니다.

```text
file_name, answer_materials, answer_ratios
```

소재명에는 `cotton`, `polyester`, `spandex`, `polyurethane`처럼 표준 영문 키를
사용합니다. 아래 두 형식을 지원합니다.

```text
cotton;polyester       / 80;20
cotton:80;polyester:20
```

정확도에 포함하는 일반 라벨의 원문 혼용률 합계는 `100%`여야 합니다.
`0.01%p`보다 큰 합계 오차는 100%로 정규화하지 않고 실패 처리합니다. OCR이 일부
숫자를 잘못 읽은 결과를 확정 혼용률처럼 사용하지 않기 위한 정책입니다. 복합/부위별
표기인 라벨은 대표 소재 정답을 별도로 적거나 `include_in_accuracy=FALSE`로 제외합니다.

원인별 실패를 분석하려면 다음 열도 기록하는 것을 권장합니다.

```text
split, source_group, capture_condition, label_layout
```

- `split`: `train`, `valid`, `test` 중 하나입니다.
- `source_group`: 같은 원본 라벨 또는 그 파생 이미지에 공통으로 부여하는 그룹입니다.
- `capture_condition`: `indoor`, `night`, `reflection`, `blur`, `wrinkle` 등의 촬영 조건입니다.
- `label_layout`: `same_line`, `alternating_lines`, `stacked`, `multi_part` 등의 라벨 배치입니다.

규칙을 변경하기 전에는 정답지 형식과 누수를 먼저 점검합니다. 이 명령은 데이터를
읽기만 하며 Google Vision을 호출하지 않습니다.

```bash
python -m scripts.audit_ocr_qa_dataset ^
  --image-dir "C:\K-DPP-QA-DATASET\images" ^
  --answer-key "C:\K-DPP-QA-DATASET\answer_key.csv" ^
  --strict
```

OCR·파서 자체의 회귀 확인에는 다음 도구를 사용합니다.

```bash
python -m scripts.run_qa_batch ^
  --image-dir "C:\K-DPP-QA-DATASET\images" ^
  --answer-key "C:\K-DPP-QA-DATASET\answer_key.csv" ^
  --credentials "C:\secure\vision-key.json"
```

기본값은 정답 CSV의 `file_name`에 있는 이미지만 처리합니다. 폴더에 섞인
미정답 이미지를 함께 점검할 때만 `--include-unanswered`를 사용합니다.
동일한 `file_name`이 하위 폴더에 중복되면 어느 이미지를 평가할지 알 수 없으므로
실행을 중단합니다. 이때는 QA 실행 결과 폴더 전체가 아니라 정확한 `images` 폴더를
`--image-dir`에 지정합니다.
`--strict-coverage`는 이미지와 정답의 누락을 OCR 호출 전에 실패 처리하므로,
데이터셋 계약을 감사할 때 함께 사용합니다. OCR·파서에서 예상 밖 예외가 발생하면
결과 CSV와 요약 파일을 남긴 뒤 프로세스는 실패 종료합니다.

첫 실행에서 저장된 OCR 캐시를 사용하면, 파서 규칙만 변경했을 때 Google Vision을
다시 호출하지 않고 비교할 수 있습니다.

```bash
python -m scripts.run_qa_batch ^
  --image-dir "C:\K-DPP-QA-DATASET\images" ^
  --answer-key "C:\K-DPP-QA-DATASET\answer_key.csv" ^
  --offline ^
  --strict-coverage
```

`--refresh-ocr-cache`는 OCR 전처리·언어 힌트·좌표 기반 줄 재구성처럼 OCR 결과가
달라지는 변경 후 기존 캐시를 갱신할 때 사용합니다. 캐시는 OCR 파이프라인 버전을
기록하므로, 다른 버전의 캐시를 발견하면 기본 실행은 안전하게 중단하고 이 옵션으로
새 캐시를 만들도록 안내합니다. 여러 QA 실행이 같은 캐시를 갱신해도 파일 잠금과 병합
저장으로 먼저 저장된 항목을 덮어쓰지 않습니다.
`outputs/`의 OCR 캐시에는 라벨 텍스트가 포함될 수 있으므로 커밋하지 않습니다.

## 합성 소재 라벨 데이터

실사진 QA와 별도로, 재현 가능한 파서 회귀 입력을 만들기 위한 Pillow 기반 도구입니다.
기본 설정은 seed가 고정된 20개 원본 라벨과 각 4개 이미지 조건 변형(총 80장)을
생성합니다. 변형에는 언어·조명·흐림·반사뿐 아니라 소재/비율 순서, 세로 열 레이아웃,
배경 테마, JPEG 품질, 혼합 조건이 포함됩니다. manifest에는 정답 소재·비율,
`source_group`, 언어, 조건, 레이아웃, 테마, JPEG 품질, 변환 정보, 이미지 SHA-256을
저장하며 모든 행은 `include_in_accuracy=false`로 기록됩니다.

```bash
python -m scripts.generate_synthetic_labels
```

생성물은 `outputs/synthetic/`에 저장되고 Git에서 제외됩니다. 같은 seed·설정·폰트 환경에서는
동일한 이미지 해시가 재생성됩니다. 합성 데이터 점수는 실제 라벨 사진의 OCR 정확도와
별도로 기록해야 합니다.

기본 설정에는 한국어·일본어·중국어가 포함됩니다. Windows는 기본 CJK 폰트를 사용하며,
Ubuntu/Debian 환경에서는 생성 전에 `sudo apt-get install fonts-noto-cjk`를 실행합니다.
AI CI는 이 폰트를 설치한 뒤 네 언어 생성 테스트를 실행합니다. 다른 운영체제에서는
Noto CJK 또는 시스템 CJK 폰트를 설치해야 합니다.

합성 manifest의 `original_text`를 파서에 직접 넣어 회귀를 측정하려면 다음 명령을 사용합니다.
이 평가는 Google Vision이나 이미지 OCR을 호출하지 않으며, 결과를 실사진 QA 정확도로
해석하면 안 됩니다.

```bash
python -m scripts.evaluate_synthetic_labels
```

`image_results.csv`에는 이미지 행별 파서 결과를, `source_group_results.csv`에는 같은 원본의
모든 변형이 통과했는지의 그룹 점수를 저장합니다. `summary.json`의
`evaluation_type`은 항상 `synthetic_parser_only`입니다.

## 세탁기호 ResNet18 실험

### 데이터 계약

로컬 데이터셋은 아래 형태로 둡니다.

```text
data/
  train/
  valid/
  test/
```

각 split에는 `_classes.csv`와 CSV가 참조하는 이미지 파일이 있어야 합니다.
`_classes.csv`는 `filename` 열 뒤에 0 또는 1 값의 클래스 열을 같은 순서로 가져야 합니다.
모든 클래스 값이 0인 행도 정상적인 음성 샘플이므로 삭제하지 않습니다.

새 데이터셋은 원본 이미지와 증강·중복 이미지를 같은 split에 유지하는 그룹 기반 분할을
권장합니다. 권장 시작 비율은 train 70%, valid 15%, test 15%이며, 실제 데이터 구조에
따라 달라질 수 있습니다.

학습 전에는 다음 감사를 실행합니다.

```bash
python -m scripts.audit_symbol_dataset --data-dir data
```

이 도구는 split별 수량·비율, 클래스별 양성 샘플, 음성 샘플, 멀티라벨 행,
원본명·SHA-256 기준 누수를 확인합니다. 학습도 양성 샘플이 없는 선언 클래스가 있으면
중단합니다.

### 학습과 평가

```bash
python -m apps.symbol.train_symbol_experiment
python -m apps.symbol.evaluate_symbol ^
  --model models/symbol/best_symbol_model_exp.pt ^
  --split valid
```

검증 지표는 전체 클래스 macro-F1, 관측 클래스 macro-F1, micro-F1, exact match를
함께 확인합니다. 전체 클래스 macro-F1은 검증 데이터에 한 번도 나오지 않은 클래스가
좋은 점수에 가려지는 것을 막고, 관측 클래스 macro-F1은 실제 등장한 클래스에서의
분류 품질을 따로 읽게 합니다. 희귀 클래스가 있는 멀티라벨 데이터에서는 Hamming
accuracy만으로 모델을 선택하지 않습니다.

현재 기본 체크포인트 경로는 `models/symbol/best_symbol_model_exp.pt` 하나입니다.
실험별 체크포인트·설정·지표를 별도 폴더로 보존하는 버저닝과 다중 백본 비교는 아직
완료되지 않았습니다.

## 현재 확인되지 않은 사항

저장소에는 실제 `data/` 폴더와 모델 가중치가 포함되어 있지 않습니다. 따라서 아래
정보는 현재 코드만으로 확인할 수 없습니다.

- 데이터 출처와 라이선스
- 총 이미지 수와 클래스별 분포
- 실제 train/valid/test 분할 결과와 누수 검사 결과
- 증강 방식과 라벨링·검수 기준
- ResNet18 및 다른 백본의 실제 성능 비교 결과

이 정보는 실제 데이터셋 경로가 준비된 뒤 감사 결과와 함께 데이터 카드로 작성합니다.

## 알려진 한계와 다음 작업

- 세탁기호 모델은 전체 라벨에서 기호 위치를 검출하지 않습니다.
- 현재 DPP 사용자 흐름은 소재 OCR 분석만 사용합니다.
- AI 단위 QA와 서버 `/api/scan` 통합 QA는 목적과 허용오차가 달라, 결과를 하나의
  정확도 수치로 직접 비교하면 안 됩니다. 다음 단계에서 기준을 문서화하고 정리합니다.
