import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
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

  testWidgets('서버 의존 계정 기능은 현재 상태를 정확히 안내한다', (tester) async {
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

    final passwordChange = find.text('비밀번호 변경');
    await tester.ensureVisible(passwordChange);
    await tester.pumpAndSettle();
    await tester.tap(passwordChange);
    await tester.pumpAndSettle();

    expect(find.text('아직 준비 중인 기능이에요. 업데이트 후 사용할 수 있어요.'), findsOneWidget);
  });
}
