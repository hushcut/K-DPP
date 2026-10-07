import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/email_login_screen.dart';
import 'package:k_dpp/password_reset_screen.dart';
import 'package:k_dpp/services/auth_api_service.dart';
import 'package:k_dpp/widgets/app_banner.dart';

import 'helpers/app_banner_expect.dart';
import 'helpers/fake_auth_backend.dart';

void main() {
  late DateTime now;
  late FakeAuthBackend backend;

  setUp(() {
    now = DateTime(2026, 10, 7, 13);
    backend = FakeAuthBackend();
  });

  // 비밀번호 찾기 화면이 위에 있을 때 아래 로그인 화면은 offstage 라 기본 찾기에서 빠집니다.
  Finder field(String label) => find.widgetWithText(TextFormField, label);

  String fieldText(WidgetTester tester, String label) => tester
      .widget<EditableText>(
        find.descendant(of: field(label), matching: find.byType(EditableText)),
      )
      .controller
      .text;

  Future<void> tapVisible(WidgetTester tester, Finder finder) async {
    await tester.ensureVisible(finder);
    await tester.pumpAndSettle();
    await tester.tap(finder);
    await tester.pumpAndSettle();
  }

  /// 로그인 화면에서 '비밀번호를 잊으셨나요?'로 들어가는 실제 경로를 띄웁니다.
  Future<void> pumpLoginWithReset(WidgetTester tester) async {
    final service = AuthApiService(client: backend.client);

    await tester.pumpWidget(
      MaterialApp(
        builder: AppBannerHost.builder,
        home: EmailLoginScreen(authApiService: service),
        routes: {
          '/password-reset': (_) =>
              PasswordResetScreen(authApiService: service, now: () => now),
        },
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('로그인 화면의 비밀번호 찾기는 적어 둔 이메일을 채워 연다', (tester) async {
    await pumpLoginWithReset(tester);
    await tester.enterText(field('이메일'), ' honggildong@example.com ');
    await tapVisible(tester, find.text('비밀번호를 잊으셨나요?'));

    expect(find.byType(PasswordResetScreen), findsOneWidget);
    expect(fieldText(tester, '이메일'), 'honggildong@example.com');
    expect(find.text('인증번호 받기를 누르면 가입된 이메일로 6자리 숫자를 보내 드려요'), findsOneWidget);
  });

  testWidgets('번호를 받아 새 비밀번호로 바꾸면 로그인 화면에 이메일을 채우고 옛 비밀번호를 지운다', (
    tester,
  ) async {
    backend
      ..on(
        '/auth/email-code',
        emailCodeSentResponse(
          message: '가입된 이메일이면 인증번호를 보냈습니다. 메일이 오지 않으면 주소를 확인해 주세요.',
        ),
      )
      ..on(
        '/auth/password-reset',
        jsonResponse({
          'status': 'success',
          'message': '비밀번호를 다시 설정했습니다. 새 비밀번호로 로그인해 주세요.',
        }, 200),
      );
    await pumpLoginWithReset(tester);
    await tester.enterText(field('비밀번호'), 'old-password');
    await tapVisible(tester, find.text('비밀번호를 잊으셨나요?'));

    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await tapVisible(tester, find.byType(OutlinedButton));

    expect(backend.bodiesFor('/auth/email-code').single, {
      'email': 'honggildong@example.com',
      'purpose': 'password_reset',
    });
    expectAppBanner(
      tester,
      '가입된 이메일이면 인증번호를 보냈어요. 메일이 오지 않으면 주소를 확인해 주세요.',
      AppBannerKind.success,
    );

    await tester.enterText(field('인증번호'), '123456');
    await tester.enterText(field('새 비밀번호'), 'newpassword123');
    await tester.enterText(field('새 비밀번호 확인'), 'newpassword123');
    await tapVisible(tester, find.widgetWithText(ElevatedButton, '비밀번호 다시 설정'));

    expect(backend.bodiesFor('/auth/password-reset').single, {
      'email': 'honggildong@example.com',
      'code': '123456',
      'new_password': 'newpassword123',
    });
    expect(find.byType(PasswordResetScreen), findsNothing);
    expect(fieldText(tester, '이메일'), 'honggildong@example.com');
    expect(fieldText(tester, '비밀번호'), isEmpty);
    expectAppBanner(
      tester,
      '비밀번호를 다시 설정했어요. 새 비밀번호로 로그인해 주세요.',
      AppBannerKind.success,
    );
  });

  testWidgets('다시 받아야 하는 번호는 화면에 남아 번호 칸에 보이고, 로그인으로 돌아가지 않는다', (tester) async {
    backend
      ..on('/auth/email-code', emailCodeSentResponse())
      ..on(
        '/auth/password-reset',
        serverErrorResponse(
          400,
          'VERIFICATION_CODE_RESEND_REQUIRED',
          '인증번호가 없거나 만료되었습니다. 인증번호를 다시 받아 주세요.',
        ),
      );
    await pumpLoginWithReset(tester);
    await tapVisible(tester, find.text('비밀번호를 잊으셨나요?'));
    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await tapVisible(tester, find.byType(OutlinedButton));
    await tester.enterText(field('인증번호'), '654321');
    await tester.enterText(field('새 비밀번호'), 'newpassword123');
    await tester.enterText(field('새 비밀번호 확인'), 'newpassword123');
    await tapVisible(tester, find.widgetWithText(ElevatedButton, '비밀번호 다시 설정'));

    expect(find.byType(PasswordResetScreen), findsOneWidget);
    expect(find.text('이 인증번호는 더 쓸 수 없어요. 인증번호를 다시 받아 주세요.'), findsOneWidget);
    expect(fieldText(tester, '인증번호'), isEmpty);
  });

  testWidgets('새 비밀번호 칸에서 자판의 다음은 눈 아이콘을 건너뛰고 확인 칸으로 간다', (
    tester,
  ) async {
    await pumpLoginWithReset(tester);
    await tapVisible(tester, find.text('비밀번호를 잊으셨나요?'));
    await tapVisible(tester, field('새 비밀번호'));

    await tester.testTextInput.receiveAction(TextInputAction.next);
    await tester.pumpAndSettle();

    final confirmEditable = tester.widget<EditableText>(
      find.descendant(
        of: field('새 비밀번호 확인'),
        matching: find.byType(EditableText),
      ),
    );
    expect(confirmEditable.focusNode.hasFocus, isTrue);
  });

  testWidgets('새 비밀번호도 가입과 같은 규칙으로 먼저 거른다', (tester) async {
    await pumpLoginWithReset(tester);
    await tapVisible(tester, find.text('비밀번호를 잊으셨나요?'));
    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await tester.enterText(field('인증번호'), '123456');
    await tester.enterText(field('새 비밀번호'), 'short');
    await tester.enterText(field('새 비밀번호 확인'), 'short');
    await tapVisible(tester, find.widgetWithText(ElevatedButton, '비밀번호 다시 설정'));

    expect(find.text('비밀번호는 8자 이상 입력해 주세요'), findsOneWidget);
    expect(backend.requests, isEmpty);
  });
}
