import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/utils/session_expiry_handler.dart';
import 'package:provider/provider.dart';

import 'helpers/fake_auth_session_storage.dart';
import 'helpers/fake_closet_storage.dart';

void main() {
  testWidgets('clears the session and moves to login with a message', (
    tester,
  ) async {
    final provider = ClosetProvider(
      storage: FakeClosetStorage(),
      authSessionStorage: FakeAuthSessionStorage(),
    );
    await provider.setAuthenticatedUser(
      nickname: '홍길동',
      email: 'honggildong@example.com',
      accessToken: 'expired-token',
      expiresInSeconds: 3600,
    );

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          initialRoute: '/main',
          routes: {
            '/main': (context) => Scaffold(
              body: Center(
                child: ElevatedButton(
                  onPressed: () {
                    SessionExpiryHandler.handle(context);
                  },
                  child: const Text('만료 처리'),
                ),
              ),
            ),
            '/login': (context) =>
                const Scaffold(body: Center(child: Text('로그인 화면'))),
          },
        ),
      ),
    );

    await tester.tap(find.text('만료 처리'));
    await tester.pumpAndSettle();

    expect(find.text('로그인 화면'), findsOneWidget);
    expect(find.text(SessionExpiryHandler.defaultMessage), findsOneWidget);
    expect(provider.isAuthenticated, isFalse);
    expect(provider.accessToken, isNull);
  });
}
