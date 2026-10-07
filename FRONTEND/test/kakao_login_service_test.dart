import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/services/kakao_login_service.dart';
import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';

OAuthToken _token(String accessToken) {
  return OAuthToken(
    accessToken,
    DateTime.now().add(const Duration(hours: 12)),
    'refresh-token',
    DateTime.now().add(const Duration(days: 60)),
    const ['profile_nickname'],
  );
}

PlatformException _cancelled() {
  return PlatformException(code: 'CANCELED', message: 'User canceled login.');
}

/// 카카오 SDK 호출을 기록하는 대역입니다.
class _FakeKakaoSdk {
  _FakeKakaoSdk({
    this.talkInstalled = true,
    this.talkResult,
    this.talkError,
    this.accountResult,
    this.accountError,
    this.logoutError,
    this.logoutCompleter,
  });

  final bool talkInstalled;
  final OAuthToken? talkResult;
  final Object? talkError;
  final OAuthToken? accountResult;
  final Object? accountError;
  final Object? logoutError;
  final Completer<void>? logoutCompleter;

  final calls = <String>[];
  List<Prompt>? lastPrompts;

  KakaoLoginService service({
    Duration signOutTimeout = const Duration(seconds: 5),
  }) {
    return KakaoLoginService(
      isKakaoTalkInstalled: () async => talkInstalled,
      loginWithKakaoTalk: () async {
        calls.add('talk');
        if (talkError case final error?) throw error;
        return talkResult!;
      },
      loginWithKakaoAccount: ({prompts}) async {
        calls.add('account');
        lastPrompts = prompts;
        if (accountError case final error?) throw error;
        return accountResult!;
      },
      logout: () async {
        calls.add('logout');
        if (logoutError case final error?) throw error;
        await logoutCompleter?.future;
      },
      signOutTimeout: signOutTimeout,
    );
  }
}

void main() {
  group('signIn', () {
    test('카카오톡이 있으면 카카오톡으로 로그인해 토큰을 돌려준다', () async {
      final sdk = _FakeKakaoSdk(talkResult: _token('talk-token'));

      final token = await sdk.service().signIn();

      expect(token, 'talk-token');
      expect(sdk.calls, ['talk']);
    });

    test('카카오톡이 없으면 카카오계정으로 로그인한다', () async {
      final sdk = _FakeKakaoSdk(
        talkInstalled: false,
        accountResult: _token('account-token'),
      );

      final token = await sdk.service().signIn();

      expect(token, 'account-token');
      expect(sdk.calls, ['account']);
      expect(sdk.lastPrompts, isNull);
    });

    test('카카오톡 화면에서 취소하면 카카오계정으로 넘어가지 않고 null 을 돌려준다', () async {
      final sdk = _FakeKakaoSdk(
        talkError: _cancelled(),
        accountResult: _token('account-token'),
      );

      final token = await sdk.service().signIn();

      expect(token, isNull);
      expect(sdk.calls, ['talk']);
    });

    test('카카오톡 로그인이 취소가 아닌 이유로 실패하면 카카오계정으로 다시 시도한다', () async {
      // 카카오톡에 카카오계정이 연결되지 않은 경우 등(카카오 문서의 기본 흐름).
      final sdk = _FakeKakaoSdk(
        talkError: PlatformException(code: 'NotSupportError'),
        accountResult: _token('account-token'),
      );

      final token = await sdk.service().signIn();

      expect(token, 'account-token');
      expect(sdk.calls, ['talk', 'account']);
    });

    test('카카오계정 화면에서 닫거나 동의를 거부하면 null 을 돌려준다', () async {
      for (final error in <Object>[
        _cancelled(),
        KakaoAuthException(AuthErrorCause.accessDenied, 'User denied access'),
      ]) {
        final sdk = _FakeKakaoSdk(talkInstalled: false, accountError: error);

        expect(await sdk.service().signIn(), isNull, reason: '$error');
      }
    });

    test('그 밖의 실패는 화면에 보일 문구를 담은 예외로 바꾼다', () async {
      final sdk = _FakeKakaoSdk(
        talkInstalled: false,
        accountError: PlatformException(code: 'NetworkError'),
      );

      await expectLater(
        sdk.service().signIn(),
        throwsA(
          isA<KakaoLoginException>().having(
            (error) => error.userMessage,
            'userMessage',
            '카카오 로그인을 마치지 못했어요. 잠시 후 다시 시도해 주세요.',
          ),
        ),
      );
    });
  });

  group('reauthenticate', () {
    test('카카오톡이 있어도 카카오계정 로그인 화면에서 다시 로그인하게 한다', () async {
      // Prompt.login 은 카카오계정 로그인에만 적용됩니다(카카오 문서). 카카오톡 로그인은
      // 사용자 입력 없이 끝날 수 있어 탈퇴 확인에 쓰지 않습니다(SCAN_API_CONTRACT 2-3).
      final sdk = _FakeKakaoSdk(accountResult: _token('fresh-token'));

      final token = await sdk.service().reauthenticate();

      expect(token, 'fresh-token');
      expect(sdk.calls, ['account']);
      expect(sdk.lastPrompts, [Prompt.login]);
    });

    test('다시 로그인 화면에서 취소하면 null 을 돌려준다', () async {
      final sdk = _FakeKakaoSdk(accountError: _cancelled());

      expect(await sdk.service().reauthenticate(), isNull);
    });
  });

  group('signOut', () {
    test('기기에 저장된 카카오 토큰을 지우도록 SDK 로그아웃을 부른다', () async {
      final sdk = _FakeKakaoSdk();

      await sdk.service().signOut();

      expect(sdk.calls, ['logout']);
    });

    test('카카오 서버 요청이 실패해도 예외를 밖으로 내지 않는다', () async {
      // SDK 는 요청이 실패해도 끝날 때 기기 토큰을 지운다(UserApi.logout 의 finally).
      // 이미 연결이 끊긴 탈퇴 뒤에는 늘 실패한다.
      final sdk = _FakeKakaoSdk(
        logoutError: KakaoApiException(
          ApiErrorCause.invalidToken,
          'this access token does not exist',
        ),
      );

      await sdk.service().signOut();

      expect(sdk.calls, ['logout']);
    });

    test('카카오가 답하지 않아도 정한 시간만 기다리고 끝난다', () async {
      // SDK 요청에는 시간 제한이 없어, 로그아웃 화면이 카카오를 기다리며 멈추지 않게 한다.
      final sdk = _FakeKakaoSdk(logoutCompleter: Completer<void>());
      final stopwatch = Stopwatch()..start();

      await sdk
          .service(signOutTimeout: const Duration(milliseconds: 50))
          .signOut();

      expect(stopwatch.elapsed, lessThan(const Duration(seconds: 2)));
      expect(sdk.calls, ['logout']);
    });
  });
}
