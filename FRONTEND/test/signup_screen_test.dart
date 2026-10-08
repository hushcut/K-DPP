import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/email_login_screen.dart';
import 'package:k_dpp/services/auth_api_service.dart';
import 'package:k_dpp/signup_screen.dart';
import 'package:k_dpp/widgets/app_banner.dart';

import 'helpers/app_banner_expect.dart';
import 'helpers/fake_auth_backend.dart';

void main() {
  // 남은 시간을 셀 가짜 시계입니다. 테스트가 앞으로 돌립니다.
  late DateTime now;
  late FakeAuthBackend backend;

  setUp(() {
    now = DateTime(2026, 10, 7, 13);
    backend = FakeAuthBackend();
  });

  Finder field(String label) =>
      find.widgetWithText(TextFormField, label, skipOffstage: false);

  Finder requestButton() => find.byType(OutlinedButton);

  String requestButtonLabel(WidgetTester tester) {
    final button = tester.widget<OutlinedButton>(requestButton());
    return (button.child! as Text).data!;
  }

  bool isRequestButtonEnabled(WidgetTester tester) =>
      tester.widget<OutlinedButton>(requestButton()).onPressed != null;

  Future<void> pumpSignupScreen(WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        builder: AppBannerHost.builder,
        home: SignupScreen(
          authApiService: AuthApiService(client: backend.client),
          now: () => now,
        ),
        routes: {'/email-login': (_) => const EmailLoginScreen()},
      ),
    );
    await tester.pumpAndSettle();
  }

  Future<void> tapVisible(WidgetTester tester, Finder finder) async {
    await tester.ensureVisible(finder);
    await tester.pumpAndSettle();
    await tester.tap(finder);
    await tester.pumpAndSettle();
  }

  Future<void> requestCode(WidgetTester tester) async {
    await tapVisible(tester, requestButton());
  }

  Future<void> fillAccountFields(
    WidgetTester tester, {
    String password = 'password123',
    String? confirmPassword,
  }) async {
    await tester.enterText(field('닉네임'), '홍길동');
    await tester.enterText(field('비밀번호'), password);
    await tester.enterText(field('비밀번호 확인'), confirmPassword ?? password);
  }

  Future<void> submitSignupForm(WidgetTester tester) async {
    await tapVisible(tester, find.widgetWithText(ElevatedButton, '회원가입'));
  }

  /// 처음 화면의 번호 칸 안내이자, 받은 뒤 남은 시간이 보이는 자리입니다.
  Finder helperText(String text) => find.text(text, skipOffstage: false);

  testWidgets('비밀번호 앞뒤 공백은 가입 검증에서 거부된다', (tester) async {
    await pumpSignupScreen(tester);
    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await fillAccountFields(tester, password: 'pass1234 ');
    await submitSignupForm(tester);

    expect(find.text('비밀번호 앞뒤 공백은 사용할 수 없어요'), findsOneWidget);
    expect(backend.requests, isEmpty);
  });

  testWidgets('숨은 공백으로 어긋난 비밀번호 확인은 불일치로 표시된다', (tester) async {
    await pumpSignupScreen(tester);
    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await fillAccountFields(
      tester,
      password: 'pass1234 ',
      confirmPassword: 'pass1234',
    );
    await submitSignupForm(tester);

    expect(find.text('비밀번호가 일치하지 않습니다'), findsOneWidget);
  });

  testWidgets('번호 칸은 처음부터 보이고, 번호 없이 가입하면 번호를 받아 넣으라고 막는다', (tester) async {
    await pumpSignupScreen(tester);

    expect(field('인증번호'), findsOneWidget);
    expect(requestButtonLabel(tester), '인증번호 받기');
    expect(helperText('인증번호 받기를 누르면 메일로 6자리 숫자를 보내 드려요'), findsOneWidget);

    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await fillAccountFields(tester);
    await submitSignupForm(tester);

    expect(find.text('인증번호를 받아 입력해 주세요'), findsOneWidget);
    expect(backend.requests, isEmpty);
  });

  testWidgets('이메일이 올바르지 않으면 번호를 요청하지 않고 이메일 칸에 알린다', (tester) async {
    await pumpSignupScreen(tester);
    await tester.enterText(field('이메일'), 'not-an-email');
    await requestCode(tester);

    expect(find.text('올바른 이메일 형식을 입력해 주세요'), findsOneWidget);
    expect(backend.requests, isEmpty);
  });

  testWidgets('번호를 받으면 알리고, 다시 받기 대기와 남은 시간을 기기 시계로 센다', (tester) async {
    backend.on('/auth/email-code', emailCodeSentResponse());
    await pumpSignupScreen(tester);
    await tester.enterText(field('이메일'), ' HongGildong@Example.com ');
    await requestCode(tester);

    expect(backend.bodiesFor('/auth/email-code').single, {
      'email': 'HongGildong@Example.com',
      'purpose': 'signup',
    });
    expectAppBanner(
      tester,
      '인증번호를 보냈어요. 메일이 오지 않으면 주소를 확인해 주세요.',
      AppBannerKind.success,
    );
    expect(requestButtonLabel(tester), '인증번호 다시 받기 (60초 후)');
    expect(isRequestButtonEnabled(tester), isFalse);
    expect(helperText('남은 시간 10:00'), findsOneWidget);
    // 받은 번호를 바로 넣도록 번호 칸으로 옮깁니다.
    final codeEditable = tester.widget<EditableText>(
      find.descendant(of: field('인증번호'), matching: find.byType(EditableText)),
    );
    expect(codeEditable.focusNode.hasFocus, isTrue);

    now = now.add(const Duration(seconds: 1));
    await tester.pump(const Duration(seconds: 1));

    expect(requestButtonLabel(tester), '인증번호 다시 받기 (59초 후)');
    expect(helperText('남은 시간 9:59'), findsOneWidget);

    // 메일 앱에 다녀오는 동안 앱 타이머가 멈췄어도, 돌아와 처음 그릴 때 기기 시계로 맞춥니다.
    now = now.add(const Duration(minutes: 5));
    await tester.pump(const Duration(seconds: 1));

    expect(requestButtonLabel(tester), '인증번호 다시 받기');
    expect(isRequestButtonEnabled(tester), isTrue);
    expect(helperText('남은 시간 4:59'), findsOneWidget);
    expect(
      find.bySemanticsLabel('남은 시간 4분 59초', skipOffstage: false),
      findsOneWidget,
    );

    now = now.add(const Duration(minutes: 5));
    await tester.pump(const Duration(seconds: 1));

    expect(helperText('유효 시간이 지났어요. 인증번호를 다시 받아 주세요.'), findsOneWidget);
  });

  testWidgets('번호를 받은 뒤 이메일을 고치면 번호 칸과 시간을 비운다', (tester) async {
    backend.on('/auth/email-code', emailCodeSentResponse());
    await pumpSignupScreen(tester);
    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await requestCode(tester);
    await tester.enterText(field('인증번호'), '123456');

    // 대소문자·앞뒤 공백만 다르면 같은 이메일이라 그대로 둡니다.
    await tester.enterText(field('이메일'), ' HONGGILDONG@example.com');
    await tester.pump();
    expect(find.text('123456', skipOffstage: false), findsOneWidget);

    await tester.enterText(field('이메일'), 'other@example.com');
    await tester.pump();

    expect(find.text('123456', skipOffstage: false), findsNothing);
    expect(requestButtonLabel(tester), '인증번호 받기');
    expect(isRequestButtonEnabled(tester), isTrue);
    expect(helperText('인증번호 받기를 누르면 메일로 6자리 숫자를 보내 드려요'), findsOneWidget);
  });

  testWidgets('번호 칸은 숫자 6자리까지만 받는다', (tester) async {
    await pumpSignupScreen(tester);
    await tester.enterText(field('인증번호'), '12 34-5678');
    await tester.pump();

    expect(find.text('123456', skipOffstage: false), findsOneWidget);
  });

  testWidgets('번호와 함께 가입하면 로그인 화면으로 이메일을 넘기고 완료를 알린다', (tester) async {
    backend
      ..on('/auth/email-code', emailCodeSentResponse())
      ..on(
        '/auth/signup',
        jsonResponse({
          'status': 'success',
          'message': '회원가입이 완료되었습니다.',
          'user': {
            'id': 1,
            'email': 'honggildong@example.com',
            'nickname': '홍길동',
          },
        }, 200),
      );
    await pumpSignupScreen(tester);
    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await requestCode(tester);
    await tester.enterText(field('인증번호'), '123456');
    await fillAccountFields(tester);
    await submitSignupForm(tester);

    expect(backend.bodiesFor('/auth/signup').single, {
      'nickname': '홍길동',
      'email': 'honggildong@example.com',
      'password': 'password123',
      'code': '123456',
    });
    expect(find.byType(EmailLoginScreen), findsOneWidget);
    expectAppBanner(tester, '회원가입이 완료됐어요. 로그인해 주세요.', AppBannerKind.success);
  });

  testWidgets('틀린 번호는 배너 대신 번호 칸에 남은 기회를 보이고, 번호를 고치면 지운다', (tester) async {
    backend
      ..on('/auth/email-code', emailCodeSentResponse())
      ..on(
        '/auth/signup',
        serverErrorResponse(
          400,
          'VERIFICATION_CODE_INVALID',
          '인증번호가 올바르지 않습니다. 4번 더 입력할 수 있습니다.',
          extra: {'remaining_attempts': 4},
        ),
      );
    await pumpSignupScreen(tester);
    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await requestCode(tester);
    // 보냄 배너가 사라진 뒤라야 이번 오류가 배너로 오지 않았음을 볼 수 있습니다.
    await tester.pump(const Duration(seconds: 10));
    await tester.pumpAndSettle();
    await tester.enterText(field('인증번호'), '111111');
    await fillAccountFields(tester);
    await submitSignupForm(tester);

    const message = '인증번호가 맞지 않아요. 4번 더 입력할 수 있어요.';
    expect(find.text(message), findsOneWidget);
    expect(find.byType(AppBannerView), findsNothing);
    expect(find.text('111111', skipOffstage: false), findsOneWidget);

    // 같은 번호로 다시 누르면 서버에 보내지 않고 막습니다.
    await submitSignupForm(tester);
    expect(backend.bodiesFor('/auth/signup'), hasLength(1));

    await tester.enterText(field('인증번호'), '11111');
    // 오류 문장은 사라지는 동안 잠깐 남아 있어 애니메이션이 끝날 때까지 기다립니다.
    await tester.pumpAndSettle();
    expect(find.text(message), findsNothing);
  });

  testWidgets('다시 받아야 하는 번호는 번호 칸을 비우고 다시 받으라고 보인다', (tester) async {
    backend
      ..on('/auth/email-code', emailCodeSentResponse())
      ..on(
        '/auth/signup',
        serverErrorResponse(
          400,
          'VERIFICATION_CODE_RESEND_REQUIRED',
          '인증번호가 없거나 만료되었습니다. 인증번호를 다시 받아 주세요.',
        ),
      );
    await pumpSignupScreen(tester);
    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await requestCode(tester);
    await tester.enterText(field('인증번호'), '111111');
    await fillAccountFields(tester);
    await submitSignupForm(tester);

    expect(
      find.text('이 인증번호는 더 쓸 수 없어요. 인증번호를 다시 받아 주세요.'),
      findsOneWidget,
    );
    expect(find.text('111111', skipOffstage: false), findsNothing);
    expect(find.textContaining('남은 시간', skipOffstage: false), findsNothing);
  });

  testWidgets('번호와 무관한 가입 거절(IP 한도 429)은 배너로 알린다', (tester) async {
    backend
      ..on('/auth/email-code', emailCodeSentResponse())
      ..on(
        '/auth/signup',
        serverErrorResponse(
          429,
          'TOO_MANY_ATTEMPTS',
          '가입 시도가 너무 많습니다. 12분 후 다시 시도해 주세요.',
        ),
      );
    await pumpSignupScreen(tester);
    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await requestCode(tester);
    await tester.enterText(field('인증번호'), '123456');
    await fillAccountFields(tester);
    await submitSignupForm(tester);

    expectAppBanner(
      tester,
      '가입 시도가 너무 많습니다. 12분 후 다시 시도해 주세요.',
      AppBannerKind.failure,
    );
    expect(find.text('123456', skipOffstage: false), findsOneWidget);
  });

  testWidgets('너무 빨리 다시 요청한 429 는 배너로 알리고 그만큼 다시 받기를 막는다', (tester) async {
    backend.on(
      '/auth/email-code',
      serverErrorResponse(
        429,
        'EMAIL_CODE_RESEND_TOO_SOON',
        '인증번호는 42초 후 다시 요청할 수 있습니다.',
        extra: {'retry_after': 42},
      ),
    );
    await pumpSignupScreen(tester);
    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await requestCode(tester);

    expectAppBanner(
      tester,
      '인증번호는 42초 후에 다시 받을 수 있어요.',
      AppBannerKind.failure,
    );
    expect(requestButtonLabel(tester), '인증번호 받기 (42초 후)');
    expect(isRequestButtonEnabled(tester), isFalse);

    // 그 대기는 그 이메일 것이라, 다른 이메일이면 바로 받을 수 있습니다.
    await tester.enterText(field('이메일'), 'other@example.com');
    await tester.pump();
    expect(isRequestButtonEnabled(tester), isTrue);
  });

  testWidgets('요청 한도에 닿은 긴 대기는 시간 단위로 보인다', (tester) async {
    backend.on(
      '/auth/email-code',
      emailCodeSentResponse(resendAfter: 3 * 3600),
    );
    await pumpSignupScreen(tester);
    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await requestCode(tester);

    expect(requestButtonLabel(tester), '인증번호 다시 받기 (3시간 후)');
  });

  testWidgets('하루 발송 상한 503 은 메일을 보낼 수 없다고 배너로 알린다', (tester) async {
    backend.on(
      '/auth/email-code',
      serverErrorResponse(
        503,
        'EMAIL_SEND_UNAVAILABLE',
        '지금은 인증 메일을 보낼 수 없습니다. 나중에 다시 시도해 주세요.',
      ),
    );
    await pumpSignupScreen(tester);
    await tester.enterText(field('이메일'), 'honggildong@example.com');
    await requestCode(tester);

    expectAppBanner(
      tester,
      '지금은 인증 메일을 보낼 수 없어요. 나중에 다시 시도해 주세요.',
      AppBannerKind.failure,
    );
    expect(isRequestButtonEnabled(tester), isTrue);
  });

  testWidgets(
    'iOS 에서 번호 칸 오류는 폼 검증처럼 1초 뒤 낭독기에 알린다',
    (tester) async {
      final announcements = <String>[];
      tester.binding.defaultBinaryMessenger.setMockDecodedMessageHandler<
        dynamic
      >(SystemChannels.accessibility, (message) async {
        final map = message as Map<dynamic, dynamic>;
        if (map['type'] == 'announce') {
          announcements.add((map['data'] as Map)['message'] as String);
        }
        return null;
      });
      addTearDown(
        () => tester.binding.defaultBinaryMessenger
            .setMockDecodedMessageHandler<dynamic>(
              SystemChannels.accessibility,
              null,
            ),
      );

      backend
        ..on('/auth/email-code', emailCodeSentResponse())
        ..on(
          '/auth/signup',
          serverErrorResponse(
            400,
            'VERIFICATION_CODE_INVALID',
            '인증번호가 올바르지 않습니다. 2번 더 입력할 수 있습니다.',
            extra: {'remaining_attempts': 2},
          ),
        );
      await pumpSignupScreen(tester);
      await tester.enterText(field('이메일'), 'honggildong@example.com');
      await requestCode(tester);
      await tester.enterText(field('인증번호'), '111111');
      await fillAccountFields(tester);
      await submitSignupForm(tester);

      await tester.pump(const Duration(seconds: 1));

      expect(announcements, contains('인증번호가 맞지 않아요. 2번 더 입력할 수 있어요.'));
    },
    variant: TargetPlatformVariant.only(TargetPlatform.iOS),
  );

  testWidgets('iOS 에서 번호 칸에 포커스가 있으면 키패드 위에 [다음]을 띄워 닉네임으로 옮긴다', (
    tester,
  ) async {
    await pumpSignupScreen(tester);
    await tester.tap(field('인증번호'));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(OutlinedButton, '다음'));
    await tester.pumpAndSettle();

    final nicknameEditable = tester.widget<EditableText>(
      find.descendant(of: field('닉네임'), matching: find.byType(EditableText)),
    );
    expect(nicknameEditable.focusNode.hasFocus, isTrue);
    expect(find.widgetWithText(OutlinedButton, '다음'), findsNothing);
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('비밀번호 칸에서 자판의 다음은 눈 아이콘을 건너뛰고 비밀번호 확인 칸으로 간다', (
    tester,
  ) async {
    await pumpSignupScreen(tester);
    await tapVisible(tester, field('비밀번호'));

    await tester.testTextInput.receiveAction(TextInputAction.next);
    await tester.pumpAndSettle();

    final confirmEditable = tester.widget<EditableText>(
      find.descendant(
        of: field('비밀번호 확인'),
        matching: find.byType(EditableText),
      ),
    );
    expect(confirmEditable.focusNode.hasFocus, isTrue);
  });

  testWidgets('이메일 로그인에서 온 회원가입의 로그인 링크는 화면을 쌓지 않고 되돌아간다', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        builder: AppBannerHost.builder,
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

  testWidgets('자판 인셋이 앱바 아래를 다 덮어 본문 높이가 0 이 돼도 레이아웃 예외가 나지 않는다', (
    tester,
  ) async {
    // iPhone 18 Pro Max(440×956pt, 3배) 크기. 이메일 로그인 화면과 같은 구조다.
    tester.view.physicalSize = const Size(440 * 3, 956 * 3);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);

    await pumpSignupScreen(tester);

    tester.view.viewInsets = const FakeViewPadding(bottom: 956 * 3);
    await tester.pump();

    expect(tester.takeException(), isNull);

    tester.view.viewInsets = const FakeViewPadding(bottom: 336 * 3);
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.byType(TextFormField, skipOffstage: false), findsNWidgets(5));
  });
}
