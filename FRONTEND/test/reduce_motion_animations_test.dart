import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/main_screen.dart';
import 'package:k_dpp/material_name_display_provider.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/navigation_bar_opacity_provider.dart';
import 'package:k_dpp/splash_screen.dart';
import 'package:k_dpp/utils/clothing_type_catalog.dart';
import 'package:k_dpp/widgets/app_banner.dart';
import 'package:k_dpp/widgets/clothing_type_picker_sheet.dart';
import 'package:provider/provider.dart';

import 'helpers/fake_auth_session_storage.dart';
import 'helpers/fake_closet_storage.dart';

// 기기에서 '동작 줄이기'를 켜면 앱의 애니메이션이 첫 프레임 뒤 100ms 안에 끝나는지 봅니다.
// 곳마다 Android '애니메이션 삭제'(disableAnimations)와 iOS '동작 줄이기'(reduceMotion)를 함께 돌립니다.
// 시험 바인딩도 앱과 같이 ReduceMotionSemanticsBinding 을 씁니다(flutter_test_config.dart).
void main() {
  _testReducedMotion('스플래시 로고가 바로 다 보인다', (tester) async {
    await _expectDoneWithin100ms(
      tester,
      act: () => tester.pumpWidget(
        ChangeNotifierProvider.value(
          value: ClosetProvider(
            storage: FakeClosetStorage(),
            authSessionStorage: FakeAuthSessionStorage(),
          ),
          child: MaterialApp(
            initialRoute: '/splash',
            routes: {
              '/splash': (context) => const SplashScreen(
                minimumDisplayDuration: Duration(seconds: 3),
              ),
              '/login': (context) => const Scaffold(body: Text('로그인 화면')),
            },
          ),
        ),
      ),
      look: () {
        final splash = find.byType(SplashScreen);
        return [
          tester
              .widget<FadeTransition>(
                find
                    .descendant(
                      of: splash,
                      matching: find.byType(FadeTransition),
                    )
                    .first,
              )
              .opacity
              .value,
          tester
              .widget<ScaleTransition>(
                find
                    .descendant(
                      of: splash,
                      matching: find.byType(ScaleTransition),
                    )
                    .first,
              )
              .scale
              .value,
        ];
      },
      // 로고 애니메이션(900ms)만 끝냅니다. 최소 표시 시간(3초) 뒤 로그인으로 넘어가는 것은 마지막에 보냅니다.
      settle: () => tester.pump(const Duration(seconds: 1)),
    );

    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
  });

  _testReducedMotion('탭을 바꾸면 새 탭과 하단 메뉴 표시가 바로 바뀐다', (tester) async {
    await _pumpMainScreen(tester);

    await _expectDoneWithin100ms(
      tester,
      act: () => tester.tap(find.text('옷장')),
      look: () => [
        _tabBodyOpacity(tester),
        tester.getTopLeft(find.text('내 옷장')),
        tester.widget<Text>(find.text('옷장')).style?.color,
        tester.widget<Text>(find.text('홈')).style?.color,
      ],
    );
  });

  _testReducedMotion('옷장 선택 모드에서 하단 메뉴가 바로 숨고 휴지통이 바로 뜬다', (tester) async {
    await _pumpMainScreen(tester);
    await tester.tap(find.text('옷장'));
    await tester.pumpAndSettle();

    await _expectDoneWithin100ms(
      tester,
      act: () => tester.tap(find.text('선택')),
      look: () => [
        tester.getTopLeft(find.text('홈')),
        tester.getTopLeft(find.byIcon(Icons.delete_outline)),
      ],
    );
  });

  _testReducedMotion('의류 종류 시트에서 직접 입력으로 바로 바뀐다', (tester) async {
    _usePhoneView(tester);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => Center(
              child: ElevatedButton(
                onPressed: () => showClothingTypePickerSheet(
                  context: context,
                  options: ClothingTypeCatalog.options,
                  initialSelection: ClothingTypeCatalog.defaultOption,
                ),
                child: const Text('시트 열기'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('시트 열기'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('직접 입력'), 100);

    await _expectDoneWithin100ms(
      tester,
      act: () => tester.tap(find.text('직접 입력')),
      // 바뀌는 동안에는 나가는 목록(그 안의 '직접 입력')이 남아 있습니다.
      look: () => find.text('직접 입력').evaluate().length,
    );
  });

  _testReducedMotion('옷장 상단 탭을 누르면 탭 본문이 바로 넘어간다', (tester) async {
    await _pumpMainScreen(tester);
    await tester.tap(find.text('옷장'));
    await tester.pumpAndSettle();

    await _expectDoneWithin100ms(
      tester,
      act: () => tester.tap(
        find.descendant(of: find.byType(TabBar), matching: find.text('하의')),
      ),
      look: () =>
          tester.getTopLeft(find.text('하의 의류가 없습니다.', skipOffstage: false)),
    );
  });

  group('Flutter 가 그리는 전환', () {
    _testReducedMotion('새 화면이 바로 열린다', (tester) async {
      await _pumpLauncher(tester, (context) {
        Navigator.of(context).push(
          MaterialPageRoute<void>(
            builder: (_) => const Scaffold(body: Text('새 화면')),
          ),
        );
      });

      await _expectDoneWithin100ms(
        tester,
        act: () => tester.tap(find.text('열기')),
        look: () => tester.getTopLeft(find.text('새 화면')),
      );
    });

    _testReducedMotion('아래 시트가 바로 올라온다', (tester) async {
      await _pumpLauncher(tester, (context) {
        showModalBottomSheet<void>(
          context: context,
          builder: (_) => const SizedBox(height: 200, child: Text('시트')),
        );
      });

      await _expectDoneWithin100ms(
        tester,
        act: () => tester.tap(find.text('열기')),
        look: () => tester.getTopLeft(find.text('시트')),
      );
    });

    _testReducedMotion('확인창이 바로 뜬다', (tester) async {
      await _pumpLauncher(tester, (context) {
        showDialog<void>(
          context: context,
          builder: (_) => const AlertDialog(content: Text('확인창')),
        );
      });

      await _expectDoneWithin100ms(
        tester,
        act: () => tester.tap(find.text('열기')),
        look: () => [
          tester.getRect(find.byType(AlertDialog)),
          tester
              .widgetList<FadeTransition>(
                find.ancestor(
                  of: find.byType(AlertDialog),
                  matching: find.byType(FadeTransition),
                ),
              )
              .map((fade) => fade.opacity.value)
              .toList(),
        ],
      );
    });
  });
}

/// [description] 을 Android '애니메이션 삭제'와 iOS '동작 줄이기'에서 한 번씩 돌립니다.
void _testReducedMotion(
  String description,
  Future<void> Function(WidgetTester tester) body,
) {
  testWidgets(
    'Android 애니메이션 삭제: $description',
    (tester) async {
      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(disableAnimations: true);
      addTearDown(
        tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
      );
      await body(tester);
    },
    variant: TargetPlatformVariant.only(TargetPlatform.android),
  );

  testWidgets(
    'iOS 동작 줄이기: $description',
    (tester) async {
      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(
            reduceMotion: true,
            supportsAnnounce: true,
          );
      addTearDown(
        tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
      );
      await body(tester);
    },
    variant: TargetPlatformVariant.only(TargetPlatform.iOS),
  );
}

/// [act] 로 애니메이션을 시작하고, 그 첫 프레임에서 100ms 뒤의 모습([look])이 다 끝난 뒤와 같은지 봅니다.
///
/// 애니메이션은 시작한 다음 프레임부터 시간을 셉니다. 그래서 한 프레임을 먼저 그린 뒤 100ms 를 보냅니다.
Future<void> _expectDoneWithin100ms(
  WidgetTester tester, {
  required Future<void> Function() act,
  required Object? Function() look,
  Future<void> Function()? settle,
}) async {
  await act();
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 100));
  final early = look();

  await (settle ?? tester.pumpAndSettle)();
  expect(early, look());
}

Future<void> _pumpMainScreen(WidgetTester tester) async {
  final provider = ClosetProvider(storage: FakeClosetStorage());
  await provider.addClothes(
    Clothes(
      title: '홍길동 니트',
      category: '상의',
      health: 84,
      materials: {'wool': 100},
      careInstruction: '드라이클리닝 권장',
      carbonFootprint: 3.6,
    ),
  );

  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider.value(value: provider),
        ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
        ChangeNotifierProvider(create: (_) => NavigationBarOpacityProvider()),
      ],
      child: const MaterialApp(
        builder: AppBannerHost.builder,
        home: MainScreen(),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

/// 메인 화면에서 탭 본문(IndexedStack)을 감싼 전환의 불투명도입니다.
double _tabBodyOpacity(WidgetTester tester) => tester
    .widgetList<FadeTransition>(
      find.ancestor(
        of: find.byType(IndexedStack),
        matching: find.byType(FadeTransition),
      ),
    )
    .first
    .opacity
    .value;

Future<void> _pumpLauncher(
  WidgetTester tester,
  void Function(BuildContext context) open,
) {
  return tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => Center(
            child: ElevatedButton(
              onPressed: () => open(context),
              child: const Text('열기'),
            ),
          ),
        ),
      ),
    ),
  );
}

void _usePhoneView(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
}
