import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

class AppBackButton extends StatelessWidget {
  const AppBackButton({super.key});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return IconButton(
      onPressed: () => Navigator.pop(context),
      tooltip: '뒤로 가기',
      padding: EdgeInsets.zero,
      splashRadius: 22,
      alignment: Alignment.centerLeft,
      icon: Icon(
        CupertinoIcons.chevron_left,
        size: 30,
        color: isDark ? Colors.white : const Color(0xFF6F6F6F),
      ),
    );
  }
}
