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
    required this.accentText,
    required this.accentForeground,
    required this.dangerText,
    required this.successText,
    required this.warningText,
    required this.inputLabel,
    required this.inputHint,
  });

  /// K-DPP 브랜드 강조색입니다.
  static const Color accent = Color(0xFF4A4EFE);

  /// 강조색의 눌림·선택 상태 색입니다.
  static const Color accentPressed = Color(0xFF383CDB);

  /// 흰 글자를 얹는 삭제·탈퇴·버리기 버튼 바탕입니다. 흰 글자와 4.98:1(전엔 redAccent 3.19:1, C53).
  static const Color danger = Color(0xFFD32F2F);

  /// 흰 글자를 얹는 확인·안내 버튼 바탕입니다. 흰 글자와 5.13:1(전엔 green 2.78:1, C53).
  static const Color success = Color(0xFF2E7D32);

  final bool isDark;
  final Color background;
  final Color card;
  final Color border;
  final Color textPrimary;
  final Color textSecondary;

  /// 글자로 쓰는 강조색(링크의 동작 글자 등)입니다. 다크 배경(#121212)에서 [accent] 는
  /// 대비가 3.4:1 로 본문 기준(4.5:1)에 못 미쳐 밝힌 색(8.0:1)을 씁니다. 라이트는 [accent](5.2:1).
  /// 다크 값은 숫자 키보드 막대의 회색 띠(#3A3A3C)에서도 4.5:1 을 넘게(4.9:1)
  /// 하나로 맞췄습니다(DECISIONS 187).
  final Color accentText;

  /// 배경·카드 위에 칠하는 강조색(선택된 탭·글자·아이콘·테두리·커서)입니다. 다크에서 [accent] 는
  /// 배경 3.4:1·카드 3.1:1 이라 밝힌 #8084FF(배경 5.9:1·카드 5.4:1)를 씁니다. 라이트는 [accent].
  /// 흰 글자·아이콘을 얹는 바탕(버튼·카드)은 이 색이 아니라 [accent] 그대로입니다(C55).
  final Color accentForeground;

  /// 글자로 쓰는 경고·삭제·만료 색입니다. 라이트는 수명 만료 카드의 붉은 바탕(#FFEBEE)에서도
  /// 4.5:1 을 넘는 #C62828, 다크는 원래 쓰던 redAccent(카드 5.3:1)입니다(C54).
  /// 아이콘·테두리는 3:1 이면 되므로 그대로 redAccent 를 씁니다.
  final Color dangerText;

  /// 글자로 쓰는 좋음·맞음 색입니다. 라이트 #2E7D32(흰 바탕 5.1:1), 다크는 원래 쓰던 green(C54).
  final Color successText;

  /// 글자로 쓰는 주의 색입니다. 라이트 #B45309(흰 바탕 5.0:1 — orange 계열은 shade900 도
  /// 3.8:1 이라 못 씀), 다크는 원래 쓰던 orange(C54).
  final Color warningText;

  /// 회색 입력 칸(라이트 #F1F1F4) 안의 칸 이름과 예시 글자입니다. 전엔 둘 다 #9E9E9E(2.4:1)였고,
  /// 라이트에서 이름은 [textSecondary](5.4:1), 예시는 그보다 옅은 #6B6B6B(4.7:1)로 나눴습니다(C56).
  final Color inputLabel;
  final Color inputHint;

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
    accentText: accent,
    accentForeground: accent,
    dangerText: Color(0xFFC62828),
    successText: Color(0xFF2E7D32),
    warningText: Color(0xFFB45309),
    inputLabel: Color(0xFF5F6368),
    inputHint: Color(0xFF6B6B6B),
  );

  static const AppPalette dark = AppPalette(
    isDark: true,
    background: Color(0xFF121212),
    card: Color(0xFF1C1C1E),
    border: Color(0xFF2C2C2E),
    textPrimary: Colors.white,
    textSecondary: Color(0xFFD1D1D6),
    accentText: Color(0xFF9EA1FF),
    accentForeground: Color(0xFF8084FF),
    dangerText: Colors.redAccent,
    successText: Colors.green,
    warningText: Colors.orange,
    inputLabel: Color(0xFF9A9A9A),
    inputHint: Color(0xFF9A9A9A),
  );
}
