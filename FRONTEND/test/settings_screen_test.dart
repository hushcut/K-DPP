import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/material_name_display_provider.dart';
import 'package:k_dpp/services/auth_api_service.dart';
import 'package:k_dpp/settings_screen.dart';
import 'package:k_dpp/theme_provider.dart';
import 'package:k_dpp/widgets/app_banner.dart';
import 'package:provider/provider.dart';

import 'helpers/app_banner_expect.dart';
import 'helpers/fake_auth_session_storage.dart';
import 'helpers/fake_closet_storage.dart';

void main() {
  testWidgets('닉네임 수정은 2자 이상만 기기 표시값으로 저장한다', (tester) async {
    final provider = ClosetProvider(
      storage: FakeClosetStorage(),
      authSessionStorage: FakeAuthSessionStorage(),
    );
    await provider.setAuthenticatedUser(
      nickname: '홍길동',
      email: 'honggildong@example.com',
      accessToken: 'access-token',
      expiresInSeconds: 3600,
    );

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: provider),
          ChangeNotifierProvider(create: (_) => ThemeProvider()),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
        ],
        child: const MaterialApp(
          builder: AppBannerHost.builder,
          home: SettingsScreen(),
        ),
      ),
    );

    await tester.tap(find.text('닉네임'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, '홍');
    await tester.tap(find.widgetWithText(ElevatedButton, '저장'));
    await tester.pumpAndSettle();

    expect(find.text('닉네임은 2자 이상 입력해 주세요.'), findsOneWidget);
    expect(provider.userName, '홍길동');

    await tester.enterText(find.byType(TextField).last, '홍길동 사용자');
    await tester.tap(find.widgetWithText(ElevatedButton, '저장'));
    await tester.pump(const Duration(milliseconds: 400));

    expect(provider.userName, '홍길동 사용자');
    expectAppBanner(tester, '이 기기에 표시되는 닉네임이 바뀌었어요.', AppBannerKind.success);
  });

  testWidgets('이메일이 없는 카카오 계정은 기본 이메일 대신 카카오 계정으로 보인다', (tester) async {
    final provider = ClosetProvider(
      storage: FakeClosetStorage(),
      authSessionStorage: FakeAuthSessionStorage(),
    );
    await provider.setAuthenticatedUser(
      nickname: '카카오 사용자',
      email: null,
      userId: 7,
      loginMethods: const ['kakao'],
      accessToken: 'access-token',
      expiresInSeconds: 3600,
    );

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: provider),
          ChangeNotifierProvider(create: (_) => ThemeProvider()),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
        ],
        child: const MaterialApp(
          builder: AppBannerHost.builder,
          home: SettingsScreen(),
        ),
      ),
    );

    expect(find.text('honggildong@kdpp.com'), findsNothing);
    expect(find.text('이메일'), findsNothing);
    // 프로필 카드와 '내 정보'의 로그인 칸 두 곳입니다.
    expect(find.text('카카오 계정'), findsNWidgets(2));
    expect(find.text('로그인'), findsOneWidget);
  });

  testWidgets('비밀번호 변경은 서버 규칙과 같은 기준으로 먼저 걸러 낸다', (tester) async {
    var requestCount = 0;
    await _pumpSettings(
      tester,
      client: MockClient((request) async {
        requestCount++;
        return http.Response('{}', 200);
      }),
    );

    await _openAccountMenu(tester, '비밀번호 변경');

    // 8자 미만이면 서버에 보내지 않는다.
    await tester.enterText(find.byType(TextField).at(0), 'password123');
    await tester.enterText(find.byType(TextField).at(1), 'short');
    await tester.enterText(find.byType(TextField).at(2), 'short');
    await tester.tap(find.widgetWithText(ElevatedButton, '변경'));
    await tester.pumpAndSettle();

    expect(find.text('비밀번호는 8자 이상 입력해 주세요.'), findsOneWidget);
    expect(requestCount, 0);

    // 확인값이 다르면 역시 보내지 않는다.
    await tester.enterText(find.byType(TextField).at(1), 'newpassword456');
    await tester.enterText(find.byType(TextField).at(2), 'newpassword457');
    await tester.tap(find.widgetWithText(ElevatedButton, '변경'));
    await tester.pumpAndSettle();

    expect(find.text('새 비밀번호가 일치하지 않습니다.'), findsOneWidget);
    expect(requestCount, 0);
  });

  testWidgets('비밀번호 변경에 성공하면 서버가 재발급한 토큰으로 세션을 갱신한다', (tester) async {
    late http.Request captured;
    final harness = await _pumpSettings(
      tester,
      client: MockClient((request) async {
        captured = request;
        return http.Response(
          jsonEncode({
            'status': 'success',
            'user': {
              'id': 1,
              'email': 'honggildong@example.com',
              'nickname': '홍길동',
            },
            'access_token': 'rotated-token',
            'token_type': 'bearer',
            'expires_in': 3600,
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    await _openAccountMenu(tester, '비밀번호 변경');
    await tester.enterText(find.byType(TextField).at(0), 'password123');
    await tester.enterText(find.byType(TextField).at(1), 'newpassword456');
    await tester.enterText(find.byType(TextField).at(2), 'newpassword456');
    await tester.tap(find.widgetWithText(ElevatedButton, '변경'));
    await tester.pumpAndSettle();

    expect(captured.url.path, '/auth/password');
    expect(captured.headers['Authorization'], 'Bearer access-token');
    expect(jsonDecode(captured.body), {
      'current_password': 'password123',
      'new_password': 'newpassword456',
    });
    // 서버가 기존 토큰을 폐기하므로 새 토큰을 반드시 물고 있어야 한다.
    expect(harness.accessToken, 'rotated-token');
    expectAppBanner(
      tester,
      '비밀번호가 바뀌었어요. 다른 기기에서는 다시 로그인해야 해요.',
      AppBannerKind.success,
    );
  });

  testWidgets('현재 비밀번호가 틀리면 안내만 하고 로그아웃하지 않는다', (tester) async {
    final harness = await _pumpSettings(
      tester,
      client: MockClient((request) async {
        // 서버는 재인증 실패를 400으로 낸다(401은 세션 만료 전용).
        return http.Response(
          jsonEncode({'status': 'error', 'message': '현재 비밀번호가 올바르지 않습니다.'}),
          400,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    await _openAccountMenu(tester, '비밀번호 변경');
    await tester.enterText(find.byType(TextField).at(0), 'wrongpassword');
    await tester.enterText(find.byType(TextField).at(1), 'newpassword456');
    await tester.enterText(find.byType(TextField).at(2), 'newpassword456');
    await tester.tap(find.widgetWithText(ElevatedButton, '변경'));
    await tester.pumpAndSettle();

    expect(find.text('현재 비밀번호가 올바르지 않습니다.'), findsOneWidget);
    expect(harness.isAuthenticated, isTrue);
    expect(harness.accessToken, 'access-token');
    expect(find.text('로그인 화면'), findsNothing);
  });

  // DECISIONS 98: 서버 오류 안내를 이어 붙이던 세 문장을 두 문장으로 줄였다.
  testWidgets('서버 로그아웃이 실패해도 기기에서 로그아웃하고, 서버 오류 문장은 덧붙이지 않는다', (tester) async {
    final harness = await _pumpSettings(
      tester,
      client: MockClient((request) async {
        return http.Response(
          jsonEncode({'status': 'error', 'message': '서버 내부 오류입니다.'}),
          500,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    await _openAccountMenu(tester, '로그아웃');
    await tester.tap(find.widgetWithText(ElevatedButton, '로그아웃'));
    await tester.pumpAndSettle();

    expect(harness.isAuthenticated, isFalse);
    expect(find.text('로그인 화면'), findsOneWidget);
    expectAppBanner(tester, '로그아웃했어요. 서버에는 연결하지 못했어요.', AppBannerKind.failure);
  });

  testWidgets('회원 탈퇴에 성공하면 기기의 계정 옷장까지 지우고 로그인 화면으로 보낸다', (tester) async {
    late http.Request captured;
    final storage = FakeClosetStorage();
    final harness = await _pumpSettings(
      tester,
      storage: storage,
      client: MockClient((request) async {
        captured = request;
        return http.Response(
          jsonEncode({'status': 'success', 'message': '회원 탈퇴가 완료되었습니다.'}),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    expect(
      await storage.hasSavedClothesListFor('honggildong@example.com'),
      isTrue,
    );

    await _openAccountMenu(tester, '회원 탈퇴');
    await tester.enterText(find.byType(TextField).first, 'password123');
    await tester.tap(find.widgetWithText(ElevatedButton, '탈퇴'));
    await tester.pumpAndSettle();

    expect(captured.url.path, '/auth/withdraw');
    expect(captured.headers['Authorization'], 'Bearer access-token');
    expect(jsonDecode(captured.body), {'password': 'password123'});
    expect(harness.isAuthenticated, isFalse);
    // 로그아웃과 달리 계정 전용 옷장까지 지워야 한다.
    expect(
      await storage.hasSavedClothesListFor('honggildong@example.com'),
      isFalse,
    );
    expect(find.text('로그인 화면'), findsOneWidget);
    // 스택을 비우고 로그인 화면으로 넘어가도 알림은 남는다.
    expectAppBanner(tester, '회원 탈퇴가 완료됐어요.', AppBannerKind.success);
  });

  testWidgets('회원 탈퇴 뒤 기기의 계정 옷장을 지우지 못하면 탈퇴는 알리되 실패로 띄운다', (tester) async {
    final storage = FakeClosetStorage();
    final harness = await _pumpSettings(
      tester,
      storage: storage,
      client: MockClient((request) async {
        return http.Response(
          jsonEncode({'status': 'success', 'message': '회원 탈퇴가 완료되었습니다.'}),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );
    storage.clearClothesForError = Exception('저장소 쓰기 실패');

    await _openAccountMenu(tester, '회원 탈퇴');
    await tester.enterText(find.byType(TextField).first, 'password123');
    await tester.tap(find.widgetWithText(ElevatedButton, '탈퇴'));
    await tester.pumpAndSettle();

    // 서버 계정은 지워졌으므로 로그아웃해 로그인 화면으로 보내고, 남은 기기 정보만 알린다.
    expect(harness.isAuthenticated, isFalse);
    expect(find.text('로그인 화면'), findsOneWidget);
    expectAppBanner(
      tester,
      '회원 탈퇴가 완료됐어요. 이 기기의 일부 정보는 정리하지 못했어요.',
      AppBannerKind.failure,
    );
  });

  testWidgets('회원 탈퇴가 서버에서 거절되면 기기 데이터를 건드리지 않는다', (tester) async {
    final storage = FakeClosetStorage();
    final harness = await _pumpSettings(
      tester,
      storage: storage,
      client: MockClient((request) async {
        return http.Response(
          jsonEncode({'status': 'error', 'message': '비밀번호가 올바르지 않습니다.'}),
          400,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    await _openAccountMenu(tester, '회원 탈퇴');
    await tester.enterText(find.byType(TextField).first, 'wrongpassword');
    await tester.tap(find.widgetWithText(ElevatedButton, '탈퇴'));
    await tester.pumpAndSettle();

    expect(find.text('비밀번호가 올바르지 않습니다.'), findsOneWidget);
    expect(harness.isAuthenticated, isTrue);
    expect(
      await storage.hasSavedClothesListFor('honggildong@example.com'),
      isTrue,
    );
    expect(find.text('로그인 화면'), findsNothing);
  });

  testWidgets('회원 탈퇴가 401을 받으면 탈퇴됐다고 안내하지 않고 기기 옷장을 남긴다', (tester) async {
    final storage = FakeClosetStorage();
    final harness = await _pumpSettings(
      tester,
      storage: storage,
      // 다른 기기의 비밀번호 변경으로 이 토큰만 폐기된 경우. 계정과 분석 이력은
      // 서버에 그대로 남아 있다(BACKEND/tests/test_withdraw_revoked_token.py).
      client: MockClient((request) async => _withdrawUnauthorized()),
    );

    await _openAccountMenu(tester, '회원 탈퇴');
    await tester.enterText(find.byType(TextField).first, 'password123');
    await tester.tap(find.widgetWithText(ElevatedButton, '탈퇴'));
    await tester.pumpAndSettle();

    expect(harness.isAuthenticated, isFalse);
    // 계정이 남아 있으므로 다시 로그인하면 쓸 옷장도 남긴다.
    expect(
      await storage.hasSavedClothesListFor('honggildong@example.com'),
      isTrue,
    );
    expect(find.text('로그인 화면'), findsOneWidget);
    expectAppBanner(
      tester,
      '로그인이 만료돼 탈퇴되지 않았어요. 다시 로그인한 뒤 탈퇴해 주세요.',
      AppBannerKind.failure,
    );
  });

  testWidgets('결과를 모르는 탈퇴 시도 뒤의 401은 처리 여부를 확인하지 못했다고 안내한다', (tester) async {
    var requestCount = 0;
    final storage = FakeClosetStorage();
    await _pumpSettings(
      tester,
      storage: storage,
      client: MockClient((request) async {
        requestCount++;
        // 서버가 삭제를 마친 뒤 응답만 잃으면, 다시 보낸 요청은 토큰이 지워져 401을 받는다.
        if (requestCount == 1) {
          throw http.ClientException('Connection reset by peer');
        }
        return _withdrawUnauthorized();
      }),
    );

    await _openAccountMenu(tester, '회원 탈퇴');
    await tester.enterText(find.byType(TextField).first, 'password123');
    await tester.tap(find.widgetWithText(ElevatedButton, '탈퇴'));
    await tester.pumpAndSettle();

    expect(
      find.text('인터넷에 연결할 수 없어요. Wi-Fi나 모바일 데이터를 확인해 주세요.'),
      findsOneWidget,
    );

    await tester.tap(find.widgetWithText(ElevatedButton, '탈퇴'));
    await tester.pumpAndSettle();

    expect(requestCount, 2);
    expect(
      await storage.hasSavedClothesListFor('honggildong@example.com'),
      isTrue,
    );
    expect(find.text('로그인 화면'), findsOneWidget);
    expectAppBanner(
      tester,
      '로그인이 만료돼 탈퇴됐는지 확인하지 못했어요. 다시 로그인되면 탈퇴를 다시 해 주세요.',
      AppBannerKind.failure,
    );
  });

  testWidgets('비밀번호가 틀려 거절된 뒤의 401은 탈퇴가 진행되지 않았다고 안내한다', (tester) async {
    var requestCount = 0;
    await _pumpSettings(
      tester,
      client: MockClient((request) async {
        requestCount++;
        // 400은 서버가 삭제 전에 거절한 것이라 앞선 시도의 결과가 분명하다.
        if (requestCount == 1) {
          return http.Response(
            jsonEncode({'status': 'error', 'message': '비밀번호가 올바르지 않습니다.'}),
            400,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }
        return _withdrawUnauthorized();
      }),
    );

    await _openAccountMenu(tester, '회원 탈퇴');
    await tester.enterText(find.byType(TextField).first, 'wrongpassword');
    await tester.tap(find.widgetWithText(ElevatedButton, '탈퇴'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).first, 'password123');
    await tester.tap(find.widgetWithText(ElevatedButton, '탈퇴'));
    await tester.pumpAndSettle();

    expect(requestCount, 2);
    expectAppBanner(
      tester,
      '로그인이 만료돼 탈퇴되지 않았어요. 다시 로그인한 뒤 탈퇴해 주세요.',
      AppBannerKind.failure,
    );
  });

  testWidgets('요청이 진행 중이면 버튼 연타로 중복 전송되지 않는다', (tester) async {
    var requestCount = 0;
    final gate = Completer<void>();
    await _pumpSettings(
      tester,
      client: MockClient((request) async {
        requestCount++;
        await gate.future;
        return http.Response(
          jsonEncode({
            'status': 'success',
            'user': {
              'id': 1,
              'email': 'honggildong@example.com',
              'nickname': '홍길동',
            },
            'access_token': 'rotated-token',
            'token_type': 'bearer',
            'expires_in': 3600,
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    await _openAccountMenu(tester, '비밀번호 변경');
    await tester.enterText(find.byType(TextField).at(0), 'password123');
    await tester.enterText(find.byType(TextField).at(1), 'newpassword456');
    await tester.enterText(find.byType(TextField).at(2), 'newpassword456');

    await tester.tap(find.widgetWithText(ElevatedButton, '변경'));
    await tester.pump();

    // 진행 중에는 버튼이 사라지고 진행 표시만 남는다.
    expect(find.widgetWithText(ElevatedButton, '변경'), findsNothing);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    // 같은 위치를 다시 눌러도 두 번째 요청은 나가지 않는다.
    await tester.tap(find.byType(ElevatedButton).last, warnIfMissed: false);
    await tester.pump();

    expect(requestCount, 1);

    gate.complete();
    await tester.pumpAndSettle();

    expect(requestCount, 1);
  });

  testWidgets('서버가 거절하면 대화상자를 닫지 않고 입력을 유지한 채 오류를 보여 준다', (tester) async {
    await _pumpSettings(
      tester,
      client: MockClient((request) async {
        return http.Response(
          jsonEncode({'status': 'error', 'message': '현재 비밀번호가 올바르지 않습니다.'}),
          400,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );

    await _openAccountMenu(tester, '비밀번호 변경');
    await tester.enterText(find.byType(TextField).at(0), 'wrongpassword');
    await tester.enterText(find.byType(TextField).at(1), 'newpassword456');
    await tester.enterText(find.byType(TextField).at(2), 'newpassword456');
    await tester.tap(find.widgetWithText(ElevatedButton, '변경'));
    await tester.pumpAndSettle();

    // 대화상자가 그대로 열려 있고 세 입력이 살아 있어야 다시 타이핑하지 않는다.
    expect(find.byType(AlertDialog), findsOneWidget);
    expect(find.text('현재 비밀번호가 올바르지 않습니다.'), findsOneWidget);
    expect(
      tester.widget<TextField>(find.byType(TextField).at(1)).controller?.text,
      'newpassword456',
    );
    expect(
      tester.widget<TextField>(find.byType(TextField).at(2)).controller?.text,
      'newpassword456',
    );
  });

  testWidgets('사진 및 권한 안내에서 스캔 이미지 처리 방식을 확인할 수 있다', (tester) async {
    final provider = ClosetProvider(
      storage: FakeClosetStorage(),
      authSessionStorage: FakeAuthSessionStorage(),
    );

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: provider),
          ChangeNotifierProvider(create: (_) => ThemeProvider()),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
        ],
        child: const MaterialApp(
          builder: AppBannerHost.builder,
          home: SettingsScreen(),
        ),
      ),
    );

    final privacyGuide = find.text('사진 및 권한 안내');
    await tester.ensureVisible(privacyGuide);
    await tester.pumpAndSettle();
    await tester.tap(privacyGuide);
    await tester.pumpAndSettle();

    expect(find.text('카메라는 스캔 화면에서만 켜지고, 다른 화면에서는 사용하지 않습니다.'), findsOneWidget);
    expect(find.text('카메라로 새로 촬영한 임시 파일은 분석이 끝난 뒤 정리합니다.'), findsOneWidget);
  });
}


/// 계정 관리 흐름 테스트가 공유하는 로그인 상태의 설정 화면입니다.
///
/// 탈퇴는 로그인 화면으로 이동하므로 `/login` 라우트를 함께 등록합니다.
Future<ClosetProvider> _pumpSettings(
  WidgetTester tester, {
  required MockClient client,
  FakeClosetStorage? storage,
}) async {
  final resolvedStorage = storage ?? FakeClosetStorage();
  final provider = ClosetProvider(
    storage: resolvedStorage,
    authSessionStorage: FakeAuthSessionStorage(),
  );
  await provider.setAuthenticatedUser(
    nickname: '홍길동',
    email: 'honggildong@example.com',
    accessToken: 'access-token',
    expiresInSeconds: 3600,
  );
  // 탈퇴가 계정 전용 옷장까지 지우는지 보려면 저장된 옷장 키가 먼저 있어야 합니다.
  await resolvedStorage.saveClothesListFor('honggildong@example.com', const []);

  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider.value(value: provider),
        ChangeNotifierProvider(create: (_) => ThemeProvider()),
        ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
      ],
      child: MaterialApp(
        builder: AppBannerHost.builder,
        home: SettingsScreen(
          authApiService: AuthApiService(
            baseUrl: 'https://example.test',
            client: client,
          ),
        ),
        routes: {
          '/login': (_) => const Scaffold(body: Text('로그인 화면')),
        },
      ),
    ),
  );

  return provider;
}

/// 폐기·만료된 토큰으로 탈퇴를 요청했을 때 서버(main.py `get_current_access_token`)가
/// 보내는 응답입니다. 이미 탈퇴해 토큰이 지워진 계정도 똑같은 응답을 받습니다.
http.Response _withdrawUnauthorized() {
  return http.Response(
    jsonEncode({
      'status': 'error',
      'error_code': 'AUTH_REQUIRED',
      'message': '로그인이 만료되었습니다.',
      'detail': '로그인이 만료되었습니다.',
    }),
    401,
    headers: {'content-type': 'application/json; charset=utf-8'},
  );
}

/// '계정 관리' 섹션의 메뉴는 스크롤해야 보이므로 눌러 대화상자를 엽니다.
Future<void> _openAccountMenu(WidgetTester tester, String title) async {
  final menu = find.text(title);
  await tester.scrollUntilVisible(
    menu,
    220,
    scrollable: find.byType(Scrollable).first,
  );
  await tester.pumpAndSettle();
  await tester.tap(menu);
  await tester.pumpAndSettle();
}
