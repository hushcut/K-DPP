import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/email_login_screen.dart';
import 'package:k_dpp/services/auth_api_service.dart';
import 'package:k_dpp/widgets/app_banner.dart';
import 'package:provider/provider.dart';

import 'helpers/app_back_button_state.dart';
import 'helpers/fake_auth_backend.dart';
import 'helpers/fake_auth_session_storage.dart';
import 'helpers/fake_closet_storage.dart';

void main() {
  // C25(DECISIONS 2026-10-14): 요청 중에 이 화면을 떠나면 서버가 준 로그인을 받을 화면이 없어져,
  // 인증은 저장됐는데 로그인 첫 화면에 남았다.
  testWidgets('로그인을 기다리는 동안은 "<"·뒤로가기·아래 링크로 떠날 수 없고, 끝나면 메인으로 간다', (
    tester,
  ) async {
    final harness = await _pumpFromLanding(tester);
    harness.backend
      ..on('/auth/login', _loginSuccess())
      ..on('/me/history', _sessionSnapshot());
    // 세션은 이미 저장되고 서버 이력을 맞추는 중 — 떠나면 화면과 인증이 어긋나던 때입니다.
    final pendingSync = harness.backend.hold('/me/history');

    await _submitLogin(tester);

    expect(harness.backend.requests.map((r) => r.url.path), [
      '/auth/login',
      '/me/history',
    ]);
    expect(harness.provider.isAuthenticated, isTrue);
    expect(isAppBackButtonEnabled(tester), isFalse);

    await tryToLeave(tester);
    for (final link in ['비밀번호를 잊으셨나요?', '계정이 없으신가요? 회원가입']) {
      await tester.ensureVisible(find.text(link));
      await tester.pump();
      await tester.tap(find.text(link));
      await pumpPastTransition(tester);
    }

    expect(find.byType(EmailLoginScreen), findsOneWidget);
    expect(find.text('첫 화면'), findsNothing);
    expect(find.text('비밀번호 찾기 화면'), findsNothing);
    expect(find.text('회원가입 화면'), findsNothing);

    pendingSync.complete();
    await tester.pumpAndSettle();

    expect(find.text('메인 화면'), findsOneWidget);
    expect(find.byType(EmailLoginScreen), findsNothing);
    expect(harness.provider.accessToken, 'server-token');
  });

  testWidgets('로그인이 거절되면 다시 "<"·뒤로가기로 떠날 수 있다', (tester) async {
    final harness = await _pumpFromLanding(tester);
    harness.backend.on(
      '/auth/login',
      serverErrorResponse(401, 'UNAUTHORIZED', '이메일 또는 비밀번호가 올바르지 않습니다.'),
    );
    final pendingLogin = harness.backend.hold('/auth/login');

    await _submitLogin(tester);
    expect(isAppBackButtonEnabled(tester), isFalse);

    pendingLogin.complete();
    await tester.pumpAndSettle();

    expect(harness.provider.isAuthenticated, isFalse);
    expect(find.byType(AppBannerView), findsOneWidget);
    expect(isAppBackButtonEnabled(tester), isTrue);

    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();

    expect(find.byType(EmailLoginScreen), findsNothing);
    expect(find.text('첫 화면'), findsOneWidget);
  });

  testWidgets('자판 인셋이 앱바 아래를 다 덮어 본문 높이가 0 이 돼도 레이아웃 예외가 나지 않는다', (
    tester,
  ) async {
    // iPhone 18 Pro Max(440×956pt, 3배) 크기.
    tester.view.physicalSize = const Size(440 * 3, 956 * 3);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(const MaterialApp(home: EmailLoginScreen()));
    await tester.pumpAndSettle();

    // 보통 자판(약 340pt)은 본문 높이를 넉넉히 남긴다. 2026-09-26 시뮬레이터에서
    // 한 번 난 예외(-12.0)는 아래 인셋이 앱바 아래를 모두 덮어 본문이 0 이 된 프레임이었다.
    tester.view.viewInsets = const FakeViewPadding(bottom: 956 * 3);
    await tester.pump();

    expect(tester.takeException(), isNull);

    // 인셋이 보통 자판 높이로 돌아오면 폼이 다시 그대로 보인다.
    tester.view.viewInsets = const FakeViewPadding(bottom: 336 * 3);
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.byType(TextFormField), findsNWidgets(2));
  });
}

class _Harness {
  _Harness(this.provider, this.backend);

  final ClosetProvider provider;
  final FakeAuthBackend backend;
}

/// 로그인 첫 화면에서 이메일 로그인으로 들어온 실제 순서를 띄웁니다. 아래 링크로 가는 화면과
/// 메인은 글자만 있는 빈 화면입니다.
Future<_Harness> _pumpFromLanding(WidgetTester tester) async {
  final provider = ClosetProvider(
    storage: FakeClosetStorage(),
    authSessionStorage: FakeAuthSessionStorage(),
  );
  final backend = FakeAuthBackend();
  final service = AuthApiService(
    baseUrl: 'https://example.test',
    client: backend.client,
  );

  await tester.pumpWidget(
    ChangeNotifierProvider.value(
      value: provider,
      child: MaterialApp(
        builder: AppBannerHost.builder,
        initialRoute: '/login',
        routes: {
          '/login': (_) => const Scaffold(body: Text('첫 화면')),
          '/email-login': (_) => EmailLoginScreen(authApiService: service),
          '/password-reset': (_) => const Scaffold(body: Text('비밀번호 찾기 화면')),
          '/signup': (_) => const Scaffold(body: Text('회원가입 화면')),
          '/main': (_) => const Scaffold(body: Text('메인 화면')),
        },
      ),
    ),
  );
  final navigator = tester.state<NavigatorState>(find.byType(Navigator));
  navigator.pushNamed('/email-login');
  await tester.pumpAndSettle();

  return _Harness(provider, backend);
}

/// 이메일·비밀번호를 넣고 로그인을 누른 뒤, 붙잡아 둔 요청까지 가도록 몇 번 넘깁니다.
Future<void> _submitLogin(WidgetTester tester) async {
  await tester.enterText(find.widgetWithText(TextFormField, '이메일'), 'a@a.com');
  await tester.enterText(
    find.widgetWithText(TextFormField, '비밀번호'),
    'password123',
  );
  final submit = find.widgetWithText(ElevatedButton, '로그인');
  await tester.ensureVisible(submit);
  await tester.pumpAndSettle();
  await tester.tap(submit);
  for (var i = 0; i < 5; i++) {
    await tester.pump();
  }
}

Map<String, Object?> _user() => {
  'id': 2,
  'email': 'a@a.com',
  'nickname': '테스트',
  'login_methods': ['email'],
};

http.Response _loginSuccess() => jsonResponse({
  'status': 'success',
  'message': '로그인되었습니다.',
  'user': _user(),
  'access_token': 'server-token',
  'token_type': 'bearer',
  'expires_in': 2592000,
}, 200);

http.Response _sessionSnapshot() =>
    jsonResponse({'status': 'success', 'user': _user(), 'history': []}, 200);
