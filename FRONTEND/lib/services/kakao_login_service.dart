import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';

/// 카카오 로그인이 취소가 아닌 이유로 끝나지 못했을 때 화면에 보일 문구를 담는다.
class KakaoLoginException implements Exception {
  const KakaoLoginException(this.cause);

  /// 카카오 SDK 가 던진 원래 예외입니다(기록용).
  final Object cause;

  String get userMessage => '카카오 로그인을 마치지 못했어요. 잠시 후 다시 시도해 주세요.';

  @override
  String toString() => 'KakaoLoginException: $cause';
}

/// 카카오 SDK 로그인을 감싸, 화면이 SDK 예외 대신 카카오 액세스 토큰만 다루게 한다.
///
/// 받은 토큰은 우리 서버의 `POST /auth/kakao`(로그인)나 `POST /auth/withdraw`(탈퇴 확인)에
/// 보낸다(`BACKEND/API_CONTRACT.md`). 사용자가 카카오 화면에서 취소하면 null 을 돌려주고,
/// 그때 화면은 서버를 부르지 않는다.
class KakaoLoginService {
  KakaoLoginService({
    Future<bool> Function()? isKakaoTalkInstalled,
    Future<OAuthToken> Function()? loginWithKakaoTalk,
    Future<OAuthToken> Function({List<Prompt>? prompts})? loginWithKakaoAccount,
    Future<void> Function()? logout,
    this.signOutTimeout = const Duration(seconds: 5),
  }) : _isKakaoTalkInstalled = isKakaoTalkInstalled ?? _sdkIsKakaoTalkInstalled,
       _loginWithKakaoTalk = loginWithKakaoTalk ?? _sdkLoginWithKakaoTalk,
       _loginWithKakaoAccount =
           loginWithKakaoAccount ?? _sdkLoginWithKakaoAccount,
       _logout = logout ?? _sdkLogout;

  final Future<bool> Function() _isKakaoTalkInstalled;
  final Future<OAuthToken> Function() _loginWithKakaoTalk;
  final Future<OAuthToken> Function({List<Prompt>? prompts})
  _loginWithKakaoAccount;
  final Future<void> Function() _logout;

  /// [signOut] 이 카카오 서버 응답을 기다리는 최대 시간입니다. SDK 요청에는 시간 제한이 없습니다.
  final Duration signOutTimeout;

  /// 카카오톡이 있으면 카카오톡으로, 없으면 카카오계정으로 로그인한다(카카오 문서의 기본 흐름).
  ///
  /// 카카오톡에서 취소하면 카카오계정으로 넘어가지 않는다. 취소가 아닌 이유로 카카오톡 로그인이
  /// 실패하면(카카오톡에 계정이 연결되지 않음 등) 카카오계정으로 다시 시도한다.
  Future<String?> signIn() async {
    if (await _isKakaoTalkInstalled()) {
      try {
        return (await _loginWithKakaoTalk()).accessToken;
      } catch (error) {
        if (_isCancellation(error)) return null;
        debugPrint('카카오톡 로그인에 실패해 카카오계정으로 다시 시도합니다: $error');
      }
    }

    return _loginWithAccount();
  }

  /// 탈퇴 확인용으로, 기존 로그인 여부와 상관없이 카카오계정 로그인 화면에서 다시 로그인하게 한다.
  ///
  /// `Prompt.login` 은 카카오계정 로그인에만 적용돼(카카오 문서) 카카오톡이 있어도 쓰지 않는다.
  /// 기기에 저장된 카카오 토큰을 그대로 보내면 사용자 입력 없이 탈퇴되므로 늘 새로 받는다
  /// (`docs/SCAN_API_CONTRACT.md` 2-3).
  Future<String?> reauthenticate() {
    return _loginWithAccount(prompts: const [Prompt.login]);
  }

  /// 카카오 계정의 로그아웃·탈퇴 뒤 기기에 저장된 카카오 토큰을 지운다(DECISIONS 183 ⑤).
  ///
  /// 앱은 저장된 카카오 토큰을 다시 쓰지 않지만 남겨 둘 이유도 없다. SDK 는 카카오 서버 요청이
  /// 실패해도 요청이 끝날 때 기기 토큰을 지우므로(`UserApi.logout` 의 finally) 실패는 기록만
  /// 하고, [signOutTimeout] 이 지나면 기다리지 않는다 — 그 뒤 요청이 끝나도 SDK 가 지운다.
  /// 브라우저의 카카오계정 로그인 상태는 이것으로 지워지지 않는다.
  Future<void> signOut() async {
    try {
      await _logout().timeout(signOutTimeout);
    } catch (error) {
      debugPrint('카카오 SDK 로그아웃을 마치지 못했습니다: $error');
    }
  }

  Future<String?> _loginWithAccount({List<Prompt>? prompts}) async {
    try {
      return (await _loginWithKakaoAccount(prompts: prompts)).accessToken;
    } catch (error) {
      if (_isCancellation(error)) return null;
      throw KakaoLoginException(error);
    }
  }

  /// 카카오톡·카카오계정 화면을 닫은 것(`CANCELED`)과 카카오계정 동의 화면에서 거부한 것
  /// (`access_denied`)을 취소로 본다.
  static bool _isCancellation(Object error) {
    return (error is PlatformException && error.code == 'CANCELED') ||
        (error is KakaoAuthException &&
            error.error == AuthErrorCause.accessDenied);
  }

  // SDK 기본값은 부를 때 UserApi.instance 를 만든다 — 화면 테스트처럼 KakaoSdk.init 없이
  // 이 서비스를 만들기만 하는 곳에서 SDK 초기화 전 객체를 건드리지 않게.
  static Future<bool> _sdkIsKakaoTalkInstalled() => isKakaoTalkInstalled();

  static Future<OAuthToken> _sdkLoginWithKakaoTalk() {
    return UserApi.instance.loginWithKakaoTalk();
  }

  static Future<OAuthToken> _sdkLoginWithKakaoAccount({List<Prompt>? prompts}) {
    return UserApi.instance.loginWithKakaoAccount(prompts: prompts);
  }

  static Future<void> _sdkLogout() async {
    await UserApi.instance.logout();
  }
}
