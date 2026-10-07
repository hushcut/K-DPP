import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/widgets/kakao_login_button.dart';

Future<void> _pumpButton(
  WidgetTester tester, {
  bool isLoading = false,
  VoidCallback? onPressed,
  ThemeMode themeMode = ThemeMode.light,
}) {
  return tester.pumpWidget(
    MaterialApp(
      theme: ThemeData.light(),
      darkTheme: ThemeData.dark(),
      themeMode: themeMode,
      home: Scaffold(
        body: Center(
          child: KakaoLoginButton(
            isLoading: isLoading,
            onPressed: onPressed ?? () {},
          ),
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('카카오 디자인 가이드의 색·모서리·문구로 그린다', (tester) async {
    for (final themeMode in [ThemeMode.light, ThemeMode.dark]) {
      await _pumpButton(tester, themeMode: themeMode);

      final button = tester.widget<ElevatedButton>(find.byType(ElevatedButton));
      final style = button.style!;
      expect(
        style.backgroundColor!.resolve({}),
        const Color(0xFFFEE500),
        reason: '$themeMode',
      );
      expect(
        (style.shape!.resolve({}) as RoundedRectangleBorder).borderRadius,
        BorderRadius.circular(12),
      );

      final label = tester.widget<Text>(find.text('카카오 로그인'));
      expect(label.style!.color, const Color(0xD9000000));

      final symbol = tester.widget<SvgPicture>(find.byType(SvgPicture));
      expect(
        symbol.colorFilter,
        const ColorFilter.mode(Color(0xFF000000), BlendMode.srcIn),
      );
    }
  });

  testWidgets('말풍선 심볼은 카카오 SDK 가 주는 그림을 쓴다', (tester) async {
    // SDK 가 그림 경로를 바꾸면 버튼 심볼이 빈칸이 되므로 경로가 실제로 있는지 고정합니다.
    final svg = await rootBundle.loadString(
      'packages/kakao_flutter_sdk_user/assets/images/icon_talk_login.svg',
    );

    expect(svg, contains('<svg'));
  });

  testWidgets('낭독기에는 심볼 없이 카카오 로그인 버튼 하나로 읽힌다', (tester) async {
    final semantics = tester.ensureSemantics();
    var pressed = 0;
    await _pumpButton(tester, onPressed: () => pressed++);
    // 심볼 그림은 비동기로 읽혀, 다 읽은 뒤에야 그림의 낭독 칸이 생깁니다.
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 200)),
    );
    await tester.pump();

    final node = tester.getSemantics(find.bySemanticsLabel('카카오 로그인'));
    // 심볼이 버튼 아래 따로 '이미지' 칸으로 잡히면 낭독기가 한 번 더 멈춥니다.
    expect(node.childrenCount, 0);
    expect(
      node,
      matchesSemantics(
        label: '카카오 로그인',
        isButton: true,
        hasEnabledState: true,
        isEnabled: true,
        isFocusable: true,
        hasTapAction: true,
        hasFocusAction: true,
      ),
    );
    expect(tester.getSize(find.byType(KakaoLoginButton)).height, 56);

    await tester.tap(find.byType(KakaoLoginButton));
    expect(pressed, 1);
    semantics.dispose();
  });

  testWidgets('처리 중에는 눌리지 않고 진행 표시를 읽어 준다', (tester) async {
    final semantics = tester.ensureSemantics();
    var pressed = 0;
    await _pumpButton(tester, isLoading: true, onPressed: () => pressed++);

    final button = tester.widget<ElevatedButton>(find.byType(ElevatedButton));
    expect(button.onPressed, isNull);
    // 처리 중에도 카카오 색을 바꾸지 않습니다.
    expect(
      button.style!.backgroundColor!.resolve({WidgetState.disabled}),
      const Color(0xFFFEE500),
    );
    expect(find.text('카카오 로그인'), findsNothing);
    expect(find.bySemanticsLabel('카카오 로그인 중'), findsOneWidget);

    await tester.tap(find.byType(KakaoLoginButton), warnIfMissed: false);
    expect(pressed, 0);
    semantics.dispose();
  });
}
