import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/main_screen.dart';
import 'package:k_dpp/material_name_display_provider.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/models/main_screen_arguments.dart';
import 'package:k_dpp/navigation_bar_opacity_provider.dart';
import 'package:provider/provider.dart';

import 'helpers/fake_closet_storage.dart';

void main() {
  testWidgets('홈 옷장 보기 버튼을 누르면 옷장 탭으로 이동한다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    final clothes = Clothes(
      title: '홍길동 니트',
      category: '상의',
      health: 84,
      materials: {'wool': 100},
      careInstruction: '드라이클리닝 권장',
      carbonFootprint: 3.6,
    );
    await provider.addClothes(clothes);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: provider),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
          ChangeNotifierProvider(create: (_) => NavigationBarOpacityProvider()),
        ],
        child: const MaterialApp(home: MainScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('옷장 보기'), findsOneWidget);

    await tester.ensureVisible(find.text('옷장 보기'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('옷장 보기'));
    await tester.pumpAndSettle();

    expect(find.text('내 옷장'), findsOneWidget);
    expect(find.text('홍길동 니트'), findsOneWidget);
  });

  testWidgets('홈 최근 의류 카드를 누르면 하단바를 유지한 채 리포트를 연다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    final clothes = Clothes(
      title: '홍길동 반팔 티셔츠',
      category: '상의',
      health: 88,
      materials: {'cotton': 100},
      careInstruction: '찬물 세탁',
      carbonFootprint: 1.8,
    );
    await provider.addClothes(clothes);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: provider),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
          ChangeNotifierProvider(create: (_) => NavigationBarOpacityProvider()),
        ],
        child: const MaterialApp(home: MainScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('홍길동 반팔 티셔츠'), findsOneWidget);

    await tester.ensureVisible(find.text('홍길동 반팔 티셔츠'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('홍길동 반팔 티셔츠'));
    await tester.pumpAndSettle();

    expect(find.text('상세 리포트'), findsOneWidget);
    expect(find.text('홍길동 반팔 티셔츠'), findsOneWidget);
    expect(find.text('홈'), findsOneWidget);
    expect(find.text('스캔'), findsOneWidget);
    expect(find.text('옷장'), findsOneWidget);
  });

  testWidgets('스캔 저장 후 메인 하단바를 유지한 채 리포트를 연다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    final clothes = Clothes(
      title: '홍길동 코튼 셔츠',
      category: '상의',
      health: 88,
      materials: {'cotton': 100},
      careInstruction: '찬물 세탁',
      carbonFootprint: 4.2,
    );
    await provider.addClothes(clothes);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: provider),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
          ChangeNotifierProvider(create: (_) => NavigationBarOpacityProvider()),
        ],
        child: MaterialApp(
          home: const MainScreen(
            initialArguments: MainScreenArguments(
              initialIndex: 1,
              showReport: true,
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('상세 리포트'), findsOneWidget);
    expect(find.text('홍길동 코튼 셔츠'), findsOneWidget);
    expect(find.text('홈'), findsOneWidget);
    expect(find.text('스캔'), findsOneWidget);
    expect(find.text('옷장'), findsOneWidget);
  });

  testWidgets('리포트가 열린 상태의 시스템 뒤로가기는 앱을 닫는 대신 리포트를 닫는다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    final clothes = Clothes(
      title: '홍길동 후드집업',
      category: '상의',
      health: 80,
      materials: {'cotton': 100},
      careInstruction: '찬물 세탁',
      carbonFootprint: 2.4,
    );
    await provider.addClothes(clothes);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: provider),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
          ChangeNotifierProvider(create: (_) => NavigationBarOpacityProvider()),
        ],
        child: const MaterialApp(
          home: MainScreen(
            initialArguments: MainScreenArguments(showReport: true),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('상세 리포트'), findsOneWidget);

    // Android 시스템 뒤로가기와 동일한 popRoute 플랫폼 메시지를 보냅니다.
    final backMessage = const JSONMethodCodec().encodeMethodCall(
      const MethodCall('popRoute'),
    );
    await tester.binding.defaultBinaryMessenger.handlePlatformMessage(
      'flutter/navigation',
      backMessage,
      (_) {},
    );
    await tester.pumpAndSettle();

    expect(find.text('상세 리포트'), findsNothing);
    expect(find.byType(MainScreen), findsOneWidget);
  });

  testWidgets('리포트가 열려 있어도 탭 위젯 트리를 해제하지 않고 보존한다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    final clothes = Clothes(
      title: '홍길동 가디건',
      category: '상의',
      health: 77,
      materials: {'wool': 100},
      careInstruction: '드라이클리닝 권장',
      carbonFootprint: 5.1,
    );
    await provider.addClothes(clothes);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: provider),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
          ChangeNotifierProvider(create: (_) => NavigationBarOpacityProvider()),
        ],
        child: const MaterialApp(
          home: MainScreen(
            initialArguments: MainScreenArguments(showReport: true),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('상세 리포트'), findsOneWidget);

    // 리포트가 떠 있는 동안에도 탭 스택은 Offstage로 유지되어야 합니다.
    expect(find.byType(IndexedStack, skipOffstage: false), findsOneWidget);
  });

  // 아래는 스캔 탭 전환(D)과 하단 메뉴 반투명(F) 검증입니다.
  Future<ClosetProvider> pumpMainScreen(
    WidgetTester tester, {
    double navigationBarOpacity = NavigationBarOpacityProvider.defaultOpacity,
  }) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    final opacityProvider = NavigationBarOpacityProvider();
    if (navigationBarOpacity != NavigationBarOpacityProvider.defaultOpacity) {
      opacityProvider.preview(navigationBarOpacity);
    }

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: provider),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
          ChangeNotifierProvider.value(value: opacityProvider),
        ],
        child: const MaterialApp(home: MainScreen()),
      ),
    );
    await tester.pumpAndSettle();
    return provider;
  }

  // 가장 가까운 조상이 먼저 나오므로 first 가 탭 트리를 감싼 SlideTransition 이다.
  Finder tabSlide() => find
      .ancestor(
        of: find.byType(IndexedStack, skipOffstage: false),
        matching: find.byType(SlideTransition),
      )
      .first;

  testWidgets('홈에서 옷장으로 갈 때는 본문이 옆에서 들어온다(기존 동작 유지)', (tester) async {
    await pumpMainScreen(tester);

    await tester.tap(find.text('옷장'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 60));

    final slide = tester.widget<SlideTransition>(tabSlide());
    expect(slide.position.value.dx, greaterThan(0));
    await tester.pumpAndSettle();
  });

  testWidgets('스캔 탭에 들어갈 때는 아래에서 살짝 떠오르고, 나올 때는 밀지 않는다', (tester) async {
    // 2026-09-23 폰 확인: 옆에서 밀면 카메라 화면이 오른쪽 위에서 밀려 나오는 것처럼 보였다.
    // 사용자 요청으로 들어갈 때만 내비 바가 내려가는 것과 짝이 맞게 아래에서 4% 올라온다.
    await pumpMainScreen(tester);

    await tester.tap(find.text('스캔'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 60));

    final entering = tester.widget<SlideTransition>(tabSlide()).position.value;
    expect(entering.dx, 0);
    expect(entering.dy, greaterThan(0));
    expect(entering.dy, lessThanOrEqualTo(0.04));
    // 스캔 탭은 카메라 준비 표시가 계속 돌 수 있어 settle 대신 전환 시간(260ms)보다 길게 펌프한다.
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('케어 라벨을 프레임 안에 맞춰 촬영해 주세요'), findsOneWidget);

    // 돌아갈 때도 마찬가지다.
    await tester.tap(find.byTooltip('스캔 화면 닫기'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 60));

    expect(tester.widget<SlideTransition>(tabSlide()).position.value, Offset.zero);
    await tester.pump(const Duration(milliseconds: 400));
  });

  testWidgets('카메라 화면은 내비 바가 내려가는 동안 제자리에 있다', (tester) async {
    // 홈 표시기 같은 시스템 하단 여백이 있는 폰을 흉내 냅니다. 내비 바가 줄어드는 동안
    // Scaffold(extendBody)가 본문에 주는 하단 padding이 매 프레임 바뀌어도 카메라 UI는
    // 시스템 여백만 기준으로 그려져야 합니다.
    tester.view.padding = const FakeViewPadding(bottom: 34 * 3);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);

    await pumpMainScreen(tester);

    await tester.tap(find.text('스캔'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 60));

    // 들어갈 때 본문 전체가 아래에서 떠오르므로, 탭 트리(IndexedStack) 기준 상대 위치로 잰다.
    final guide = find.text('케어 라벨을 프레임 안에 맞춰 촬영해 주세요');
    final stack = find.byType(IndexedStack);
    final midTransition =
        tester.getTopLeft(guide) - tester.getTopLeft(stack);

    await tester.pump(const Duration(milliseconds: 400));

    expect(tester.getTopLeft(guide) - tester.getTopLeft(stack), midTransition);
  });

  testWidgets('하단 메뉴는 설정한 불투명도로 뒤를 흐리게 비추고, 100%면 흐림 없이 그린다', (
    tester,
  ) async {
    await pumpMainScreen(tester, navigationBarOpacity: 0.7);

    final backdrop = find.byType(BackdropFilter);
    expect(backdrop, findsOneWidget);
    final fill = tester.widget<DecoratedBox>(
      find.descendant(of: backdrop, matching: find.byType(DecoratedBox)).first,
    );
    final fillColor = (fill.decoration as BoxDecoration).color!;
    expect(fillColor.a, closeTo(0.7, 0.01));

    await pumpMainScreen(tester, navigationBarOpacity: 1.0);
    expect(find.byType(BackdropFilter), findsNothing);
  });
}
