import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/email_login_screen.dart';

void main() {
  testWidgets('자판 인셋이 앱바 아래를 다 덮어 본문 높이가 0 이 돼도 레이아웃 예외가 나지 않는다', (
    tester,
  ) async {
    // iPhone 18 Pro Max(440×956pt, 3배) 크기.
    tester.view.physicalSize = const Size(440 * 3, 956 * 3);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(const MaterialApp(home: EmailLoginScreen()));
    await tester.pumpAndSettle();

    // 보통 자판(약 340pt)은 본문 높이를 넉넉히 남긴다. 2026-09-26 시뮬레이터에서
    // 한 번 난 예외(-12.0)는 아래 인셋이 앱바 아래를 모두 덮어 본문이 0 이 된 프레임이었다.
    tester.view.viewInsets = const FakeViewPadding(bottom: 956 * 3);
    await tester.pump();

    expect(tester.takeException(), isNull);

    // 인셋이 보통 자판 높이로 돌아오면 폼이 다시 그대로 보인다.
    tester.view.viewInsets = const FakeViewPadding(bottom: 336 * 3);
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.byType(TextFormField), findsNWidgets(2));
  });
}
