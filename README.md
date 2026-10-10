# K-DPP

의류 라벨에서 소재·혼용률을 분석하고, 소재별 탄소배출량을 계산·기록하는 프로젝트입니다.

## 현재 기능

- AI: Google Vision OCR과 규칙 기반 파서로 소재·혼용률·세탁 지침을 추출합니다.
- 백엔드: `/api/scan`에서 소재를 분석하고 `/api/carbon/calculate`에서 탄소배출량 계산과 이력 저장을 처리합니다.
- 프론트엔드: Flutter 앱에서 스캔·수동 입력·탄소 계산 흐름을 제공합니다.
- 세탁기호 분류: 잘라낸 단일 기호 이미지를 대상으로 하는 별도 실험 기능입니다.

## 영역별 안내

| 영역 | 문서 |
| --- | --- |
| AI 설치·실행·응답 계약·OCR QA | [AI README](AI/kdpp_ai_ocr_integrated/README.md) |
| 백엔드 설치·실행 | [백엔드 README](BACKEND/README.md) |
| 백엔드 요청·응답·인증 | [백엔드 API 계약](BACKEND/API_CONTRACT.md) |
| Flutter 앱 실행 | [프론트엔드 README](FRONTEND/README.md) |
| 백엔드 통합 배치 검사 | [QA README](QA/README.md) |
| 기존 스캔 계약과 develop 차이 | [스캔 API 계약](docs/SCAN_API_CONTRACT.md) |
| 준원·AI 담당 연동 협의 | [연동 협의안](docs/AI_DEVELOP_INTEGRATION_PLAN.md) |
| IN·승우 실사진 비교 | [검증 보고서](AI/kdpp_ai_ocr_integrated/reports/qa_real_photo_comparison_20261009.md) |

AI 기본 HTTP 주소는 `http://127.0.0.1:8100`, 백엔드는 `http://127.0.0.1:8000`입니다.
두 서비스의 경로와 업로드 필드는 다르므로 해당 영역의 문서를 따릅니다.

## 평가 범위

OCR·파서 단위 QA, 백엔드 통합 QA, 합성 원문 파서 평가를 각각 기록합니다.
저장 OCR 캐시를 재사용한 결과와 합성 데이터 점수는 새로운 실사진 OCR 정확도를 의미하지 않습니다.
실제 데이터셋·모델·자격증명·DB·OCR 캐시와 결과물은 로컬에서 관리하며 커밋하지 않습니다.

2026-10-09 기존 원본 사진 50장을 두 AI 버전으로 각각 새 Vision 호출하여 검사했습니다.
평가 대상 48장의 소재·혼용률 완전일치는 IN 41/48(85.42%), 승우 ai-integration 30/48(62.50%)입니다.
독립 새사진·앱·최신 develop 연동 검증은 별도이며, 자세한 조건과 한계는 위 검증 보고서를 따릅니다.

프론트엔드·백엔드 통합 기준은 담당자의 `develop`입니다. 이 브랜치에 남아 있는 기존
프론트·백엔드가 최신 develop과 같다는 뜻은 아닙니다. 필요한 연동 수정은 담당 브랜치에서
검증한 뒤 가져옵니다.

## 자동 검사

[AI 검사](.github/workflows/ai-checks.yml)와 [프론트·백엔드 검사](.github/workflows/ci.yml)를
push·PR에서 실행합니다. 실제 통과 여부는 해당 커밋의 Actions 결과로 확인합니다.
