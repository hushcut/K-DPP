import 'package:flutter/material.dart';

/// 라이트·다크 테마에서 앱 전반이 공유하는 기본 색상 묶음입니다.
/// 화면마다 흩어져 있던 isDark 삼항 색상을 한곳에서 관리해
/// 테마 색이 파일마다 어긋나지 않게 합니다.
class AppPalette {
  const AppPalette({
    required this.isDark,
    required this.background,
    required this.card,
    required this.border,
    required this.textPrimary,
    required this.textSecondary,
  });

  /// K-DPP 브랜드 강조색입니다.
  static const Color accent = Color(0xFF4A4EFE);

  /// 강조색의 눌림·선택 상태 색입니다.
  static const Color accentPressed = Color(0xFF383CDB);

  final bool isDark;
  final Color background;
  final Color card;
  final Color border;
  final Color textPrimary;
  final Color textSecondary;

  /// 현재 테마 밝기에 맞는 팔레트를 돌려줍니다.
  factory AppPalette.of(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return isDark ? dark : light;
  }

  static const AppPalette light = AppPalette(
    isDark: false,
    background: Color(0xFFF8F9FC),
    card: Colors.white,
    border: Color(0xFFE8E8EE),
    textPrimary: Color(0xFF111111),
    textSecondary: Color(0xFF5F6368),
  );

  static const AppPalette dark = AppPalette(
    isDark: true,
    background: Color(0xFF121212),
    card: Color(0xFF1C1C1E),
    border: Color(0xFF2C2C2E),
    textPrimary: Colors.white,
    textSecondary: Color(0xFFD1D1D6),
  );
}
