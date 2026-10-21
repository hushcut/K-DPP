import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../closet_provider.dart';
import '../widgets/app_banner.dart';

/// 만료된 로그인 세션을 정리하고 사용자를 로그인 화면으로 돌려보내는 공통 처리기다.
class SessionExpiryHandler {
  const SessionExpiryHandler._();

  static const String defaultMessage = '로그인이 만료됐어요. 다시 로그인해 주세요.';

  // 저장된 로그인 정보를 다 지우지 못했을 때 알리는 문장입니다.
  static const String _cleanupFailedNotice = '일부 로그인 정보는 지우지 못했어요.';
  static const String _signInAgain = '다시 로그인해 주세요.';

  /// 로컬 사용자 상태를 로그아웃한 뒤 탐색 스택을 초기화하고 안내 메시지를 표시한다.
  ///
  /// 사용자가 요청한 작업이 만료 때문에 이뤄지지 않았다면 [kind]로 실패를 넘긴다.
  static Future<void> handle(
    BuildContext context, {
    String message = defaultMessage,
    AppBannerKind kind = AppBannerKind.info,
  }) async {
    final provider = context.read<ClosetProvider>();
    final navigator = Navigator.of(context);
    final banner = AppBanner.of(context);

    // 저장소 정리가 실패해도 화면 이동과 안내는 반드시 수행합니다.
    // logout()은 메모리 상태를 먼저 비우므로, 여기서 예외가 그대로 올라가면
    // 사용자는 옷장만 사라진 채 로그인된 듯한 화면에 갇힙니다.
    var storageCleanupFailed = false;

    try {
      await provider.logout();
    } catch (error, stackTrace) {
      storageCleanupFailed = true;
      debugPrint('세션 만료 처리 중 저장 정보 정리에 실패했습니다: $error');
      debugPrintStack(stackTrace: stackTrace);
    }

    if (!context.mounted) return;

    navigator.pushNamedAndRemoveUntil('/login', (route) => false);
    // 배너는 Navigator 위에 있어 로그인 화면으로 넘어가도 남고, 앞 알림은 바로 바뀐다.
    // 만료는 사용자가 요청하지 않은 상태 변화라 기본은 안내, 정리까지 못 했으면 실패다.
    banner.show(
      storageCleanupFailed ? _withCleanupFailure(message) : message,
      kind: storageCleanupFailed ? AppBannerKind.failure : kind,
    );
  }

  /// [message] 에 정리 실패를 더합니다. 다시 로그인하라는 끝 문장은 로그인 화면이 대신하므로
  /// 그 자리를 바꿔 문장이 셋으로 늘지 않게 하고, 그 밖의 안내(의류는 기기에 저장 등)는
  /// 남긴 채 뒤에 붙입니다(DECISIONS 98).
  static String _withCleanupFailure(String message) {
    final trimmed = message.trimRight();

    if (trimmed.endsWith(_signInAgain)) {
      final head = trimmed.substring(0, trimmed.length - _signInAgain.length);
      return '$head$_cleanupFailedNotice';
    }

    return '$trimmed $_cleanupFailedNotice';
  }
}
