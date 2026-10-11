import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/kakao_nickname_screen.dart';
import 'package:k_dpp/login_screen.dart';
import 'package:k_dpp/services/auth_api_service.dart';
import 'package:k_dpp/widgets/app_back_button.dart';
import 'package:k_dpp/widgets/app_banner.dart';
import 'package:k_dpp/widgets/auth_form_widgets.dart';
import 'package:k_dpp/widgets/kakao_login_button.dart';
import 'package:provider/provider.dart';

import 'helpers/app_banner_expect.dart';
import 'helpers/fake_auth_backend.dart';
import 'helpers/fake_auth_session_storage.dart';
import 'helpers/fake_closet_storage.dart';
import 'helpers/fake_kakao_sdk.dart';

void main() {
  testWidgets('로그인 화면 오른쪽 위를 눌러도 인증 없이 메인으로 이동하지 않는다', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        initialRoute: '/login',
        routes: {
          '/login': (context) => const LoginScreen(),
          '/main': (context) => const Scaffold(body: Text('메인 화면')),
        },
      ),
    );

    expect(find.text('K-DPP'), findsOneWidget);
    expect(find.text('메인 화면'), findsNothing);

    final screenSize = tester.view.physicalSize / tester.view.devicePixelRatio;
    await tester.tapAt(Offset(screenSize.width - 20, 20));
    await tester.pumpAndSettle();

    expect(find.text('K-DPP'), findsOneWidget);
    expect(find.text('메인 화면'), findsNothing);
  });

  testWidgets('작은 화면과 큰 글자에서도 카카오 버튼이 있는 로그인 랜딩이 넘치지 않는다', (tester) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      const MaterialApp(
        home: MediaQuery(
          data: MediaQueryData(textScaler: TextScaler.linear(1.8)),
          child: LoginScreen(showKakaoLogin: true),
        ),
      ),
    );
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 200)),
    );
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.byType(KakaoLoginButton), findsOneWidget);
    expect(find.text('이메일로 로그인'), findsOneWidget);
    expect(find.text('계정이 없으신가요? 회원가입'), findsOneWidget);
  });

  testWidgets('카카오 키가 없는 빌드는 카카오 버튼 없이 이메일로 로그인만 보인다', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        routes: {
          '/': (_) => const LoginScreen(showKakaoLogin: false),
          '/email-login': (_) => const Scaffold(body: Text('이메일 로그인 화면')),
        },
      ),
    );

    expect(find.byType(KakaoLoginButton), findsNothing);
    // 키가 있든 없든 같은 글자라, 빌드마다 버튼 이름이 바뀌지 않는다(DECISIONS 183 ①).
    expect(find.text('이메일로 로그인'), findsOneWidget);
    expect(find.text('로그인'), findsNothing);

    await tester.tap(find.text('이메일로 로그인'));
    await tester.pumpAndSettle();

    expect(find.text('이메일 로그인 화면'), findsOneWidget);
  });

  testWidgets('카카오 버튼은 이메일 로그인 위에, 회원가입 링크는 이메일 로그인 바로 아래에 있다', (tester) async {
    await _pumpLogin(tester);

    final kakaoTop = tester.getTopLeft(find.byType(KakaoLoginButton)).dy;
    final emailTop = tester.getTopLeft(find.text('이메일로 로그인')).dy;
    final signupTop = tester.getTopLeft(find.text('계정이 없으신가요? 회원가입')).dy;

    expect(kakaoTop, lessThan(emailTop));
    expect(emailTop, lessThan(signupTop));

    // 회원가입 링크는 다른 인증 화면과 같은 공용 링크다(밑줄 없음·동작 글자 강조 —
    // auth_link_button_test.dart).
    expect(
      find.widgetWithText(AuthLinkButton, '계정이 없으신가요? 회원가입'),
      findsOneWidget,
    );
  });

  testWidgets('카카오 화면에서 취소하면 서버를 부르지 않고 버튼이 다시 눌린다', (tester) async {
    final harness = await _pumpLogin(tester);
    harness.sdk.nextAccountLogin = FakeKakaoSdk.cancelled();

    await tester.tap(find.byType(KakaoLoginButton));
    await tester.pumpAndSettle();

    expect(harness.backend.requests, isEmpty);
    expect(find.byType(AppBannerView), findsNothing);
    expect(_kakaoButton(tester).isLoading, isFalse);

    await tester.tap(find.byType(KakaoLoginButton));
    await tester.pumpAndSettle();

    expect(harness.sdk.accountLoginPrompts, hasLength(2));
  });

  testWidgets('이미 있는 카카오 계정이면 카카오 토큰만 보내 로그인하고 메인으로 간다', (tester) async {
    final harness = await _pumpLogin(tester);
    harness.backend
      ..on('/auth/kakao', _kakaoLoginSuccess(isNewUser: false))
      ..on('/me/history', _kakaoSessionSnapshot());

    await tester.tap(find.byType(KakaoLoginButton));
    await tester.pumpAndSettle();

    expect(harness.backend.bodiesFor('/auth/kakao'), [
      {'access_token': 'kakao-access-token'},
    ]);
    expect(harness.provider.isAuthenticated, isTrue);
    expect(harness.provider.accessToken, 'server-token');
    expect(harness.provider.accountEmail, isNull);
    expect(harness.provider.loginMethods, ['kakao']);
    expect(harness.provider.userName, '카카오 사용자');
    expect(find.text('메인 화면'), findsOneWidget);
    // 이메일 로그인처럼 조용히 들어간다 — 가입 안내는 새 계정에만.
    expect(find.byType(AppBannerView), findsNothing);
  });

  testWidgets('처음 온 카카오 계정이면 새 계정으로 가입했다고 알린다', (tester) async {
    final harness = await _pumpLogin(tester);
    harness.backend
      ..on('/auth/kakao', _kakaoLoginSuccess(isNewUser: true))
      ..on('/me/history', _kakaoSessionSnapshot());

    await tester.tap(find.byType(KakaoLoginButton));
    await tester.pumpAndSettle();

    expect(find.text('메인 화면'), findsOneWidget);
    expectAppBanner(tester, '카카오 계정으로 가입했어요.', AppBannerKind.success);
  });

  testWidgets('서버가 닉네임을 요구하면 닉네임 화면에서 받아 같은 카카오 토큰으로 다시 보낸다', (tester) async {
    final harness = await _pumpLogin(tester);
    harness.backend
      ..on('/auth/kakao', _nicknameRequired())
      ..on('/auth/kakao', _kakaoLoginSuccess(isNewUser: true))
      ..on('/me/history', _kakaoSessionSnapshot());

    await tester.tap(find.byType(KakaoLoginButton));
    await tester.pumpAndSettle();

    expect(find.byType(KakaoNicknameScreen), findsOneWidget);
    expect(find.text('닉네임 정하기'), findsOneWidget);

    // 가입과 같은 규칙(2자 이상·50자 이하)으로 먼저 거른다.
    await tester.enterText(find.byType(TextFormField), '홍');
    await tester.tap(find.text('시작하기'));
    await tester.pumpAndSettle();

    expect(find.text('닉네임은 2자 이상 입력해 주세요'), findsOneWidget);

    await tester.enterText(find.byType(TextFormField), '가' * 51);
    await tester.tap(find.text('시작하기'));
    await tester.pumpAndSettle();

    expect(find.text('닉네임은 50자 이하로 입력해 주세요'), findsOneWidget);
    expect(harness.backend.bodiesFor('/auth/kakao'), hasLength(1));

    await tester.enterText(find.byType(TextFormField), '  새 닉네임 ');
    await tester.tap(find.text('시작하기'));
    await tester.pumpAndSettle();

    expect(harness.backend.bodiesFor('/auth/kakao'), [
      {'access_token': 'kakao-access-token'},
      {'access_token': 'kakao-access-token', 'nickname': '새 닉네임'},
    ]);
    // 카카오 로그인은 한 번만 — 받아 둔 토큰을 다시 쓴다.
    expect(harness.sdk.accountLoginPrompts, hasLength(1));
    expect(harness.provider.isAuthenticated, isTrue);
    expect(find.byType(KakaoNicknameScreen), findsNothing);
    expect(find.text('메인 화면'), findsOneWidget);
    expectAppBanner(tester, '카카오 계정으로 가입했어요.', AppBannerKind.success);
  });

  testWidgets('닉네임 화면에서 카카오 토큰이 거부되면 로그인 화면으로 돌아가 카카오 로그인부터 다시 하게 한다', (
    tester,
  ) async {
    final harness = await _pumpLogin(tester);
    harness.backend
      ..on('/auth/kakao', _nicknameRequired())
      ..on(
        '/auth/kakao',
        serverErrorResponse(
          401,
          'SOCIAL_TOKEN_INVALID',
          '카카오 로그인을 확인하지 못했습니다. 카카오 로그인을 다시 해 주세요.',
        ),
      );

    await tester.tap(find.byType(KakaoLoginButton));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField), '새 닉네임');
    await tester.tap(find.text('시작하기'));
    await tester.pumpAndSettle();

    expect(find.byType(KakaoNicknameScreen), findsNothing);
    expect(find.byType(KakaoLoginButton), findsOneWidget);
    expect(_kakaoButton(tester).isLoading, isFalse);
    expect(harness.provider.isAuthenticated, isFalse);
    expectAppBanner(
      tester,
      '카카오 로그인을 확인하지 못했어요. 카카오 로그인부터 다시 해 주세요.',
      AppBannerKind.failure,
    );
  });

  testWidgets('서버가 닉네임을 거절하면 닉네임 칸에 보이고 닉네임 화면에 남는다', (tester) async {
    final harness = await _pumpLogin(tester);
    harness.backend
      ..on('/auth/kakao', _nicknameRequired())
      ..on(
        '/auth/kakao',
        serverErrorResponse(400, 'BAD_REQUEST', '닉네임에 쓸 수 없는 문자가 있습니다.'),
      );

    await tester.tap(find.byType(KakaoLoginButton));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField), '새 닉네임');
    await tester.tap(find.text('시작하기'));
    await tester.pumpAndSettle();

    expect(find.byType(KakaoNicknameScreen), findsOneWidget);
    expect(find.text('닉네임에 쓸 수 없는 문자가 있습니다.'), findsOneWidget);
    // 입력은 그대로 두어 고쳐서 다시 보낼 수 있다.
    expect(find.text('새 닉네임'), findsOneWidget);
    expect(find.byType(AppBannerView), findsNothing);

    // 고치기 시작하면 서버 오류는 지운다.
    await tester.enterText(find.byType(TextFormField), '새 닉네임2');
    await tester.pump();

    expect(find.text('닉네임에 쓸 수 없는 문자가 있습니다.'), findsNothing);
    expect(harness.provider.isAuthenticated, isFalse);
  });

  testWidgets('닉네임 화면에서 카카오가 응답하지 않으면 알리고 입력을 둔 채 남는다', (tester) async {
    final harness = await _pumpLogin(tester);
    harness.backend
      ..on('/auth/kakao', _nicknameRequired())
      ..on(
        '/auth/kakao',
        serverErrorResponse(
          502,
          'SOCIAL_PROVIDER_UNAVAILABLE',
          '카카오 서버가 응답하지 않습니다. 잠시 후 다시 시도해 주세요.',
        ),
      );

    await tester.tap(find.byType(KakaoLoginButton));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField), '새 닉네임');
    await tester.tap(find.text('시작하기'));
    await tester.pumpAndSettle();

    expect(find.byType(KakaoNicknameScreen), findsOneWidget);
    expect(find.text('새 닉네임'), findsOneWidget);
    expectAppBanner(
      tester,
      '카카오가 응답하지 않아요. 잠시 후 다시 시도해 주세요.',
      AppBannerKind.failure,
    );
    expect(harness.provider.isAuthenticated, isFalse);
  });

  testWidgets('닉네임 화면에서 뒤로 가면 아무것도 보내지 않고 로그인 화면으로 돌아온다', (tester) async {
    final harness = await _pumpLogin(tester);
    harness.backend.on('/auth/kakao', _nicknameRequired());

    await tester.tap(find.byType(KakaoLoginButton));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(AppBackButton));
    await tester.pumpAndSettle();

    expect(find.byType(KakaoNicknameScreen), findsNothing);
    expect(harness.backend.bodiesFor('/auth/kakao'), hasLength(1));
    expect(harness.provider.isAuthenticated, isFalse);
    expect(find.byType(AppBannerView), findsNothing);
    expect(_kakaoButton(tester).isLoading, isFalse);
  });

  testWidgets('카카오가 응답하지 않으면 잠시 후 다시 하라고 알리고 로그인 화면에 남는다', (tester) async {
    final harness = await _pumpLogin(tester);
    harness.backend.on(
      '/auth/kakao',
      serverErrorResponse(
        502,
        'SOCIAL_PROVIDER_UNAVAILABLE',
        '카카오 서버가 응답하지 않습니다. 잠시 후 다시 시도해 주세요.',
      ),
    );

    await tester.tap(find.byType(KakaoLoginButton));
    await tester.pumpAndSettle();

    expect(find.byType(KakaoLoginButton), findsOneWidget);
    expect(_kakaoButton(tester).isLoading, isFalse);
    expect(harness.provider.isAuthenticated, isFalse);
    expectAppBanner(
      tester,
      '카카오가 응답하지 않아요. 잠시 후 다시 시도해 주세요.',
      AppBannerKind.failure,
    );
  });

  testWidgets('카카오 SDK 가 취소가 아닌 이유로 실패하면 서버를 부르지 않고 알린다', (tester) async {
    final harness = await _pumpLogin(tester);
    harness.sdk.nextAccountLogin = PlatformException(code: 'NetworkError');

    await tester.tap(find.byType(KakaoLoginButton));
    await tester.pumpAndSettle();

    expect(harness.backend.requests, isEmpty);
    expectAppBanner(
      tester,
      '카카오 로그인을 마치지 못했어요. 잠시 후 다시 시도해 주세요.',
      AppBannerKind.failure,
    );
  });

  testWidgets('카카오 로그인 중에는 카카오·이메일 로그인 버튼과 회원가입 링크가 모두 눌리지 않는다', (
    tester,
  ) async {
    final harness = await _pumpLogin(tester);
    final pendingLogin = Completer<String>();
    harness.sdk.nextAccountLogin = pendingLogin;

    await tester.tap(find.byType(KakaoLoginButton));
    await tester.pump();

    expect(_kakaoButton(tester).isLoading, isTrue);

    await tester.tap(find.byType(KakaoLoginButton), warnIfMissed: false);
    await tester.tap(find.text('이메일로 로그인'));
    await tester.tap(find.text('계정이 없으신가요? 회원가입'));
    // 진행 표시가 계속 돌아 pumpAndSettle 은 끝나지 않는다 — 화면 전환 시간만큼만 넘긴다.
    await tester.pump(const Duration(milliseconds: 500));

    expect(harness.sdk.accountLoginPrompts, hasLength(1));
    expect(find.text('이메일 로그인 화면'), findsNothing);
    expect(find.text('회원가입 화면'), findsNothing);

    pendingLogin.completeError(FakeKakaoSdk.cancelled());
    await tester.pumpAndSettle();

    expect(_kakaoButton(tester).isLoading, isFalse);
  });
}

