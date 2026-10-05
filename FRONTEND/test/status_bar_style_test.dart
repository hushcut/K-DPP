import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/main_screen.dart';
import 'package:k_dpp/material_name_display_provider.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/navigation_bar_opacity_provider.dart';
import 'package:k_dpp/theme/app_theme.dart';
import 'package:provider/provider.dart';

import 'helpers/fake_closet_storage.dart';

// 2026-09-26 시뮬레이터 확인: 라이트 모드의 홈·옷장·스캔 화면에서 상태 표시줄(시각·배터리)이
// 흰색이라 밝은 배경 위에서 거의 안 보였다. 위 막대(AppBar) 배경이 투명이면 Flutter 는 그 색
// (0x00000000, 검정 취급)으로 밝기를 어림해 흰 아이콘을 고른다. 아이콘 색은 테마 밝기를 따라야 한다.
void main() {
  const routeTransition = Duration(milliseconds: 1000);
  const clothesTitle = '홍길동 린넨 셔츠';

  for (final mode in [ThemeMode.light, ThemeMode.dark]) {
    final isLight = mode == ThemeMode.light;
    final label = isLight ? '라이트' : '다크';
    final icons = isLight ? '검은' : '흰';

    Future<void> pumpApp(WidgetTester tester) async {
      final provider = ClosetProvider(storage: FakeClosetStorage());
      await provider.addClothes(
        Clothes(
          title: clothesTitle,
          category: '상의',
          health: 82,
          materials: {'linen': 100},
          careInstruction: '찬물 세탁',
          carbonFootprint: 2.1,
        ),
      );

      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: provider),
            ChangeNotifierProvider(
              create: (_) => MaterialNameDisplayProvider(),
            ),
            ChangeNotifierProvider(
              create: (_) => NavigationBarOpacityProvider(),
            ),
          ],
          child: MaterialApp(
            theme: AppTheme.light(),
            darkTheme: AppTheme.dark(),
            themeMode: mode,
            home: const MainScreen(),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    Future<void> expectThemedStatusBar(WidgetTester tester) async {
      final style = await _statusBarStyleOnScreen(tester);
      // iOS 는 statusBarBrightness(배경 밝기), Android 는 statusBarIconBrightness(아이콘 밝기)로 읽는다.
      expect(
        style?.statusBarBrightness,
        isLight ? Brightness.light : Brightness.dark,
        reason: 'iOS: $label 모드에선 $icons 아이콘이어야 한다',
      );
      expect(
        style?.statusBarIconBrightness,
        isLight ? Brightness.dark : Brightness.light,
        reason: 'Android: $label 모드에선 $icons 아이콘이어야 한다',
      );
      // 상태 표시줄만 정한다. Android 아래 시스템 내비게이션 바는 건드리지 않는다
      // (SystemUiOverlayStyle.dark 상수를 그대로 쓰면 검정으로 칠해진다).
      expect(style?.systemNavigationBarColor, isNull);
      expect(style?.statusBarColor, Colors.transparent);
    }

    testWidgets('$label 모드 홈 화면의 상태 표시줄은 $icons 아이콘이다', (tester) async {
      await pumpApp(tester);

      await expectThemedStatusBar(tester);
    });

    testWidgets('$label 모드 옷장 화면의 상태 표시줄은 $icons 아이콘이다', (tester) async {
      await pumpApp(tester);
      await tester.tap(find.text('옷장'));
      await tester.pumpAndSettle();
      expect(find.text('내 옷장'), findsOneWidget);

      await expectThemedStatusBar(tester);
    });

    testWidgets('$label 모드 스캔 화면의 상태 표시줄은 $icons 아이콘이다', (tester) async {
      await pumpApp(tester);
      await tester.tap(find.text('스캔'));
      await tester.pump();
      await tester.pump(routeTransition);
      expect(find.byTooltip('스캔 화면 닫기'), findsOneWidget);

      await expectThemedStatusBar(tester);
    });

    testWidgets('$label 모드 상세 리포트의 상태 표시줄은 $icons 아이콘이다', (tester) async {
      await pumpApp(tester);
      await tester.ensureVisible(find.text(clothesTitle));
      await tester.pumpAndSettle();
      await tester.tap(find.text(clothesTitle));
      await tester.pumpAndSettle();
      expect(find.text('상세 리포트'), findsOneWidget);

      await expectThemedStatusBar(tester);
    });
  }
}

/// 지금 화면이 엔진(iOS·Android)에 보내는 상태 표시줄 스타일입니다.
///
/// [SystemChrome.latestStyle] 은 테스트 사이에도 남는 값이라, 앞 화면의 값으로 통과하지 않게
/// 먼저 빈 스타일로 덮은 뒤 한 프레임을 새로 그립니다. 화면 맨 위에 스타일을 정하는 곳이 없으면
/// 빈 스타일이 그대로 남아 실패합니다.
Future<SystemUiOverlayStyle?> _statusBarStyleOnScreen(
  WidgetTester tester,
) async {
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle());
  tester.binding.scheduleFrame();
  await tester.pump();
  return SystemChrome.latestStyle;
}
