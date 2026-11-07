import 'package:flutter_test/flutter_test.dart';

/// 리포트 탄소 카드의 '계산 기준 보기'를 펼친다. 범위·무게·가정·한계는 그 안에 접혀 있다
/// (DECISIONS 2026-11-07). 출처 줄은 접지 않아 펼치지 않아도 보인다.
Future<void> openCalculationBasis(WidgetTester tester) async {
  final toggle = find.text('계산 기준 보기');
  await tester.ensureVisible(toggle);
  await tester.pumpAndSettle();
  await tester.tap(toggle);
  await tester.pumpAndSettle();
}
