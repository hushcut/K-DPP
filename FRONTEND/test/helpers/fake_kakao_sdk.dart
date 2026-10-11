import 'dart:async';

import 'package:flutter/services.dart';
import 'package:k_dpp/services/kakao_login_service.dart';
import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';

/// 화면 테스트가 쓰는 카카오 SDK 대역입니다.
///
/// 카카오톡이 없는 기기(시뮬레이터)처럼 늘 카카오계정으로 로그인합니다. 다음 로그인의 결과는
/// [nextAccountLogin] 으로 정합니다 — 토큰 문자열, 던질 오류, 또는 테스트가 나중에 끝낼
/// `Completer<String>`(진행 중 상태를 보려고).
class FakeKakaoSdk {
  Object nextAccountLogin = 'kakao-access-token';

  /// 카카오계정 로그인이 불릴 때마다 받은 `prompts` 를 남깁니다(재인증은 `[Prompt.login]`).
  final accountLoginPrompts = <List<Prompt>?>[];

  /// SDK 로그아웃(`UserApi.instance.logout`)을 부른 횟수입니다.
  int logoutCount = 0;

  KakaoLoginService service() {
    return KakaoLoginService(
      isKakaoTalkInstalled: () async => false,
      loginWithKakaoTalk: () => throw StateError('카카오톡이 없는 기기입니다.'),
      loginWithKakaoAccount: ({prompts}) async {
        accountLoginPrompts.add(prompts);
        final next = nextAccountLogin;
        if (next is Completer<String>) return _token(await next.future);
        if (next is String) return _token(next);
        throw next;
      },
      logout: () async {
        logoutCount++;
      },
    );
  }

  /// 카카오 화면을 닫았을 때 SDK 가 던지는 예외입니다.
  static PlatformException cancelled() {
    return PlatformException(code: 'CANCELED', message: 'User canceled login.');
  }

  static OAuthToken _token(String accessToken) {
    return OAuthToken(
      accessToken,
      DateTime.now().add(const Duration(hours: 12)),
      'refresh-token',
      DateTime.now().add(const Duration(days: 60)),
      const ['profile_nickname'],
    );
  }
}
