import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/services/scan_api_service.dart';

void main() {
  test('HTTP 502는 OCR 실패로 분류해 직접 입력 안내를 제공한다', () {
    final exception = ScanApiException.fromStatusCode(
      statusCode: 502,
      responseBody: '{"message":"AI OCR 처리에 실패했습니다."}',
    );

    expect(exception.type, ScanApiErrorType.ocrFailed);
    expect(exception.statusCode, 502);
    expect(exception.userMessage, contains('직접 입력해 주세요'));
    expect(exception.userMessage, contains('자동으로 인식하지 못했어요'));
  });

  test('HTTP 503은 일반 서버 오류로 유지한다', () {
    final exception = ScanApiException.fromStatusCode(
      statusCode: 503,
      responseBody: '{"message":"AI OCR 모듈을 불러오지 못했습니다."}',
    );

    expect(exception.type, ScanApiErrorType.server);
    expect(exception.userMessage, contains('일시적인 문제'));
  });
  test('HTTP 403은 세션 만료가 아닌 권한 없음으로 분류한다', () {
    final exception = ScanApiException.fromStatusCode(
      statusCode: 403,
      responseBody: '{"message":"접근 권한이 없습니다."}',
    );

    // 401(재로그인)과 달리 세션을 지우지 않아야 하므로 타입이 분리되어야 합니다.
    expect(exception.type, ScanApiErrorType.forbidden);
    expect(exception.type, isNot(ScanApiErrorType.unauthorized));
    expect(exception.userMessage, contains('권한'));
  });

  test('HTTP 401은 여전히 재로그인 안내로 분류한다', () {
    final exception = ScanApiException.fromStatusCode(
      statusCode: 401,
      responseBody: '{"message":"로그인이 필요합니다."}',
    );

    expect(exception.type, ScanApiErrorType.unauthorized);
    expect(exception.userMessage, contains('다시 로그인'));
  });
}
