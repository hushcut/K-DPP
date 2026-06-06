import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/services/auth_api_service.dart';
import 'package:k_dpp/services/auth_session_storage_service.dart';
import 'package:k_dpp/services/auth_session_validation_service.dart';
import 'package:k_dpp/splash_screen.dart';
import 'package:provider/provider.dart';

import 'helpers/fake_auth_session_storage.dart';
import 'helpers/fake_closet_storage.dart';

void main() {
  testWidgets('인증 저장소 오류가 발생하면 로그인 화면으로 안전하게 이동한다', (tester) async {
    final authStorage = FakeAuthSessionStorage()
      ..loadError = StateError('secure storage unavailable');
    final provider = ClosetProvider(
      storage: FakeClosetStorage(),
      authSessionStorage: authStorage,
    );

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          initialRoute: '/splash',
          routes: {
            '/splash': (context) =>
                const SplashScreen(minimumDisplayDuration: Duration.zero),
            '/login': (context) => const Scaffold(body: Text('로그인 화면')),
            '/main': (context) => const Scaffold(body: Text('메인 화면')),
          },
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('로그인 화면'), findsOneWidget);
    expect(find.text('메인 화면'), findsNothing);
  });

  testWidgets('유효한 저장 세션은 서버 검증 후 메인 화면으로 이동한다', (tester) async {
    final authStorage = FakeAuthSessionStorage()
      ..savedSession = AuthSession(
        accessToken: 'valid-token',
        expiresAt: DateTime.now().add(const Duration(hours: 1)),
      );
    final provider = ClosetProvider(
      storage: FakeClosetStorage(),
      authSessionStorage: authStorage,
    );

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          initialRoute: '/splash',
          routes: {
            '/splash': (context) => SplashScreen(
              minimumDisplayDuration: Duration.zero,
              authSessionValidationService: _FakeValidationService(
                const AuthSessionValid(
                  AuthUser(
                    id: 1,
                    email: 'honggildong@example.com',
                    nickname: '홍길동',
                  ),
                ),
              ),
            ),
            '/login': (context) => const Scaffold(body: Text('로그인 화면')),
            '/main': (context) => const Scaffold(body: Text('메인 화면')),
          },
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('메인 화면'), findsOneWidget);
    expect(find.text('로그인 화면'), findsNothing);
    expect(provider.userName, '홍길동');
    expect(provider.userEmail, 'honggildong@example.com');
  });
}

class _FakeValidationService extends AuthSessionValidationService {
  const _FakeValidationService(this.result);

  final AuthSessionValidationResult result;

  @override
  Future<AuthSessionValidationResult> validate({
    required String accessToken,
  }) async {
    return result;
  }
}
