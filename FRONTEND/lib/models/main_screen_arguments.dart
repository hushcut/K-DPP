/// 메인 화면을 열 때 선택할 탭과 리포트 표시 여부를 전달하는 경로 인자입니다.
class MainScreenArguments {
  const MainScreenArguments({this.initialIndex = 0, this.showReport = false});

  /// 처음 보일 화면입니다. 0 홈 · 2 옷장은 하단 탭이고, 1 스캔은 홈 위에 쌓아 엽니다.
  final int initialIndex;

  /// 진입 직후 리포트 화면을 열어야 하는지 나타냅니다.
  final bool showReport;
}
