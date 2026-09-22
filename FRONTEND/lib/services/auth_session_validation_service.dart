import 'auth_api_service.dart';
import '../models/analysis_history_record.dart';

/// 저장된 세션 검증 결과를 유효·무효·확인 불가 상태로 구분한다.
sealed class AuthSessionValidationResult {
  const AuthSessionValidationResult();
}

/// 토큰이 유효하며 서버 사용자와 분석 이력을 사용할 수 있는 상태다.
class AuthSessionValid extends AuthSessionValidationResult {
  const AuthSessionValid(this.user, {this.history = const []});

  final AuthUser user;
  final List<AnalysisHistoryRecord> history;
}

/// 서버가 인증 거부를 반환해 다시 로그인해야 하는 상태다.
class AuthSessionInvalid extends AuthSessionValidationResult {
  const AuthSessionInvalid();
}

/// `unauthorized` 이외의 인증 API 오류로 현재 세션 유효성을 확정할 수 없는 상태다.
class AuthSessionUnavailable extends AuthSessionValidationResult {
  const AuthSessionUnavailable(this.exception);

  final AuthApiException exception;
}

/// 액세스 토큰으로 서버 세션과 초기 분석 이력을 확인한다.
class AuthSessionValidationService {
  AuthSessionValidationService({AuthApiService? authApiService})
    : authApiService = authApiService ?? AuthApiService();

  final AuthApiService authApiService;

  /// `unauthorized` 오류만 무효로 판정하고 나머지 인증 API 오류는 확인 불가로 보존한다.
  Future<AuthSessionValidationResult> validate({
    required String accessToken,
  }) async {
    try {
      final snapshot = await authApiService.fetchSessionSnapshot(
        accessToken: accessToken,
      );
      return AuthSessionValid(snapshot.user, history: snapshot.history);
    } on AuthApiException catch (error) {
      if (error.type == AuthApiErrorType.unauthorized) {
        return const AuthSessionInvalid();
      }

      return AuthSessionUnavailable(error);
    }
  }
}
