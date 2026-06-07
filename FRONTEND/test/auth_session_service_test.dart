import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/services/auth_session_service.dart';
import 'helpers/fake_auth_session_storage.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('access token can be saved and read', () async {
    final storage = FakeAuthSessionStorage();
    final service = AuthSessionService(storage: storage);

    await service.saveAccessToken('test-token');

    expect(await service.readAccessToken(), 'test-token');
  });

  test('clear removes saved access token', () async {
    final storage = FakeAuthSessionStorage();
    final service = AuthSessionService(storage: storage);

    await service.saveAccessToken('test-token');
    await service.clear();

    expect(await service.readAccessToken(), isNull);
  });
}
