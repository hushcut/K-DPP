import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/main_screen.dart';
import 'package:k_dpp/material_name_display_provider.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/models/main_screen_arguments.dart';
import 'package:k_dpp/navigation_bar_opacity_provider.dart';
import 'package:k_dpp/scan_screen.dart';
import 'package:k_dpp/widgets/app_back_button.dart';
import 'package:k_dpp/widgets/scan_result_view.dart';
import 'package:provider/provider.dart';

import 'helpers/fake_closet_storage.dart';

void main() {
  // 스캔 화면은 카메라 준비 표시가 계속 돌 수 있어 settle 대신 라우트 전환
  // (iOS 500ms, Android 기본은 그보다 김)보다 길게 펌프한다.
  const routeTransition = Duration(milliseconds: 1000);
  const scanGuide = '케어 라벨을 프레임 안에 맞춰 촬영해 주세요';

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

  testWidgets('홈 최근 의류 카드를 누르면 리포트를 하단 메뉴까지 덮는 새 화면으로 연다', (tester) async {
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
    // 설정처럼 라우트로 쌓여 하단 메뉴는 가려진다(2026-09-24 사용자 결정 A안).
    expect(find.text('홈'), findsNothing);
    expect(find.text('옷장'), findsNothing);
  });

  testWidgets('스캔 저장 후에는 새 스캔 화면 위에 리포트를 쌓아 열고, 리포트를 닫으면 카메라를 켠다', (
    tester,
  ) async {
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
    expect(find.text('홈'), findsNothing);
    // 리포트 아래는 새 스캔 화면이지만 가려져 있으므로 카메라를 켜지 않는다.
    ScanScreen scanScreen() =>
        tester.widget<ScanScreen>(find.byType(ScanScreen, skipOffstage: false));
    expect(scanScreen().isActive, isFalse);

    // 리포트를 닫으면 바로 다음 옷을 찍을 수 있게 스캔 화면이 보인다.
    await tester.tap(find.byTooltip('리포트 닫기'));
    await tester.pump();
    await tester.pump(routeTransition);

    expect(find.text('상세 리포트'), findsNothing);
    expect(find.text(scanGuide), findsOneWidget);
    expect(scanScreen().isActive, isTrue);

    // 스캔 화면을 닫으면 그 아래 홈이 나오고, 스캔 화면은 정리된다.
    await tester.tap(find.byTooltip('스캔 화면 닫기'));
    await tester.pump();
    await tester.pump(routeTransition);

    expect(find.text('홈'), findsOneWidget);
    expect(find.byType(ScanScreen, skipOffstage: false), findsNothing);
  });

  testWidgets('스캔 저장 직후 리포트에서 의류를 지우면 스캔 화면까지 닫히고 옷장 탭이 보인다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    await provider.addClothes(
      Clothes(
        title: '홍길동 데님 재킷',
        category: '아우터',
        health: 70,
        materials: {'cotton': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 6.3,
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
          home: MainScreen(
            initialArguments: MainScreenArguments(
              initialIndex: 1,
              showReport: true,
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.text('이 의류 삭제하기'),
      300,
      scrollable: find.byType(Scrollable).last,
    );
    await tester.tap(find.text('이 의류 삭제하기'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ElevatedButton, '삭제'));
    await tester.pumpAndSettle();

    expect(provider.items, isEmpty);
    expect(find.text('상세 리포트'), findsNothing);
    expect(find.byType(ScanScreen, skipOffstage: false), findsNothing);
    expect(find.text('내 옷장'), findsOneWidget);
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

    // 리포트가 위에 쌓여 있는 동안에도 아래 메인 화면의 탭 스택은 유지되어야 합니다.
    expect(find.byType(IndexedStack, skipOffstage: false), findsOneWidget);
  });

  // 리포트는 설정처럼 라우트로 쌓인다(2026-09-24 사용자 결정 A안: iOS 에서 밀어서 닫히게).
  group('리포트 라우트', () {
    Future<ClosetProvider> pumpHomeWithClothes(WidgetTester tester) async {
      final provider = ClosetProvider(storage: FakeClosetStorage());
      await provider.addClothes(
        Clothes(
          title: '홍길동 린넨 셔츠',
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
          child: const MaterialApp(home: MainScreen()),
        ),
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('홍길동 린넨 셔츠'));
      await tester.pumpAndSettle();
      return provider;
    }

    testWidgets(
      'iOS 에서 리포트 왼쪽 끝을 밀면 설정 화면처럼 닫히고 홈이 다시 보인다',
      (tester) async {
        await pumpHomeWithClothes(tester);
        await tester.tap(find.text('홍길동 린넨 셔츠'));
        await tester.pumpAndSettle();
        expect(find.text('상세 리포트'), findsOneWidget);

        // 화면 왼쪽 끝(뒤로 밀기 영역 20px 안)에서 오른쪽으로 끝까지 민다.
        await tester.dragFrom(const Offset(5, 300), const Offset(600, 0));
        await tester.pumpAndSettle();

        expect(find.text('상세 리포트'), findsNothing);
        expect(find.text('홈'), findsOneWidget);
      },
      variant: TargetPlatformVariant.only(TargetPlatform.iOS),
    );

    testWidgets('리포트의 "<" 를 누르면 리포트가 닫힌다', (tester) async {
      await pumpHomeWithClothes(tester);
      await tester.tap(find.text('홍길동 린넨 셔츠'));
      await tester.pumpAndSettle();

      await tester.tap(find.byType(AppBackButton));
      await tester.pumpAndSettle();

      expect(find.text('상세 리포트'), findsNothing);
      expect(find.text('홈'), findsOneWidget);
    });

    testWidgets('리포트에서 의류를 지우면 리포트가 닫히고 옷장 탭이 보인다', (tester) async {
      final provider = await pumpHomeWithClothes(tester);
      await tester.tap(find.text('홍길동 린넨 셔츠'));
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(
        find.text('이 의류 삭제하기'),
        300,
        scrollable: find.byType(Scrollable).last,
      );
      await tester.tap(find.text('이 의류 삭제하기'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(ElevatedButton, '삭제'));
      await tester.pumpAndSettle();

      expect(provider.items, isEmpty);
      expect(find.text('상세 리포트'), findsNothing);
      expect(find.text('내 옷장'), findsOneWidget);
    });
  });

  // 아래는 탭 전환·스캔 화면과 하단 메뉴 반투명(F) 검증입니다.
  Future<ClosetProvider> pumpMainScreen(
    WidgetTester tester, {
    double navigationBarOpacity = NavigationBarOpacityProvider.defaultOpacity,
    Map<String, WidgetBuilder> routes = const {},
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
        child: MaterialApp(home: const MainScreen(), routes: routes),
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

  // 스캔은 탭이 아니라 리포트·설정처럼 위에 쌓는 화면이다(2026-09-26 사용자 결정 A안: iOS 에서 밀어서 닫히게).
  testWidgets('가운데 스캔 버튼은 하단 메뉴까지 덮는 새 화면을 열고, "<" 로 닫으면 스캔 화면을 정리한다', (
    tester,
  ) async {
    await pumpMainScreen(tester);

    await tester.tap(find.text('스캔'));
    await tester.pump();
    await tester.pump(routeTransition);

    expect(find.text(scanGuide), findsOneWidget);
    // 라우트로 쌓여 하단 메뉴를 포함한 메인 화면은 가려진다.
    expect(find.byType(MainScreen), findsNothing);
    expect(find.text('홈'), findsNothing);

    await tester.tap(find.byTooltip('스캔 화면 닫기'));
    await tester.pump();
    await tester.pump(routeTransition);

    expect(find.text('홈'), findsOneWidget);
    expect(find.byType(ScanScreen, skipOffstage: false), findsNothing);
  });

  testWidgets(
    'iOS 에서 스캔 화면 왼쪽 끝을 밀면 리포트처럼 닫히고 들어왔던 탭이 다시 보인다',
    (tester) async {
      await pumpMainScreen(tester);
      await tester.tap(find.text('옷장'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('스캔'));
      await tester.pump();
      await tester.pump(routeTransition);
      expect(find.text(scanGuide), findsOneWidget);

      // 화면 왼쪽 끝(뒤로 밀기 영역 20px 안)에서 오른쪽으로 끝까지 민다.
      await tester.dragFrom(const Offset(5, 300), const Offset(600, 0));
      await tester.pump();
      await tester.pump(routeTransition);

      expect(find.byType(ScanScreen, skipOffstage: false), findsNothing);
      expect(find.text('내 옷장'), findsOneWidget);
    },
    variant: TargetPlatformVariant.only(TargetPlatform.iOS),
  );

  testWidgets('스캔 화면에서 설정을 열면 카메라를 끄고, 설정을 닫으면 다시 켠다', (tester) async {
    await pumpMainScreen(
      tester,
      routes: {
        '/settings': (_) => Scaffold(
          appBar: AppBar(leading: const AppBackButton(tooltip: '설정 닫기')),
          body: const Text('설정 화면'),
        ),
      },
    );

    await tester.tap(find.text('스캔'));
    await tester.pump();
    await tester.pump(routeTransition);
    ScanScreen scanScreen() =>
        tester.widget<ScanScreen>(find.byType(ScanScreen, skipOffstage: false));
    expect(scanScreen().isActive, isTrue);

    await tester.tap(find.byTooltip('설정'));
    await tester.pump();
    await tester.pump(routeTransition);
    expect(find.text('설정 화면'), findsOneWidget);
    expect(scanScreen().isActive, isFalse);

    await tester.tap(find.byTooltip('설정 닫기'));
    await tester.pump();
    await tester.pump(routeTransition);
    expect(find.text('설정 화면'), findsNothing);
    expect(scanScreen().isActive, isTrue);
  });

  // 앨범에서 사진을 고른 것처럼 흉내 내 결과 입력 화면까지 들어간다. 없는 파일이라 분석이 실패해
  // 직접 입력으로 넘어간다(서버 분석 실패와 같은 경로). 파일 읽기는 실제 입출력이라 runAsync 로 기다린다.
  Future<void> openScanResultForm(WidgetTester tester) async {
    const picker = MethodChannel('plugins.flutter.io/image_picker');
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      picker,
      (call) async => '/nonexistent/k-dpp-label.jpg',
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        picker,
        null,
      ),
    );

    await tester.tap(find.text('스캔'));
    await tester.pump();
    await tester.pump(routeTransition);

    await tester.tap(find.byIcon(Icons.photo_library_outlined));
    final typeOption = find.text('반팔 티셔츠');
    for (var i = 0; i < 30 && typeOption.evaluate().isEmpty; i++) {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 20)),
      );
      await tester.pump(const Duration(milliseconds: 100));
    }
    // 종류 선택 시트가 다 올라온 뒤에 고른다(올라오는 도중엔 탭이 빗나간다).
    await tester.pump(routeTransition);
    await tester.tap(typeOption);
    await tester.pump();
    await tester.pump(routeTransition);

    // '다시 촬영' 글자는 종류 선택 시트에도 있으므로 결과 화면 위젯으로 확인한다.
    expect(find.byType(ScanResultView), findsOneWidget);
    expect(find.byType(BottomSheet), findsNothing);
  }

  testWidgets(
    '결과를 입력하는 동안에는 iOS 왼쪽 끝을 밀어도 스캔 화면이 닫히지 않는다',
    (tester) async {
      await pumpMainScreen(tester);
      await openScanResultForm(tester);

      await tester.dragFrom(const Offset(5, 300), const Offset(600, 0));
      await tester.pump();
      await tester.pump(routeTransition);

      expect(find.byType(ScanResultView), findsOneWidget);
      expect(find.byType(AlertDialog), findsNothing);
    },
    variant: TargetPlatformVariant.only(TargetPlatform.iOS),
  );

  testWidgets('결과를 입력하는 동안 "<"·뒤로가기를 누르면 버릴지 묻고, 버리기로 해야 닫힌다', (tester) async {
    await pumpMainScreen(tester);
    await openScanResultForm(tester);

    // "<" 에서 계속 작성하기를 고르면 입력 화면이 그대로 남는다.
    await tester.tap(find.byTooltip('스캔 화면 닫기'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('작성 중인 내용을 버릴까요?'), findsOneWidget);

    await tester.tap(find.text('계속 작성하기'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byType(AlertDialog), findsNothing);
    expect(find.byType(ScanResultView), findsOneWidget);

    // Android 시스템 뒤로가기에서 버리기로 하면 스캔 화면이 닫히고 홈이 보인다.
    final backMessage = const JSONMethodCodec().encodeMethodCall(
      const MethodCall('popRoute'),
    );
    await tester.binding.defaultBinaryMessenger.handlePlatformMessage(
      'flutter/navigation',
      backMessage,
      (_) {},
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('작성 중인 내용을 버릴까요?'), findsOneWidget);

    await tester.tap(find.text('버리고 닫기'));
    await tester.pump();
    await tester.pump(routeTransition);

    expect(find.byType(ScanScreen, skipOffstage: false), findsNothing);
    expect(find.text('홈'), findsOneWidget);
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