class _LoginHarness {
  _LoginHarness(this.provider, this.backend, this.sdk);

  final ClosetProvider provider;
  final FakeAuthBackend backend;
  final FakeKakaoSdk sdk;
}

/// 카카오 버튼이 보이는 로그인 화면입니다. 성공하면 `/main`, 이메일 로그인은 `/email-login`,
/// 회원가입은 `/signup`.
Future<_LoginHarness> _pumpLogin(WidgetTester tester) async {
  final provider = ClosetProvider(
    storage: FakeClosetStorage(),
    authSessionStorage: FakeAuthSessionStorage(),
  );
  final backend = FakeAuthBackend();
  final sdk = FakeKakaoSdk();

  await tester.pumpWidget(
    ChangeNotifierProvider.value(
      value: provider,
      child: MaterialApp(
        builder: AppBannerHost.builder,
        initialRoute: '/login',
        routes: {
          '/login': (_) => LoginScreen(
            authApiService: AuthApiService(
              baseUrl: 'https://example.test',
              client: backend.client,
            ),
            kakaoLoginService: sdk.service(),
            showKakaoLogin: true,
          ),
          '/email-login': (_) => const Scaffold(body: Text('이메일 로그인 화면')),
          '/signup': (_) => const Scaffold(body: Text('회원가입 화면')),
          '/main': (_) => const Scaffold(body: Text('메인 화면')),
        },
      ),
    ),
  );

  return _LoginHarness(provider, backend, sdk);
}

KakaoLoginButton _kakaoButton(WidgetTester tester) {
  return tester.widget<KakaoLoginButton>(find.byType(KakaoLoginButton));
}

Map<String, Object?> _kakaoUser() {
  return {
    'id': 7,
    'email': null,
    'nickname': '카카오 사용자',
    'login_methods': ['kakao'],
  };
}

http.Response _kakaoLoginSuccess({required bool isNewUser}) {
  return jsonResponse({
    'status': 'success',
    'message': isNewUser ? '카카오 계정으로 가입했습니다.' : '로그인되었습니다.',
    'user': _kakaoUser(),
    'access_token': 'server-token',
    'token_type': 'bearer',
    'expires_in': 2592000,
    'is_new_user': isNewUser,
  }, 200);
}

http.Response _kakaoSessionSnapshot() {
  return jsonResponse({
    'status': 'success',
    'user': _kakaoUser(),
    'history': [],
  }, 200);
}

http.Response _nicknameRequired() {
  return serverErrorResponse(
    400,
    'SOCIAL_NICKNAME_REQUIRED',
    '사용할 닉네임을 입력해 주세요.',
  );
}
