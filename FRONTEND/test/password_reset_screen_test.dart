import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/email_login_screen.dart';
import 'package:k_dpp/password_reset_screen.dart';
import 'package:k_dpp/services/auth_api_service.dart';
import 'package:k_dpp/widgets/app_banner.dart';
import 'package:k_dpp/widgets/number_keyboard_toolbar.dart';

import 'helpers/app_back_button_state.dart';
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
    // 이메일이 채워져 있어도 번호 칸은 [인증번호 받기]를 눌러야 나타납니다(DECISIONS 266).
    expect(field('인증번호'), findsNothing);
  });

  testWidgets('번호를 받기 전에 다시 설정하면 [인증번호 받기] 아래에서 막고, 누르면 시간 초과로 끝나도 칸이 남는다', (
    tester,
  ) async {
    await pumpLoginWithReset(tester);
    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await tapVisible(tester, find.text('비밀번호를 잊으셨나요?'));
    await tester.enterText(field('새 비밀번호'), 'newpassword123');
    await tester.enterText(field('새 비밀번호 확인'), 'newpassword123');
    await tapVisible(tester, find.widgetWithText(ElevatedButton, '비밀번호 다시 설정'));

    final error = find.text('인증번호를 받아 입력해 주세요');
    expect(error, findsOneWidget);
    expect(field('인증번호'), findsNothing);
    expect(backend.requests, isEmpty);

    final pendingCode = backend.hold('/auth/email-code');
    final requestButton = find.byType(OutlinedButton);
    await tester.ensureVisible(requestButton);
    await tester.pumpAndSettle();
    await tester.tap(requestButton);
    await tester.pump();

    expect(field('인증번호'), findsOneWidget);
    // 안내는 칸이 펼쳐지는 동안 같이 접히고, 다 펼치면 지워집니다.
    await tester.pump(const Duration(milliseconds: 300));
    expect(error, findsNothing);

    await tester.pump(const Duration(seconds: 15));
    await tester.pump();

    expectAppBanner(
      tester,
      '응답이 늦어지고 있어요. 네트워크를 확인한 뒤 다시 시도해 주세요.',
      AppBannerKind.failure,
    );
    expect(field('인증번호'), findsOneWidget);
    expect(find.text('인증번호 받기를 누르면 가입된 이메일로 6자리 숫자를 보내 드려요'), findsOneWidget);
    pendingCode.complete();
  });

  testWidgets('너무 빨리 다시 요청한 429 에도 번호 칸은 남고, 이메일을 고쳐도 숨지 않는다', (tester) async {
    backend.on(
      '/auth/email-code',
      serverErrorResponse(
        429,
        'EMAIL_CODE_RESEND_TOO_SOON',
        '인증번호는 42초 후 다시 요청할 수 있습니다.',
        extra: {'retry_after': 42},
      ),
    );
    await pumpLoginWithReset(tester);
    await tapVisible(tester, find.text('비밀번호를 잊으셨나요?'));
    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await tapVisible(tester, find.byType(OutlinedButton));

    expectAppBanner(tester, '인증번호는 42초 후에 다시 받을 수 있어요.', AppBannerKind.failure);
    expect(field('인증번호'), findsOneWidget);

    await tester.enterText(field('인증번호'), '123456');
    await tester.enterText(field('이메일'), 'other@example.com');
    await tester.pump();

    expect(field('인증번호'), findsOneWidget);
    expect(fieldText(tester, '인증번호'), isEmpty);
  });

  testWidgets('요청을 기다리는 동안 이메일을 고치면 늦게 온 요청 한도 429 대기를 새 이메일에 걸지 않는다', (
    tester,
  ) async {
    final pendingCode = backend.hold('/auth/email-code');
    backend.on(
      '/auth/email-code',
      serverErrorResponse(
        429,
        'TOO_MANY_ATTEMPTS',
        '인증번호 요청이 너무 많습니다. 10분 후 다시 시도해 주세요.',
        extra: {'retry_after': 600},
      ),
    );
    await pumpLoginWithReset(tester);
    await tapVisible(tester, find.text('비밀번호를 잊으셨나요?'));
    await tester.enterText(field('이메일'), 'honggildong@example.com');
    final requestButton = find.byType(OutlinedButton);
    await tester.ensureVisible(requestButton);
    await tester.pumpAndSettle();
    await tester.tap(requestButton);
    await tester.pump();

    await tester.enterText(field('이메일'), 'other@example.com');
    await tester.pump();
    pendingCode.complete();
    await tester.pumpAndSettle();

    final button = tester.widget<OutlinedButton>(requestButton);
    expect((button.child! as Text).data, '인증번호 받기');
    expect(button.onPressed, isNotNull);
  });

  testWidgets('하루 발송 상한 503 뒤 넣은 번호도 이메일을 고치면 비운다', (tester) async {
    backend.on(
      '/auth/email-code',
      serverErrorResponse(
        503,
        'EMAIL_SEND_UNAVAILABLE',
        '지금은 인증 메일을 보낼 수 없습니다. 나중에 다시 시도해 주세요.',
      ),
    );
    await pumpLoginWithReset(tester);
    await tapVisible(tester, find.text('비밀번호를 잊으셨나요?'));
    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await tapVisible(tester, find.byType(OutlinedButton));

    expectAppBanner(
      tester,
      '지금은 인증 메일을 보낼 수 없어요. 나중에 다시 시도해 주세요.',
      AppBannerKind.failure,
    );
    // 앞서 온 메일의 번호를 넣었더라도 그 이메일 것이라, 이메일을 고치면 비웁니다(DECISIONS 170).
    await tester.enterText(field('인증번호'), '123456');
    await tester.enterText(field('이메일'), 'other@example.com');
    await tester.pump();

    expect(field('인증번호'), findsOneWidget);
    expect(fieldText(tester, '인증번호'), isEmpty);
  });

  testWidgets('번호를 기다리는 동안 다시 설정을 눌러 번호 칸에 붙은 오류는 번호가 오면 지우고 남은 시간을 보인다', (
    tester,
  ) async {
    final pendingCode = backend.hold('/auth/email-code');
    backend.on('/auth/email-code', emailCodeSentResponse());
    await pumpLoginWithReset(tester);
    await tapVisible(tester, find.text('비밀번호를 잊으셨나요?'));
    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await tester.enterText(field('새 비밀번호'), 'newpassword123');
    await tester.enterText(field('새 비밀번호 확인'), 'newpassword123');
    final requestButton = find.byType(OutlinedButton);
    await tester.ensureVisible(requestButton);
    await tester.pumpAndSettle();
    await tester.tap(requestButton);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    // 기다리는 동안은 pumpAndSettle 을 부르지 않습니다(요청 시간 초과를 넘겨 버림).
    final submit = find.widgetWithText(ElevatedButton, '비밀번호 다시 설정');
    await tester.ensureVisible(submit);
    await tester.pump();
    await tester.tap(submit);
    await tester.pump();

    final error = find.text('인증번호를 받아 입력해 주세요');
    expect(error, findsOneWidget);
    expect(backend.bodiesFor('/auth/password-reset'), isEmpty);

    pendingCode.complete();
    await tester.pumpAndSettle();

    expect(error, findsNothing);
    expect(find.text('남은 시간 10:00'), findsOneWidget);
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

  // C25(DECISIONS 2026-10-14): 요청 중에 떠나면 서버 비밀번호는 바뀌었는데 안내가 없고, 로그인
  // 화면엔 옛 비밀번호가 남았다.
  testWidgets('재설정을 기다리는 동안은 "<"·뒤로가기로 떠날 수 없고, 끝나면 이메일을 넘겨 돌아간다', (
    tester,
  ) async {
    backend
      ..on('/auth/email-code', emailCodeSentResponse())
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
    await tester.enterText(field('인증번호'), '123456');
    await tester.enterText(field('새 비밀번호'), 'newpassword123');
    await tester.enterText(field('새 비밀번호 확인'), 'newpassword123');
    final pendingReset = backend.hold('/auth/password-reset');
    final submit = find.widgetWithText(ElevatedButton, '비밀번호 다시 설정');
    await tester.ensureVisible(submit);
    await tester.pumpAndSettle();
    await tester.tap(submit);
    await tester.pump();

    expect(backend.bodiesFor('/auth/password-reset'), hasLength(1));
    expect(isAppBackButtonEnabled(tester), isFalse);

    await tryToLeave(tester);

    expect(find.byType(PasswordResetScreen), findsOneWidget);

    pendingReset.complete();
    await tester.pumpAndSettle();

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

  testWidgets('iOS 에서 번호 칸 막대의 ∧ 는 이메일, ∨ 는 새 비밀번호로 옮긴다', (tester) async {
    backend.on('/auth/email-code', emailCodeSentResponse());
    await pumpLoginWithReset(tester);
    await tapVisible(tester, find.text('비밀번호를 잊으셨나요?'));
    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await tapVisible(tester, find.byType(OutlinedButton));

    Finder arrow(String label) => find.descendant(
      of: find.byType(NumberKeyboardToolbar),
      matching: find.byWidgetPredicate(
        (widget) => widget is Icon && widget.semanticLabel == label,
      ),
    );
    bool hasFocus(String label) => tester
        .widget<EditableText>(
          find.descendant(
            of: field(label),
            matching: find.byType(EditableText),
          ),
        )
        .focusNode
        .hasFocus;

    await tapVisible(tester, field('인증번호'));
    await tester.tap(arrow('이전 칸'));
    await tester.pumpAndSettle();
    expect(hasFocus('이메일'), isTrue);
    expect(find.byType(NumberKeyboardToolbar), findsNothing);

    await tapVisible(tester, field('인증번호'));
    await tester.tap(arrow('다음 칸'));
    await tester.pumpAndSettle();
    expect(hasFocus('새 비밀번호'), isTrue);
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('새 비밀번호도 가입과 같은 규칙으로 먼저 거른다', (tester) async {
    backend.on('/auth/email-code', emailCodeSentResponse());
    await pumpLoginWithReset(tester);
    await tapVisible(tester, find.text('비밀번호를 잊으셨나요?'));
    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await tapVisible(tester, find.byType(OutlinedButton));
    await tester.enterText(field('인증번호'), '123456');
    await tester.enterText(field('새 비밀번호'), 'short');
    await tester.enterText(field('새 비밀번호 확인'), 'short');
    await tapVisible(tester, find.widgetWithText(ElevatedButton, '비밀번호 다시 설정'));

    expect(find.text('비밀번호는 8자 이상 입력해 주세요'), findsOneWidget);
    expect(backend.bodiesFor('/auth/password-reset'), isEmpty);
  });
}
