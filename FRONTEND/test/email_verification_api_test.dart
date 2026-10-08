import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/services/auth_api_service.dart';

import 'helpers/fake_auth_backend.dart';

// 이메일 인증·비밀번호 찾기 계약(jw/email-verification 의 BACKEND/API_CONTRACT.md
// 'POST /auth/email-code'·'POST /auth/signup'·'POST /auth/password-reset')을 앱 쪽에서 지킵니다.
void main() {
  group('POST /auth/email-code', () {
    test('이메일 앞뒤 공백을 지우고 용도와 함께 보내며, 남은 시간을 읽는다', () async {
      final backend = FakeAuthBackend()
        ..on(
          '/auth/email-code',
          emailCodeSentResponse(expiresIn: 600, resendAfter: 60),
        );
      final service = AuthApiService(client: backend.client);

      final result = await service.requestEmailCode(
        email: ' honggildong@example.com ',
        purpose: EmailCodePurpose.signup,
      );

      expect(backend.requests.single.method, 'POST');
      expect(
        backend.requests.single.url,
        Uri.parse('http://10.0.2.2:8000/auth/email-code'),
      );
      expect(backend.bodiesFor('/auth/email-code').single, {
        'email': 'honggildong@example.com',
        'purpose': 'signup',
      });
      expect(result.expiresInSeconds, 600);
      expect(result.resendAfterSeconds, 60);
    });

    test('비밀번호 찾기 용도는 password_reset 으로 보내고, 한도에 닿은 긴 대기도 그대로 읽는다', () async {
      final backend = FakeAuthBackend()
        ..on('/auth/email-code', emailCodeSentResponse(resendAfter: 3540));
      final service = AuthApiService(client: backend.client);

      final result = await service.requestEmailCode(
        email: 'honggildong@example.com',
        purpose: EmailCodePurpose.passwordReset,
      );

      expect(
        backend.bodiesFor('/auth/email-code').single['purpose'],
        'password_reset',
      );
      expect(result.resendAfterSeconds, 3540);
    });

    test('시간 값이 빠진 성공 응답은 계약 기본값으로 받는다(번호가 이미 간 뒤라 오류로 보이지 않게)', () async {
      final backend = FakeAuthBackend()
        ..on('/auth/email-code', jsonResponse({'status': 'success'}, 200));
      final service = AuthApiService(client: backend.client);

      final result = await service.requestEmailCode(
        email: 'honggildong@example.com',
        purpose: EmailCodePurpose.signup,
      );

      expect(result.expiresInSeconds, 600);
      expect(result.resendAfterSeconds, 60);
    });

    test('60초 안에 다시 요청한 429 는 기다릴 초를 담고 앱 문구로 알린다', () async {
      final backend = FakeAuthBackend()
        ..on(
          '/auth/email-code',
          serverErrorResponse(
            429,
            'EMAIL_CODE_RESEND_TOO_SOON',
            '인증번호는 42초 후 다시 요청할 수 있습니다.',
            extra: {'retry_after': 42},
          ),
        );
      final service = AuthApiService(client: backend.client);

      await expectLater(
        service.requestEmailCode(
          email: 'honggildong@example.com',
          purpose: EmailCodePurpose.signup,
        ),
        throwsA(
          isA<AuthApiException>()
              .having((e) => e.statusCode, 'statusCode', 429)
              .having(
                (e) => e.errorCode,
                'errorCode',
                'EMAIL_CODE_RESEND_TOO_SOON',
              )
              .having((e) => e.retryAfterSeconds, 'retryAfterSeconds', 42)
              .having(
                (e) => e.userMessage,
                'userMessage',
                '인증번호는 42초 후에 다시 받을 수 있어요.',
              ),
        ),
      );
    });

    test('요청 한도 429 는 서버의 대기 문구를 그대로 쓰고 기다릴 초도 담는다', () async {
      final backend = FakeAuthBackend()
        ..on(
          '/auth/email-code',
          serverErrorResponse(
            429,
            'TOO_MANY_ATTEMPTS',
            '인증번호 요청이 너무 많습니다. 50분 후 다시 시도해 주세요.',
            extra: {'retry_after': 2990},
          ),
        );
      final service = AuthApiService(client: backend.client);

      await expectLater(
        service.requestEmailCode(
          email: 'honggildong@example.com',
          purpose: EmailCodePurpose.signup,
        ),
        throwsA(
          isA<AuthApiException>()
              .having((e) => e.errorCode, 'errorCode', 'TOO_MANY_ATTEMPTS')
              .having((e) => e.retryAfterSeconds, 'retryAfterSeconds', 2990)
              .having(
                (e) => e.userMessage,
                'userMessage',
                '인증번호 요청이 너무 많습니다. 50분 후 다시 시도해 주세요.',
              ),
        ),
      );
    });

    test('하루 발송 상한 503 은 서버 고장 안내가 아니라 메일을 보낼 수 없다고 알린다', () async {
      final backend = FakeAuthBackend()
        ..on(
          '/auth/email-code',
          serverErrorResponse(
            503,
            'EMAIL_SEND_UNAVAILABLE',
            '지금은 인증 메일을 보낼 수 없습니다. 나중에 다시 시도해 주세요.',
          ),
        );
      final service = AuthApiService(client: backend.client);

      await expectLater(
        service.requestEmailCode(
          email: 'honggildong@example.com',
          purpose: EmailCodePurpose.signup,
        ),
        throwsA(
          isA<AuthApiException>()
              .having((e) => e.type, 'type', AuthApiErrorType.server)
              .having(
                (e) => e.userMessage,
                'userMessage',
                '지금은 인증 메일을 보낼 수 없어요. 나중에 다시 시도해 주세요.',
              ),
        ),
      );
    });
  });

  group('POST /auth/password-reset', () {
    test('이메일·번호·새 비밀번호를 한 번에 보낸다(비밀번호는 다듬지 않음)', () async {
      final backend = FakeAuthBackend()
        ..on(
          '/auth/password-reset',
          jsonResponse({
            'status': 'success',
            'message': '비밀번호를 다시 설정했습니다. 새 비밀번호로 로그인해 주세요.',
          }, 200),
        );
      final service = AuthApiService(client: backend.client);

      await service.resetPassword(
        email: ' honggildong@example.com ',
        code: ' 123456 ',
        newPassword: 'newpassword123',
      );

      expect(
        backend.requests.single.url,
        Uri.parse('http://10.0.2.2:8000/auth/password-reset'),
      );
      expect(backend.bodiesFor('/auth/password-reset').single, {
        'email': 'honggildong@example.com',
        'code': '123456',
        'new_password': 'newpassword123',
      });
    });
  });

  group('인증번호 오류 응답', () {
    test('틀린 번호는 남은 기회를 담아 번호 칸 오류로 분류된다', () {
      final error = AuthApiException.fromStatusCode(
        statusCode: 400,
        responseBody: serverErrorResponse(
          400,
          'VERIFICATION_CODE_INVALID',
          '인증번호가 올바르지 않습니다. 3번 더 입력할 수 있습니다.',
          extra: {'remaining_attempts': 3},
        ).body,
      );

      expect(error.type, AuthApiErrorType.badRequest);
      expect(error.errorCode, 'VERIFICATION_CODE_INVALID');
      expect(error.remainingAttempts, 3);
      expect(error.isVerificationCodeError, isTrue);
      expect(error.userMessage, '인증번호가 맞지 않아요. 3번 더 입력할 수 있어요.');
    });

    test('다시 받아야 하는 번호도 번호 칸 오류이고, 다시 받으라고 알린다', () {
      final error = AuthApiException.fromStatusCode(
        statusCode: 400,
        responseBody: serverErrorResponse(
          400,
          'VERIFICATION_CODE_RESEND_REQUIRED',
          '인증번호가 없거나 만료되었습니다. 인증번호를 다시 받아 주세요.',
        ).body,
      );

      expect(error.isVerificationCodeError, isTrue);
      expect(error.userMessage, '이 인증번호는 더 쓸 수 없어요. 인증번호를 다시 받아 주세요.');
    });

    test('번호 형식 400(문자열 detail)은 번호 칸 오류가 아니고 서버 문장을 그대로 쓴다', () {
      final error = AuthApiException.fromStatusCode(
        statusCode: 400,
        responseBody: jsonResponse({
          'status': 'error',
          'error_code': 'BAD_REQUEST',
          'message': '인증번호 6자리를 입력해 주세요.',
          'detail': '인증번호 6자리를 입력해 주세요.',
        }, 400).body,
      );

      expect(error.errorCode, 'BAD_REQUEST');
      expect(error.isVerificationCodeError, isFalse);
      expect(error.retryAfterSeconds, isNull);
      expect(error.userMessage, '인증번호 6자리를 입력해 주세요.');
    });
  });

  test('기다릴 시간은 60초까지 초, 1시간 미만은 분, 그 이상은 시간으로 올려 쓴다', () {
    expect(formatAuthWait(0), '1초');
    expect(formatAuthWait(42), '42초');
    expect(formatAuthWait(60), '60초');
    expect(formatAuthWait(61), '2분');
    expect(formatAuthWait(3540), '59분');
    expect(formatAuthWait(3541), '1시간');
    expect(formatAuthWait(3601), '2시간');
    expect(formatAuthWait(86400), '24시간');
  });
}
