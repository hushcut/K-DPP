import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'app_palette.dart';

/// 앱의 라이트·다크 [ThemeData]입니다.
///
/// 시트·대화상자 배경처럼 화면마다 반복되는 색은 여기서 한 번 정합니다. 시트를 여는 쪽에서
/// `backgroundColor: isDark ? … : …` 로 직접 넣으면 **여는 순간의 테마로 굳어**, 시트가 열린 채
/// 시스템 밝기가 바뀌면 글자만 바뀌고 배경은 남습니다(2026-09-22 폰 확인). 테마에 두면
/// 시트가 그릴 때마다 읽으므로 따라옵니다.
///
/// 버튼을 길게 누를 때 뜨는 툴팁은 끕니다([_tooltipTheme]).
class AppTheme {
  const AppTheme._();

  /// 길게 누를 때 뜨는 툴팁 말풍선을 끕니다(2026-09-24 사용자 요청: "<" 를 꾹 누르면 "리포트 닫기"가 뜸).
  /// `tooltip:` 문구는 VoiceOver 가 읽는 버튼 이름과 테스트의 `find.byTooltip` 용으로 그대로 남습니다.
  static const _tooltipTheme = TooltipThemeData(
    triggerMode: TooltipTriggerMode.manual,
  );

  /// 상태 표시줄(시각·와이파이·배터리) 아이콘 색은 테마 밝기를 따릅니다.
  ///
  /// 메인·스캔·리포트의 위 막대는 배경이 투명인데, AppBar 는 스타일을 따로 받지 않으면 배경색으로
  /// 밝기를 어림합니다. 투명(0x00000000)은 검정으로 쳐서 라이트 모드에서도 흰 아이콘이 됐습니다
  /// (2026-09-26 시뮬레이터 확인). 위 막대 뒤에는 늘 화면 배경이 비치므로 테마 밝기로 정합니다.
  /// 배경을 진한 색으로 칠한 위 막대를 새로 만들면 그 AppBar 에 `systemOverlayStyle` 을 따로 줍니다.
  ///
  /// 상태 표시줄만 정하고 Android 아래 내비게이션 바는 건드리지 않습니다(Flutter 기본과 같게).
  /// [SystemUiOverlayStyle.dark] 상수는 내비게이션 바를 검정으로 칠하므로 쓰지 않습니다.
  static const _lightStatusBar = SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarBrightness: Brightness.light, // iOS: 밝은 배경 → 검은 아이콘
    statusBarIconBrightness: Brightness.dark, // Android
  );

  static const _darkStatusBar = SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarBrightness: Brightness.dark, // iOS: 어두운 배경 → 흰 아이콘
    statusBarIconBrightness: Brightness.light, // Android
  );

  static ThemeData light() {
    return ThemeData(
      brightness: Brightness.light,
      scaffoldBackgroundColor: const Color(0xFFF8F9FC),
      colorScheme: ColorScheme.fromSeed(
        seedColor: AppPalette.accent,
        brightness: Brightness.light,
      ),
      appBarTheme: const AppBarTheme(systemOverlayStyle: _lightStatusBar),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: Colors.white,
        modalBackgroundColor: Colors.white,
      ),
      tooltipTheme: _tooltipTheme,
      useMaterial3: true,
    );
  }

  static ThemeData dark() {
    return ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: const Color(0xFF121212),
      canvasColor: const Color(0xFF121212),
      cardColor: const Color(0xFF1C1C1E),
      dividerColor: const Color(0xFF2C2C2E),
      colorScheme: ColorScheme.fromSeed(
        seedColor: AppPalette.accent,
        brightness: Brightness.dark,
        surface: const Color(0xFF1C1C1E),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: Color(0xFF121212),
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        systemOverlayStyle: _darkStatusBar,
        iconTheme: IconThemeData(color: Colors.white),
        titleTextStyle: TextStyle(
          color: Colors.white,
          fontSize: 20,
          fontWeight: FontWeight.w700,
        ),
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: Color(0xFF121212),
        modalBackgroundColor: Color(0xFF121212),
      ),
      dialogTheme: const DialogThemeData(
        backgroundColor: Color(0xFF1C1C1E),
        titleTextStyle: TextStyle(
          color: Colors.white,
          fontSize: 18,
          fontWeight: FontWeight.w700,
        ),
        contentTextStyle: TextStyle(
          color: Color(0xFFD1D1D6),
          fontSize: 14,
          height: 1.5,
        ),
      ),
      navigationBarTheme: const NavigationBarThemeData(
        backgroundColor: Color(0xFF161616),
        indicatorColor: Color(0xFF2A2A2E),
        labelTextStyle: WidgetStatePropertyAll(
          TextStyle(
            color: Colors.white,
            fontSize: 12,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      tooltipTheme: _tooltipTheme,
      useMaterial3: true,
    );
  }
}
