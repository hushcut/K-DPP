import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/email_login_screen.dart';
import 'package:k_dpp/signup_screen.dart';

void main() {
  Future<void> pumpSignupScreen(WidgetTester tester) async {
    await tester.pumpWidget(const MaterialApp(home: SignupScreen()));
    await tester.pumpAndSettle();
  }

  Future<void> fillSignupForm(
    WidgetTester tester, {
    required String password,
    required String confirmPassword,
  }) async {
    final fields = find.byType(TextFormField);
    await tester.enterText(fields.at(0), '홍길동');
    await tester.enterText(fields.at(1), 'honggildong@example.com');
    await tester.enterText(fields.at(2), password);
    await tester.enterText(fields.at(3), confirmPassword);
  }

  Future<void> submitSignupForm(WidgetTester tester) async {
    final submitButton = find.widgetWithText(ElevatedButton, '회원가입');
    await tester.ensureVisible(submitButton);
    await tester.pumpAndSettle();
    await tester.tap(submitButton);
    await tester.pumpAndSettle();
  }

  testWidgets('비밀번호 앞뒤 공백은 가입 검증에서 거부된다', (tester) async {
    await pumpSignupScreen(tester);
    await fillSignupForm(
      tester,
      password: 'pass1234 ',
      confirmPassword: 'pass1234 ',
    );
    await submitSignupForm(tester);

    expect(find.text('비밀번호 앞뒤 공백은 사용할 수 없어요'), findsOneWidget);
  });

  testWidgets('숨은 공백으로 어긋난 비밀번호 확인은 불일치로 표시된다', (tester) async {
    await pumpSignupScreen(tester);
    await fillSignupForm(
      tester,
      password: 'pass1234 ',
      confirmPassword: 'pass1234',
    );
    await submitSignupForm(tester);

    expect(find.text('비밀번호가 일치하지 않습니다'), findsOneWidget);
  });

  testWidgets('이메일 로그인에서 온 회원가입의 로그인 링크는 화면을 쌓지 않고 되돌아간다', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: const EmailLoginScreen(),
        routes: {
          '/signup': (_) => const SignupScreen(),
          '/email-login': (_) => const EmailLoginScreen(),
        },
      ),
    );
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text('계정이 없으신가요? 회원가입'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('계정이 없으신가요? 회원가입'));
    await tester.pumpAndSettle();

    expect(find.byType(SignupScreen), findsOneWidget);

    await tester.ensureVisible(find.text('이미 계정이 있으신가요? 로그인'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('이미 계정이 있으신가요? 로그인'));
    await tester.pumpAndSettle();

    // 이메일 로그인 화면이 한 장만 남아야 중복 스택이 없는 것입니다.
    expect(find.byType(EmailLoginScreen, skipOffstage: false), findsOneWidget);
    expect(find.byType(SignupScreen, skipOffstage: false), findsNothing);
  });
}
