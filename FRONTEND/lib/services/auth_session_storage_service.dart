import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 액세스 토큰과 만료 시각으로 구성된 로컬 로그인 세션이다.
class AuthSession {
  const AuthSession({required this.accessToken, required this.expiresAt});

  final String accessToken;
  final DateTime expiresAt;

  bool get isExpired => !expiresAt.isAfter(DateTime.now());
}

/// 인증 세션의 저장·조회·삭제 동작을 추상화한다.
abstract class AuthSessionStorage {
  Future<void> saveSession(AuthSession session);
  Future<AuthSession?> loadSession();
  Future<void> clearSession();
}

/// 보안 저장소 구현을 교체하거나 테스트 대역으로 주입하기 위한 키-값 인터페이스다.
abstract class SecureAuthKeyValueStorage {
  Future<void> write({required String key, required String value});
  Future<String?> read({required String key});
  Future<void> delete({required String key});
}

/// `flutter_secure_storage`를 사용해 토큰 정보를 플랫폼 보안 저장소에 보관한다.
class FlutterSecureAuthKeyValueStorage implements SecureAuthKeyValueStorage {
  FlutterSecureAuthKeyValueStorage({FlutterSecureStorage? storage})
    : _storage =
          storage ?? const FlutterSecureStorage(aOptions: AndroidOptions());

  final FlutterSecureStorage _storage;

  @override
  Future<void> write({required String key, required String value}) {
    return _storage.write(key: key, value: value);
  }

  @override
  Future<String?> read({required String key}) {
    return _storage.read(key: key);
  }

  @override
  Future<void> delete({required String key}) {
    return _storage.delete(key: key);
  }
}

/// 이전 SharedPreferences 기반 세션을 읽고 제거하기 위한 마이그레이션 인터페이스다.
abstract class LegacyAuthSessionStorage {
  Future<AuthSession?> loadSession();
  Future<void> clearSession();
}

/// 구버전 키에 저장된 세션을 읽어 새 보안 저장 방식으로 옮길 수 있게 한다.
class SharedPreferencesLegacyAuthSessionStorage
    implements LegacyAuthSessionStorage {
  static const String accessTokenKey = 'auth_access_token';
  static const String expiresAtKey = 'auth_expires_at';

  SharedPreferencesLegacyAuthSessionStorage({
    SharedPreferencesAsync? preferences,
  }) : _preferences = preferences;

  SharedPreferencesAsync? _preferences;

  SharedPreferencesAsync get _prefs =>
      _preferences ??= SharedPreferencesAsync();

  @override
  Future<AuthSession?> loadSession() async {
    final values = await Future.wait([
      _prefs.getString(accessTokenKey),
      _prefs.getInt(expiresAtKey),
    ]);

    return _parseSession(
      accessToken: values[0] as String?,
      expiresAtValue: values[1]?.toString(),
    );
  }

  @override
  Future<void> clearSession() async {
    await Future.wait([
      _prefs.remove(accessTokenKey),
      _prefs.remove(expiresAtKey),
    ]);
  }
}

/// 세션을 보안 저장소에 저장하고 기존 SharedPreferences 세션을 자동 이전한다.
class AuthSessionStorageService implements AuthSessionStorage {
  static const String _secureAccessTokenKey = 'secure_auth_access_token';
  static const String _secureExpiresAtKey = 'secure_auth_expires_at';

  AuthSessionStorageService({
    SecureAuthKeyValueStorage? secureStorage,
    LegacyAuthSessionStorage? legacyStorage,
  }) : _secureStorage = secureStorage ?? FlutterSecureAuthKeyValueStorage(),
       _legacyStorage =
           legacyStorage ?? SharedPreferencesLegacyAuthSessionStorage();

  final SecureAuthKeyValueStorage _secureStorage;
  final LegacyAuthSessionStorage _legacyStorage;

  /// 토큰과 만료 시각을 함께 기록한 후 남아 있는 구버전 세션을 제거한다.
  @override
  Future<void> saveSession(AuthSession session) async {
    await Future.wait([
      _secureStorage.write(
        key: _secureAccessTokenKey,
        value: session.accessToken,
      ),
      _secureStorage.write(
        key: _secureExpiresAtKey,
        value: session.expiresAt.millisecondsSinceEpoch.toString(),
      ),
    ]);
    await _legacyStorage.clearSession();
  }

  /// 보안 세션을 우선 읽고, 없으면 구버전 세션을 읽어 즉시 보안 저장소로 이전한다.
  @override
  Future<AuthSession?> loadSession() async {
    final secureSession = await _loadSecureSession();

    if (secureSession != null) {
      return secureSession;
    }

    final legacySession = await _legacyStorage.loadSession();

    if (legacySession == null) {
      return null;
    }

    await saveSession(legacySession);
    return legacySession;
  }

  /// 로그아웃 시 새 저장소와 구버전 저장소의 인증 정보를 모두 삭제한다.
  @override
  Future<void> clearSession() async {
    await Future.wait([_clearSecureSession(), _legacyStorage.clearSession()]);
  }

  Future<AuthSession?> _loadSecureSession() async {
    final values = await Future.wait([
      _secureStorage.read(key: _secureAccessTokenKey),
      _secureStorage.read(key: _secureExpiresAtKey),
    ]);
    final session = _parseSession(
      accessToken: values[0],
      expiresAtValue: values[1],
    );

    if (session == null && (values[0] != null || values[1] != null)) {
      await _clearSecureSession();
    }

    return session;
  }

  Future<void> _clearSecureSession() async {
    await Future.wait([
      _secureStorage.delete(key: _secureAccessTokenKey),
      _secureStorage.delete(key: _secureExpiresAtKey),
    ]);
  }
}

AuthSession? _parseSession({
  required String? accessToken,
  required String? expiresAtValue,
}) {
  final normalizedToken = accessToken?.trim() ?? '';
  final expiresAtMilliseconds = int.tryParse(expiresAtValue ?? '');

  if (normalizedToken.isEmpty || expiresAtMilliseconds == null) {
    return null;
  }

  return AuthSession(
    accessToken: normalizedToken,
    expiresAt: DateTime.fromMillisecondsSinceEpoch(expiresAtMilliseconds),
  );
}
