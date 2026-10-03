import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/services/auth_api_service.dart';
import 'package:k_dpp/services/carbon_api_service.dart';

void main() {
  test('탄소 API 403은 권한 없음으로 분류되어 세션 만료 처리에서 제외되고, 임시 추정값 저장만 알린다', () {
    final exception = CarbonApiException.fromStatusCode(
      statusCode: 403,
      responseBody: '{"message":"접근 권한이 없습니다."}',
    );

    expect(exception.type, CarbonApiErrorType.forbidden);
    expect(exception.type, isNot(CarbonApiErrorType.unauthorized));
    // DECISIONS 98: 원인마다 다르던 긴 문장을 한 문장으로 줄였다.
    expect(exception.userMessage, '탄소량은 임시 추정값으로 저장했어요.');
  });

  group('탄소 계산 실패 알림 문구(DECISIONS 98)', () {
    CarbonApiException badRequest(List<String> unknownMaterials) {
      return CarbonApiException(
        type: CarbonApiErrorType.badRequest,
        message: '',
        unknownMaterials: unknownMaterials,
      );
    }

    test('기준 없는 소재는 첫 소재와 남은 개수만 보인다', () {
      expect(
        badRequest(const ['텐셀']).userMessage,
        '텐셀 소재는 기준이 없어 임시 추정값으로 저장했어요.',
      );
      expect(
        badRequest(const ['텐셀', '모달', '큐프라']).userMessage,
        '텐셀 외 2개 소재는 기준이 없어 임시 추정값으로 저장했어요.',
      );
    });

    test('인터넷 끊김과 로그인 만료만 따로 알리고, 나머지 원인은 한 문장이다', () {
      String messageFor(CarbonApiErrorType type) =>
          CarbonApiException(type: type, message: '').userMessage;

      expect(
        messageFor(CarbonApiErrorType.network),
        '인터넷에 연결할 수 없어 임시 추정값으로 저장했어요.',
      );
      expect(
        messageFor(CarbonApiErrorType.unauthorized),
        '로그인이 만료됐어요. 탄소량은 임시 추정값으로 저장했어요.',
      );
      for (final type in [
        CarbonApiErrorType.badRequest,
        CarbonApiErrorType.forbidden,
        CarbonApiErrorType.server,
        CarbonApiErrorType.timeout,
        CarbonApiErrorType.invalidResponse,
        CarbonApiErrorType.unknown,
      ]) {
        expect(messageFor(type), '탄소량은 임시 추정값으로 저장했어요.', reason: '$type');
      }
    });
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
