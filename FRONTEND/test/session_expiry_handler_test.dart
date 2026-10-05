import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/utils/session_expiry_handler.dart';
import 'package:k_dpp/widgets/app_banner.dart';
import 'package:provider/provider.dart';

import 'helpers/app_banner_expect.dart';
import 'helpers/fake_auth_session_storage.dart';
import 'helpers/fake_closet_storage.dart';

void main() {
  testWidgets('clears the session and moves to login with a message', (
    tester,
  ) async {
    final provider = await _signedInProvider();
    await _pumpExpiryButton(tester, provider);

    await tester.tap(find.text('만료 처리'));
    await tester.pumpAndSettle();

    expect(find.text('로그인 화면'), findsOneWidget);
    expectAppBanner(
      tester,
      SessionExpiryHandler.defaultMessage,
      AppBannerKind.info,
    );
    expect(provider.isAuthenticated, isFalse);
    expect(provider.accessToken, isNull);
  });

  // DECISIONS 98: 괄호로 덧붙이던 정리 실패를 짧은 둘째 문장으로 알린다.
  group('저장된 로그인 정보를 다 지우지 못하면 실패로 알린다', () {
    testWidgets("'다시 로그인해 주세요.' 로 끝나면 그 자리에 정리 실패를 쓴다", (tester) async {
      final storage = FakeAuthSessionStorage();
      final provider = await _signedInProvider(storage: storage);
      storage.clearError = Exception('저장소 잠김');
      await _pumpExpiryButton(tester, provider);

      await tester.tap(find.text('만료 처리'));
      await tester.pumpAndSettle();

      expect(find.text('로그인 화면'), findsOneWidget);
      expectAppBanner(
        tester,
        '로그인이 만료됐어요. 일부 로그인 정보는 지우지 못했어요.',
        AppBannerKind.failure,
      );
    });

    testWidgets('다른 안내로 끝나면 그 안내를 남기고 뒤에 붙인다', (tester) async {
      final storage = FakeAuthSessionStorage();
      final provider = await _signedInProvider(storage: storage);
      storage.clearError = Exception('저장소 잠김');
      await _pumpExpiryButton(
        tester,
        provider,
        message: '로그인이 만료됐어요. 의류는 기기에 저장했어요.',
      );

      await tester.tap(find.text('만료 처리'));
      await tester.pumpAndSettle();

      expectAppBanner(
        tester,
        '로그인이 만료됐어요. 의류는 기기에 저장했어요. 일부 로그인 정보는 지우지 못했어요.',
        AppBannerKind.failure,
      );
    });
  });
}

Future<ClosetProvider> _signedInProvider({
  FakeAuthSessionStorage? storage,
}) async {
  final provider = ClosetProvider(
    storage: FakeClosetStorage(),
    authSessionStorage: storage ?? FakeAuthSessionStorage(),
  );
  await provider.setAuthenticatedUser(
    nickname: '홍길동',
    email: 'honggildong@example.com',
    accessToken: 'expired-token',
    expiresInSeconds: 3600,
  );
  return provider;
}

Future<void> _pumpExpiryButton(
  WidgetTester tester,
  ClosetProvider provider, {
  String? message,
}) {
  return tester.pumpWidget(
    ChangeNotifierProvider.value(
      value: provider,
      child: MaterialApp(
        builder: AppBannerHost.builder,
        initialRoute: '/main',
        routes: {
          '/main': (context) => Scaffold(
            body: Center(
              child: ElevatedButton(
                onPressed: () {
                  if (message == null) {
                    SessionExpiryHandler.handle(context);
                  } else {
                    SessionExpiryHandler.handle(context, message: message);
                  }
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
}
