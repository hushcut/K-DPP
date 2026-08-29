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

    await provider.logout();

    if (!context.mounted) return;

    navigator.pushNamedAndRemoveUntil('/login', (route) => false);
    messenger
      ..clearSnackBars()
      ..showSnackBar(SnackBar(content: Text(message)));
  }
}
