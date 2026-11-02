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
    expect(find.text('이메일 또는 비밀번호가 올바르지 않습니다.'), findsOneWidget);
    // 거절이면 세션을 남기지 않고, 서버 이력도 부르지 않습니다.
    expect(harness.sessionStorage.savedSession, isNull);
    expect(harness.backend.requests.map((r) => r.url.path), ['/auth/login']);
    expect(isAppBackButtonEnabled(tester), isTrue);

    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();

    expect(find.byType(EmailLoginScreen), findsNothing);
    expect(find.text('첫 화면'), findsOneWidget);
  });

  // C35: 아래는 NEXT_WORK 가 이 화면 전용 시험이 없다고 적었던 분기들입니다.
  testWidgets('형식이 틀리면 서버에 보내지 않고 칸 아래에 이유를 보인다', (tester) async {
    final harness = await _pumpFromLanding(tester);

    await _submitLogin(tester, email: 'aa.com', password: 'short');
    await tester.pumpAndSettle();

    expect(find.text('올바른 이메일 형식을 입력해 주세요'), findsOneWidget);
    expect(find.text('비밀번호는 8자 이상 입력해 주세요'), findsOneWidget);

    await _submitLogin(tester, email: '', password: '');
    await tester.pumpAndSettle();

    expect(find.text('이메일을 입력해 주세요'), findsOneWidget);
    expect(find.text('비밀번호를 입력해 주세요'), findsOneWidget);

    expect(harness.backend.requests, isEmpty);
    expect(find.byType(EmailLoginScreen), findsOneWidget);
  });

  testWidgets('이메일은 앞뒤 공백을 떼고 비밀번호는 그대로 보내며, 성공하면 세션을 저장하고 돌아올 수 없게 메인으로 간다', (
    tester,
  ) async {
    final harness = await _pumpFromLanding(tester);
    harness.backend
      ..on('/auth/login', _loginSuccess())
      ..on('/me/history', _sessionSnapshot());

    await _submitLogin(tester, email: '  a@a.com ', password: ' password123 ');
    await tester.pumpAndSettle();

    expect(harness.backend.bodiesFor('/auth/login'), [
      {'email': 'a@a.com', 'password': ' password123 '},
    ]);
    expect(harness.sessionStorage.savedSession?.accessToken, 'server-token');
    expect(harness.provider.accessToken, 'server-token');
    expect(harness.provider.userEmail, 'a@a.com');
    expect(find.text('메인 화면'), findsOneWidget);
    // 첫 화면·이메일 로그인 화면을 모두 걷어 내, 뒤로가기로 인증 화면에 돌아오지 않습니다.
    expect(find.text('첫 화면', skipOffstage: false), findsNothing);
    expect(find.byType(EmailLoginScreen, skipOffstage: false), findsNothing);
  });

  testWidgets('서버는 받아 줬지만 기기에 세션을 저장하지 못하면 로그인되지 않은 채 안내한다', (
    tester,
  ) async {
    final harness = await _pumpFromLanding(tester);
    harness.sessionStorage.saveError = StateError('보안 저장소 실패');
    harness.backend
      ..on('/auth/login', _loginSuccess())
      ..on('/me/history', _sessionSnapshot());

    await _submitLogin(tester);
    await tester.pumpAndSettle();

    expect(
      find.text('로그인 정보를 안전하게 저장하지 못했어요. 다시 시도해 주세요.'),
      findsOneWidget,
    );
    expect(harness.provider.isAuthenticated, isFalse);
    expect(harness.provider.accessToken, isNull);
    // 세션이 없으니 서버 이력도 부르지 않고 이 화면에 남습니다.
    expect(harness.backend.requests.map((r) => r.url.path), ['/auth/login']);
    expect(find.byType(EmailLoginScreen), findsOneWidget);
    expect(find.text('메인 화면'), findsNothing);
    expect(isAppBackButtonEnabled(tester), isTrue);
  });

  testWidgets('경로 인자로 받은 이메일은 앞뒤 공백을 떼고 이메일 칸에 채운다', (tester) async {
    String emailField() => tester
        .widget<TextFormField>(find.widgetWithText(TextFormField, '이메일'))
        .controller!
        .text;

    await _pumpFromLanding(tester, emailArgument: '  b@b.com ');
    expect(emailField(), 'b@b.com');

    // 공백뿐이거나 문자열이 아닌 인자는 무시합니다.
    for (final argument in <Object>['   ', 3]) {
      await tester.pumpWidget(const SizedBox.shrink());
      await _pumpFromLanding(tester, emailArgument: argument);
      expect(emailField(), isEmpty, reason: '$argument');
    }
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
  _Harness(this.provider, this.backend, this.sessionStorage);

  final ClosetProvider provider;
  final FakeAuthBackend backend;
  final FakeAuthSessionStorage sessionStorage;
}

/// 로그인 첫 화면에서 이메일 로그인으로 들어온 실제 순서를 띄웁니다. 아래 링크로 가는 화면과
/// 메인은 글자만 있는 빈 화면입니다. [emailArgument] 는 이메일 로그인 경로에 넘기는 인자입니다
/// (회원가입·비밀번호 찾기에서 넘어올 때의 이메일).
Future<_Harness> _pumpFromLanding(
  WidgetTester tester, {
  Object? emailArgument,
}) async {
  final sessionStorage = FakeAuthSessionStorage();
  final provider = ClosetProvider(
    storage: FakeClosetStorage(),
    authSessionStorage: sessionStorage,
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
  navigator.pushNamed('/email-login', arguments: emailArgument);
  await tester.pumpAndSettle();

  return _Harness(provider, backend, sessionStorage);
}

/// 이메일·비밀번호를 넣고 로그인을 누른 뒤, 붙잡아 둔 요청까지 가도록 몇 번 넘깁니다.
Future<void> _submitLogin(
  WidgetTester tester, {
  String email = 'a@a.com',
  String password = 'password123',
}) async {
  await tester.enterText(find.widgetWithText(TextFormField, '이메일'), email);
  await tester.enterText(
    find.widgetWithText(TextFormField, '비밀번호'),
    password,
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
