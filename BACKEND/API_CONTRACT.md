# K-DPP v1 API Contract

이 문서는 프론트엔드와 AI/OCR 파트가 백엔드 탄소배출량 계산 기능을 호출할 때 맞춰야 하는 최소 규격입니다.

## v1 목표

AI/OCR 또는 프론트엔드가 의류 라벨에서 추출한 소재 혼용률을 백엔드에 전달하면, 백엔드는 SQLite `materials` 테이블의 소재별 탄소배출계수를 기준으로 예상 탄소배출량을 계산해 반환합니다.

## Local Base URL

백엔드 서버:

```text
http://127.0.0.1:8000
```

Android Emulator에서 Flutter가 호출할 때:

```text
http://10.0.2.2:8000
```

## Official v1 Endpoint

```http
POST /analyze
```

### Request

```json
{
  "materials": {
    "cotton": 80,
    "polyester": 20
  },
  "raw_ocr_text": "COTTON 80% POLYESTER 20%"
}
```

`raw_ocr_text`는 선택값입니다. AI/OCR 원문을 저장하고 싶을 때만 보내면 됩니다.

### Required Rules

- `materials`는 필수입니다.
- 소재명은 `materials` 테이블의 `name_ko`, `name_en`, `aliases` 중 하나와 매칭되어야 합니다.
- 소재 비율은 0 이상이어야 합니다.
- 전체 혼용률 합계는 OCR 오차를 고려해 `99.5 ~ 100.5` 범위까지 허용합니다.

### Success Response

```json
{
  "status": "success",
  "message": "분석 완료",
  "materials": {
    "cotton": 80,
    "polyester": 20
  },
  "carbon_footprint": 8.54,
  "unit": "kg CO2eq",
  "care_instruction": "30도 이하 물에서 중성세제로 손세탁하세요.",
  "saved_result_id": 13
}
```

## Supporting Endpoints

```http
GET /materials
```

현재 DB에 등록된 소재별 탄소배출량 기준표를 반환합니다.

```http
GET /history
```

분석 결과 저장 기록을 최신순으로 반환합니다.

## Error Response

오류 응답은 아래 형식으로 통일합니다.

```json
{
  "status": "error",
  "message": "DB에 등록되지 않은 소재가 있습니다.",
  "detail": {
    "message": "DB에 등록되지 않은 소재가 있습니다.",
    "unknown_materials": ["acrylic"]
  }
}
```

## Flutter Call Example

```dart
final response = await http.post(
  Uri.parse('http://10.0.2.2:8000/analyze'),
  headers: {'Content-Type': 'application/json'},
  body: jsonEncode({
    'materials': {
      'cotton': 80,
      'polyester': 20,
    },
    'raw_ocr_text': 'COTTON 80% POLYESTER 20%',
  }),
);
```
