import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/login_screen.dart';

void main() {
  testWidgets('로그인 화면 오른쪽 위를 눌러도 인증 없이 메인으로 이동하지 않는다', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        initialRoute: '/login',
        routes: {
          '/login': (context) => const LoginScreen(),
          '/main': (context) => const Scaffold(body: Text('메인 화면')),
        },
      ),
    );

    expect(find.text('K-DPP'), findsOneWidget);
    expect(find.text('메인 화면'), findsNothing);

    final screenSize = tester.view.physicalSize / tester.view.devicePixelRatio;
    await tester.tapAt(Offset(screenSize.width - 20, 20));
    await tester.pumpAndSettle();

    expect(find.text('K-DPP'), findsOneWidget);
    expect(find.text('메인 화면'), findsNothing);
  });
}
