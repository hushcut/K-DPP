import 'auth_session_storage_service.dart';

class AuthSessionService {
  const AuthSessionService({this.storage});

  final AuthSessionStorage? storage;

  AuthSessionStorage get _storage => storage ?? AuthSessionStorageService();

  Future<void> saveAccessToken(String token) async {
    await _storage.saveSession(
      AuthSession(
        accessToken: token,
        expiresAt: DateTime.now().add(const Duration(days: 30)),
      ),
    );
  }

  Future<String?> readAccessToken() async {
    final session = await _storage.loadSession();
    if (session == null || session.isExpired) {
      if (session != null) {
        await _storage.clearSession();
      }
      return null;
    }
    return session.accessToken;
  }

  Future<void> clear() async {
    await _storage.clearSession();
  }
}
