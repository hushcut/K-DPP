import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/models/analysis_history_record.dart';
import 'package:k_dpp/services/auth_api_service.dart';
import 'package:k_dpp/services/auth_session_validation_service.dart';

void main() {
  test('returns valid with the latest backend user profile', () async {
    final service = AuthSessionValidationService(
      authApiService: _FakeAuthApiService(
        user: const AuthUser(
          id: 7,
          email: 'honggildong@example.com',
          nickname: '홍길동',
        ),
        history: const [
          AnalysisHistoryRecord(
            id: 13,
            materials: {'cotton': 100},
            carbonFootprint: 1.46,
          ),
        ],
      ),
    );

    final result = await service.validate(accessToken: 'valid-token');

    expect(result, isA<AuthSessionValid>());
    final valid = result as AuthSessionValid;
    expect(valid.user.nickname, '홍길동');
    expect(valid.user.email, 'honggildong@example.com');
    expect(valid.history.single.id, 13);
  });

  test('returns invalid when the backend rejects the token', () async {
    final service = AuthSessionValidationService(
      authApiService: _FakeAuthApiService(
        error: const AuthApiException(
          type: AuthApiErrorType.unauthorized,
          message: '로그인이 필요합니다.',
          statusCode: 401,
        ),
      ),
    );

    final result = await service.validate(accessToken: 'revoked-token');

    expect(result, isA<AuthSessionInvalid>());
  });

  test(
    'keeps offline use available when the backend cannot be reached',
    () async {
      final service = AuthSessionValidationService(
        authApiService: _FakeAuthApiService(
          error: const AuthApiException(
            type: AuthApiErrorType.network,
            message: 'connection failed',
          ),
        ),
      );

      final result = await service.validate(accessToken: 'stored-token');

      expect(result, isA<AuthSessionUnavailable>());
      final unavailable = result as AuthSessionUnavailable;
      expect(unavailable.exception.type, AuthApiErrorType.network);
    },
  );
}

class _FakeAuthApiService extends AuthApiService {
  _FakeAuthApiService({this.user, this.history = const [], this.error});

  final AuthUser? user;
  final List<AnalysisHistoryRecord> history;
  final AuthApiException? error;

  @override
  Future<AuthSessionSnapshot> fetchSessionSnapshot({
    required String accessToken,
  }) async {
    if (error != null) throw error!;
    return AuthSessionSnapshot(user: user!, history: history);
  }
}
