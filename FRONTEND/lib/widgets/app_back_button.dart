import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

/// 현재 경로를 닫아 이전 화면으로 돌아가는 공용 뒤로가기 버튼입니다.
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
