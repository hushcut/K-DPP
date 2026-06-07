import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/services/scan_api_service.dart';

void main() {
  test('maps HTTP 502 to an OCR-specific user message', () {
    final exception = ScanApiException.fromStatusCode(
      statusCode: 502,
      responseBody: '{"message":"AI OCR 처리에 실패했습니다."}',
    );

    expect(exception.type, ScanApiErrorType.ocrFailed);
    expect(exception.statusCode, 502);
    expect(exception.userMessage, contains('라벨 글자를 읽지 못했어요'));
    expect(exception.userMessage, contains('다시 촬영'));
  });

  test('keeps HTTP 503 as a server error', () {
    final exception = ScanApiException.fromStatusCode(
      statusCode: 503,
      responseBody: '{"message":"AI OCR 모듈을 불러오지 못했습니다."}',
    );

    expect(exception.type, ScanApiErrorType.server);
    expect(exception.userMessage, contains('서버에서 문제가 발생했어요'));
  });
}
