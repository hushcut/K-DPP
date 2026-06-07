import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AuthSession {
  const AuthSession({required this.accessToken, required this.expiresAt});

  final String accessToken;
  final DateTime expiresAt;

  bool get isExpired => !expiresAt.isAfter(DateTime.now());
}

abstract class AuthSessionStorage {
  Future<void> saveSession(AuthSession session);
  Future<AuthSession?> loadSession();
  Future<void> clearSession();
}

abstract class SecureAuthKeyValueStorage {
  Future<void> write({required String key, required String value});
  Future<String?> read({required String key});
  Future<void> delete({required String key});
}

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

abstract class LegacyAuthSessionStorage {
  Future<AuthSession?> loadSession();
  Future<void> clearSession();
}

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
