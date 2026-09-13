import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/services/auth_api_service.dart';
import 'package:k_dpp/settings_screen.dart';
import 'package:k_dpp/theme_provider.dart';
import 'package:provider/provider.dart';

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
        ],
        child: const MaterialApp(home: SettingsScreen()),
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
    expect(find.text('이 기기에 표시되는 닉네임이 변경되었습니다.'), findsOneWidget);
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
    expect(
      find.text('비밀번호가 변경되었습니다. 다른 기기에서는 다시 로그인해야 합니다.'),
      findsOneWidget,
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
        ],
        child: const MaterialApp(home: SettingsScreen()),
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
      ],
      child: MaterialApp(
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
