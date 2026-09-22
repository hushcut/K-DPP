import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/services/auth_session_storage_service.dart';

void main() {
  group('AuthSessionStorageService', () {
    test('saves and loads a session from secure storage', () async {
      final secureStorage = _FakeSecureStorage();
      final legacyStorage = _FakeLegacyStorage();
      final service = AuthSessionStorageService(
        secureStorage: secureStorage,
        legacyStorage: legacyStorage,
      );
      final session = AuthSession(
        accessToken: 'secure-token',
        expiresAt: DateTime(2026, 7, 1),
      );

      await service.saveSession(session);
      final restored = await service.loadSession();

      expect(restored?.accessToken, 'secure-token');
      expect(restored?.expiresAt, DateTime(2026, 7, 1));
      expect(legacyStorage.clearCount, 1);
    });

    test('migrates a legacy session and clears the old values', () async {
      final secureStorage = _FakeSecureStorage();
      final legacyStorage = _FakeLegacyStorage(
        session: AuthSession(
          accessToken: 'legacy-token',
          expiresAt: DateTime(2026, 7, 2),
        ),
      );
      final service = AuthSessionStorageService(
        secureStorage: secureStorage,
        legacyStorage: legacyStorage,
      );

      final restored = await service.loadSession();

      expect(restored?.accessToken, 'legacy-token');
      expect(legacyStorage.session, isNull);
      expect(secureStorage.values.values, contains('legacy-token'));
    });

    test(
      'clears partial secure values before checking legacy storage',
      () async {
        final secureStorage = _FakeSecureStorage()
          ..values['secure_auth_access_token'] = 'partial-token';
        final legacyStorage = _FakeLegacyStorage();
        final service = AuthSessionStorageService(
          secureStorage: secureStorage,
          legacyStorage: legacyStorage,
        );

        final restored = await service.loadSession();

        expect(restored, isNull);
        expect(secureStorage.values, isEmpty);
      },
    );

    test('clears secure and legacy sessions together', () async {
      final secureStorage = _FakeSecureStorage()
        ..values['secure_auth_access_token'] = 'secure-token'
        ..values['secure_auth_expires_at'] = '123';
      final legacyStorage = _FakeLegacyStorage(
        session: AuthSession(
          accessToken: 'legacy-token',
          expiresAt: DateTime(2026, 7, 2),
        ),
      );
      final service = AuthSessionStorageService(
        secureStorage: secureStorage,
        legacyStorage: legacyStorage,
      );

      await service.clearSession();

      expect(secureStorage.values, isEmpty);
      expect(legacyStorage.session, isNull);
    });
  });
}

class _FakeSecureStorage implements SecureAuthKeyValueStorage {
  final Map<String, String> values = {};

  @override
  Future<void> delete({required String key}) async {
    values.remove(key);
  }

  @override
  Future<String?> read({required String key}) async {
    return values[key];
  }

  @override
  Future<void> write({required String key, required String value}) async {
    values[key] = value;
  }
}

class _FakeLegacyStorage implements LegacyAuthSessionStorage {
  _FakeLegacyStorage({this.session});

  AuthSession? session;
  int clearCount = 0;

  @override
  Future<void> clearSession() async {
    clearCount++;
    session = null;
  }

  @override
  Future<AuthSession?> loadSession() async {
    return session;
  }
}
