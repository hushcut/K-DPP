import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../closet_provider.dart';

/// 만료된 로그인 세션을 정리하고 사용자를 로그인 화면으로 돌려보내는 공통 처리기다.
class SessionExpiryHandler {
  const SessionExpiryHandler._();

  static const String defaultMessage = '로그인 세션이 만료되었습니다. 다시 로그인해 주세요.';

  /// 로컬 사용자 상태를 로그아웃한 뒤 탐색 스택을 초기화하고 안내 메시지를 표시한다.
  static Future<void> handle(
    BuildContext context, {
    String message = defaultMessage,
  }) async {
    final provider = context.read<ClosetProvider>();
    final navigator = Navigator.of(context);
    final messenger = ScaffoldMessenger.of(context);

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
    messenger
      ..clearSnackBars()
      ..showSnackBar(
        SnackBar(
          content: Text(
            storageCleanupFailed
                ? '$message (저장된 로그인 정보 정리는 완료하지 못했습니다)'
                : message,
          ),
        ),
      );
  }
}
