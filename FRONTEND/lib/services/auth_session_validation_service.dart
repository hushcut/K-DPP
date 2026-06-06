import 'auth_api_service.dart';
import '../models/analysis_history_record.dart';

sealed class AuthSessionValidationResult {
  const AuthSessionValidationResult();
}

class AuthSessionValid extends AuthSessionValidationResult {
  const AuthSessionValid(this.user, {this.history = const []});

  final AuthUser user;
  final List<AnalysisHistoryRecord> history;
}

class AuthSessionInvalid extends AuthSessionValidationResult {
  const AuthSessionInvalid();
}

class AuthSessionUnavailable extends AuthSessionValidationResult {
  const AuthSessionUnavailable(this.exception);

  final AuthApiException exception;
}

class AuthSessionValidationService {
  const AuthSessionValidationService({
    this.authApiService = const AuthApiService(),
  });

  final AuthApiService authApiService;

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
