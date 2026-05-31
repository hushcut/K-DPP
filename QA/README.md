# K-DPP QA 대량 테스트 도구

이 폴더는 의류 라벨 사진 데이터셋을 백엔드 `/api/scan`에 자동으로 보내고, AI 인식 결과를 정답표와 비교하기 위한 QA 도구이다.

## 목적

앱에서 사진을 하나씩 넣는 대신, 사진 폴더와 정답표를 기준으로 여러 장의 라벨 이미지를 한 번에 테스트한다.

```text
images 폴더
+ answer_key.csv
+ run_qa_batch.py
→ qa_result.csv 생성
```

앱 화면 흐름 검증은 대표 사진 10~20장만 직접 앱에서 테스트하고, AI 정확도 측정은 이 배치 테스트로 진행한다.

## 폴더 예시

```text
QA_DATASET/
  images/
    QA001.jpg
    QA002.jpg
    QA003.jpg
  answer_key.csv
  results/
```

## 정답표 양식

`answer_key_template.csv`를 복사해서 `answer_key.csv`로 사용한다.

중요 컬럼:

```text
id
file_name
answer_materials
answer_ratios
shooting_pose
lighting
resolution
label_language
label_condition
notation_type
```

소재와 비율은 세미콜론(`;`)으로 구분한다.

예시:

```csv
QA001,QA001.jpg,cotton;polyester,80;20,손에 들고,자연광,고해상도,한글,정상,% 있음
QA002,QA002.jpg,cotton,100,바닥에 두고,실내 조명,중간 해상도,한글,그림자,% 있음
```

## 백엔드 실행

배치 테스트 전에 백엔드 서버를 먼저 켠다.

```powershell
cd C:\DEV\K-DPP-merge-work\BACKEND
C:\DEV\K-DPP\BACKEND\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

브라우저에서 아래 주소가 열리면 준비 완료이다.

```text
http://127.0.0.1:8000/docs
```

## 실행 방법

Windows 예시:

```powershell
cd C:\DEV\K-DPP-merge-work
python QA\run_qa_batch.py --answers C:\DEV\K-DPP-QA-DATASET\answer_key.csv --images C:\DEV\K-DPP-QA-DATASET\images --output C:\DEV\K-DPP-QA-DATASET\results\qa_result.csv
```

`python` 명령이 인식되지 않으면 아래 중 하나를 사용한다.

```powershell
py QA\run_qa_batch.py --answers C:\DEV\K-DPP-QA-DATASET\answer_key.csv --images C:\DEV\K-DPP-QA-DATASET\images --output C:\DEV\K-DPP-QA-DATASET\results\qa_result.csv
```

또는 백엔드 가상환경 Python을 직접 사용한다.

```powershell
C:\DEV\K-DPP\BACKEND\.venv\Scripts\python.exe QA\run_qa_batch.py --answers C:\DEV\K-DPP-QA-DATASET\answer_key.csv --images C:\DEV\K-DPP-QA-DATASET\images --output C:\DEV\K-DPP-QA-DATASET\results\qa_result.csv
```

백엔드 주소를 바꿔야 할 때:

```powershell
python QA\run_qa_batch.py --api-url http://127.0.0.1:8000/api/scan --answers C:\DEV\K-DPP-QA-DATASET\answer_key.csv --images C:\DEV\K-DPP-QA-DATASET\images --output C:\DEV\K-DPP-QA-DATASET\results\qa_result.csv
```

## 결과 판정 기준

기본 허용 오차는 `±5%p`이다.

```text
완전 성공: 소재명과 혼용률이 허용 오차 내에서 모두 일치
부분 성공: 소재명은 모두 맞지만 일부 비율이 허용 오차를 벗어남
소재 성공/비율 실패: 소재명은 맞지만 비율이 크게 다름
소재 실패: 소재 누락 또는 잘못된 소재 인식
서버/API 실패: 백엔드 요청 실패 또는 오류 응답
```

허용 오차를 바꾸려면:

```powershell
python QA\run_qa_batch.py --tolerance 3 --answers ... --images ... --output ...
```

## QA팀 사용 방식

```text
QA 1: 사진 파일명과 촬영 조건 정리
QA 2: 정답표 작성
QA 3: 배치 테스트 실행 및 실패 사례 정리
```

결과 CSV는 Excel 또는 Google Sheets로 열어 실패 사례를 필터링하면 된다.
