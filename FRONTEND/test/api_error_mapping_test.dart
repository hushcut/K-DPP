import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/services/auth_api_service.dart';
import 'package:k_dpp/services/carbon_api_service.dart';

void main() {
  test('탄소 API 403은 권한 없음으로 분류되어 세션 만료 처리에서 제외된다', () {
    final exception = CarbonApiException.fromStatusCode(
      statusCode: 403,
      responseBody: '{"message":"접근 권한이 없습니다."}',
    );

    expect(exception.type, CarbonApiErrorType.forbidden);
    expect(exception.type, isNot(CarbonApiErrorType.unauthorized));
    expect(exception.userMessage, contains('권한'));
  });

  test('인증 API 403은 권한 없음 안내를 제공한다', () {
    final exception = AuthApiException.fromStatusCode(
      statusCode: 403,
      responseBody: '{"message":"접근 권한이 없습니다."}',
    );

    expect(exception.type, AuthApiErrorType.forbidden);
    expect(exception.userMessage, contains('권한'));
  });

  test('로그인 잠금 429는 서버의 대기 안내를 그대로 보여준다', () {
    final exception = AuthApiException.fromStatusCode(
      statusCode: 429,
      responseBody:
          '{"message":"로그인 시도가 너무 많습니다. 60초 후 다시 시도해 주세요."}',
    );

    expect(exception.userMessage, contains('60초'));
  });
}
