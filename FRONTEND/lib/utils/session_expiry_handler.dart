import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../closet_provider.dart';

class SessionExpiryHandler {
  const SessionExpiryHandler._();

  static const String defaultMessage = '로그인 세션이 만료되었습니다. 다시 로그인해 주세요.';

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
