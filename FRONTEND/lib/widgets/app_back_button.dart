import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

/// 이전 화면으로 돌아가는 공용 뒤로가기 버튼("<")입니다.
///
/// [onPressed] 를 주지 않으면 현재 경로를 닫습니다. 메인 화면처럼 경로를 닫는 대신
/// 상태를 바꿔 돌아가는 곳은 [onPressed]·[tooltip] 을 넘겨 같은 모양을 씁니다.
class AppBackButton extends StatelessWidget {
  const AppBackButton({
    super.key,
    this.onPressed,
    this.tooltip = '뒤로 가기',
    this.color,
  });

  /// 누를 때 동작. null 이면 `Navigator.pop`.
  final VoidCallback? onPressed;

  /// 접근성·테스트용 툴팁.
  final String tooltip;

  /// 아이콘 색. null 이면 밝기에 따라 흰색/회색.
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return IconButton(
      onPressed: onPressed ?? () => Navigator.pop(context),
      tooltip: tooltip,
      padding: EdgeInsets.zero,
      splashRadius: 22,
      alignment: Alignment.centerLeft,
      icon: Icon(
        CupertinoIcons.chevron_left,
        size: 30,
        color: color ?? (isDark ? Colors.white : const Color(0xFF6F6F6F)),
      ),
    );
  }
}
