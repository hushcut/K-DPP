import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/services/auth_session_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const service = AuthSessionService();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('access token can be saved and read', () async {
    await service.saveAccessToken('test-token');

    expect(await service.readAccessToken(), 'test-token');
  });

  test('clear removes saved access token', () async {
    await service.saveAccessToken('test-token');
    await service.clear();

    expect(await service.readAccessToken(), isNull);
  });
}
