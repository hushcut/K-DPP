import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/services/scan_api_service.dart';

void main() {
  test('HTTP 502는 OCR 실패로 분류해 재촬영 안내를 제공한다', () {
    final exception = ScanApiException.fromStatusCode(
      statusCode: 502,
      responseBody: '{"message":"AI OCR 처리에 실패했습니다."}',
    );

    expect(exception.type, ScanApiErrorType.ocrFailed);
    expect(exception.statusCode, 502);
    expect(exception.userMessage, contains('라벨 글자를 읽지 못했어요'));
    expect(exception.userMessage, contains('다시 촬영'));
  });

  test('HTTP 503은 일반 서버 오류로 유지한다', () {
    final exception = ScanApiException.fromStatusCode(
      statusCode: 503,
      responseBody: '{"message":"AI OCR 모듈을 불러오지 못했습니다."}',
    );

    expect(exception.type, ScanApiErrorType.server);
    expect(exception.userMessage, contains('일시적인 문제'));
  });
}
