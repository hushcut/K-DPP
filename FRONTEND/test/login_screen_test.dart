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

  testWidgets('작은 화면과 큰 글자에서도 로그인 랜딩이 넘치지 않는다', (tester) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      const MaterialApp(
        home: MediaQuery(
          data: MediaQueryData(textScaler: TextScaler.linear(1.8)),
          child: LoginScreen(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('로그인'), findsOneWidget);
    expect(find.text('계정이 없으신가요? 회원가입'), findsOneWidget);
  });
}
