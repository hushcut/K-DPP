/// 메인 화면을 열 때 선택할 탭과 리포트 표시 여부를 전달하는 경로 인자입니다.
class MainScreenArguments {
  const MainScreenArguments({this.initialIndex = 0, this.showReport = false});

  /// 처음 활성화할 하단 탭의 인덱스입니다.
  final int initialIndex;

  /// 진입 직후 리포트 화면을 열어야 하는지 나타냅니다.
  final bool showReport;
}
