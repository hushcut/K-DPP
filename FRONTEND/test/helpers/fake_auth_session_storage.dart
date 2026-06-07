import 'package:k_dpp/services/auth_session_storage_service.dart';

class FakeAuthSessionStorage implements AuthSessionStorage {
  AuthSession? savedSession;
  Object? saveError;
  Object? loadError;
  Object? clearError;

  @override
  Future<void> saveSession(AuthSession session) async {
    if (saveError case final error?) {
      throw error;
    }

    savedSession = session;
  }

  @override
  Future<AuthSession?> loadSession() async {
    if (loadError case final error?) {
      throw error;
    }

    return savedSession;
  }

  @override
  Future<void> clearSession() async {
    if (clearError case final error?) {
      throw error;
    }

    savedSession = null;
  }
}
