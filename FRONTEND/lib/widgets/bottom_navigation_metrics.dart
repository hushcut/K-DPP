// 메인 화면 하단 메뉴의 치수입니다. 옷장 선택 모드의 휴지통이 숨은 메뉴 막대 자리에 맞춰 서도록 함께 씁니다.
// (main_screen.dart 와 closet_screen.dart 가 서로를 import 하지 않게 따로 둡니다.)

/// 하단 메뉴 상자의 치수입니다. 안전 영역 위에 [bottomMargin] 을 두고 [boxHeight] 상자를 놓으며,
/// 막대([barHeight])는 상자 아래쪽에 붙고 가운데 스캔 버튼이 그 위로 솟습니다.
abstract final class BottomNavigationMetrics {
  /// 화면 양옆과 상자 사이 간격입니다.
  static const double horizontalMargin = 18;

  /// 안전 영역과 상자 아래 끝 사이 간격입니다.
  static const double bottomMargin = 12;

  /// 막대와 위로 솟은 스캔 버튼을 합친 상자 높이입니다.
  static const double boxHeight = 94;

  /// 탭이 놓인 둥근 막대 높이입니다.
  static const double barHeight = 70;

  /// 탭 이름 글자가 시스템 글자 크기를 따라 커질 수 있는 최대 배율입니다.
  ///
  /// 스캔 버튼은 원(66) 아래 1 띄워 이름을 쓰므로, 상자([boxHeight]) 안에 남는 높이는 27 입니다.
  /// 12pt·줄 높이 1.1 글자는 2배에서 약 26.7 이라 여기까지는 잘리지 않습니다. 세 탭이 같은
  /// 크기로 보이도록 홈·옷장도 같은 배율에서 멈춥니다.
  static const double labelMaxTextScale = 2.0;
}
