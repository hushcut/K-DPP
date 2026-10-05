import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/closet_screen.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:provider/provider.dart';

import 'helpers/fake_auth_session_storage.dart';
import 'helpers/fake_closet_storage.dart';

void main() {
  testWidgets('정렬 기준을 고르면 저장되고, 다음 실행에서 그 기준으로 시작한다', (tester) async {
    final storage = FakeClosetStorage();

    Future<ClosetProvider> pumpCloset({required bool restore}) async {
      final provider = ClosetProvider(
        storage: storage,
        authSessionStorage: FakeAuthSessionStorage(),
      );

      if (restore) {
        await provider.loadFromStorage();
      }

      await tester.pumpWidget(
        ChangeNotifierProvider.value(
          value: provider,
          child: MaterialApp(
            home: Scaffold(body: ClosetScreen(onOpenReport: (_) {})),
          ),
        ),
      );
      await tester.pumpAndSettle();

      return provider;
    }

    final provider = await pumpCloset(restore: false);
    await provider.addClothes(
      Clothes(
        title: '린넨 셔츠',
        category: '상의',
        health: 88,
        materials: {'linen': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 2.1,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('현재 정렬: 친환경 순'), findsOneWidget);

    await tester.tap(find.byTooltip('옷장 정렬'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('내 설정 순'));
    await tester.pumpAndSettle();

    expect(find.textContaining('현재 정렬: 내 설정 순'), findsOneWidget);
    // enum 이름이 아니라 storageValue가 기록돼야 이름을 바꿔도 값이 깨지지 않는다.
    expect(storage.savedSortOptionRaw, 'custom');

    // 앱을 다시 연 상황을 만든다. 빈 화면을 한 번 그려 이전 State를 확실히 버려야
    // 새 화면이 저장된 값으로 다시 시작하는지 검증할 수 있다.
    // (같은 트리를 그대로 다시 pump하면 Element가 재사용돼 initState가 실행되지 않는다.)
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpAndSettle();

    await pumpCloset(restore: true);

    expect(find.textContaining('현재 정렬: 내 설정 순'), findsOneWidget);
  });

  testWidgets('정렬 저장에 실패하면 화면도 이전 기준으로 되돌아간다', (tester) async {
    final storage = FakeClosetStorage();
    final provider = ClosetProvider(
      storage: storage,
      authSessionStorage: FakeAuthSessionStorage(),
    );
    await provider.addClothes(
      Clothes(
        title: '린넨 셔츠',
        category: '상의',
        health: 88,
        materials: {'linen': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 2.1,
      ),
    );

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          home: Scaffold(body: ClosetScreen(onOpenReport: (_) {})),
        ),
      ),
    );
    await tester.pumpAndSettle();

    storage.saveSortOptionError = Exception('저장소 오류');

    await tester.tap(find.byTooltip('옷장 정렬'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('건강도 순'));
    await tester.pumpAndSettle();

    // 화면이 Provider를 그대로 따르므로 되돌림이 즉시 보인다.
    // 화면만 새 기준을 유지하면 나중에 화면이 재생성될 때 말없이 바뀐다.
    expect(find.textContaining('현재 정렬: 친환경 순'), findsOneWidget);
    expect(find.text('정렬 방식을 저장하지 못해 이전 기준으로 되돌렸어요.'), findsOneWidget);
  });

  testWidgets('빈 옷장에서는 스캔 탭으로 이동하는 버튼을 제공한다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    var didTapScan = false;

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          home: Scaffold(
            body: ClosetScreen(
              onOpenReport: (_) {},
              onStartScan: () {
                didTapScan = true;
              },
            ),
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('스캔하러 가기'), findsOneWidget);

    await tester.tap(find.text('스캔하러 가기'));
    await tester.pump();

    expect(didTapScan, isTrue);
  });

  testWidgets('옷장 검색은 의류 이름과 소재명으로 목록을 필터링한다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());

    await provider.addClothes(
      Clothes(
        title: '린넨 셔츠',
        category: '상의',
        health: 88,
        materials: {'linen': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 2.1,
      ),
    );
    await provider.addClothes(
      Clothes(
        title: '데님 팬츠',
        category: '하의',
        health: 76,
        materials: {'cotton': 98, 'polyurethane': 2},
        careInstruction: '단독 세탁',
        carbonFootprint: 8.4,
      ),
    );

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          home: Scaffold(body: ClosetScreen(onOpenReport: (_) {})),
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('린넨 셔츠'), findsOneWidget);
    expect(find.text('데님 팬츠'), findsOneWidget);

    final listView = tester.widget<ListView>(find.byType(ListView).first);
    final padding = listView.padding as EdgeInsets;
    expect(padding.bottom, greaterThanOrEqualTo(26));

    await tester.enterText(find.byType(TextField), 'linen');
    await tester.pumpAndSettle();

    expect(find.text('린넨 셔츠'), findsOneWidget);
    expect(find.text('데님 팬츠'), findsNothing);

    await tester.enterText(find.byType(TextField), '없는 의류');
    await tester.pumpAndSettle();

    expect(find.text('"없는 의류"에 맞는 의류가 없습니다.'), findsOneWidget);
    expect(find.text('검색어 지우기'), findsOneWidget);

    await tester.tap(find.text('검색어 지우기'));
    await tester.pumpAndSettle();

    expect(find.text('린넨 셔츠'), findsOneWidget);
    expect(find.text('데님 팬츠'), findsOneWidget);
  });

  testWidgets('검색 결과가 없을 때 키보드가 올라와도 빈 목록 안내가 넘치지 않는다', (tester) async {
    // 2026-09-18 폰 확인(SM-N986N): 검색 결과 0건 + 키보드에서
    // 'BOTTOM OVERFLOWED BY 105 PIXELS'. 화면·배율·글자 크기는 그 폰 값(1080x2316,
    // 밀도 450 = 배율 2.8125, 글자 1.1 — adb로 확인), 키보드는 스크린샷에서 잰 1098 물리 픽셀.
    // (정정 2026-09-19: 처음엔 배율 2.625에 키보드를 500dp로 크게 잡았다)
    tester.view.physicalSize = const Size(1080, 2316);
    tester.view.devicePixelRatio = 2.8125;
    tester.platformDispatcher.textScaleFactorTestValue = 1.1;
    addTearDown(tester.view.reset);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

    final provider = ClosetProvider(storage: FakeClosetStorage());
    await provider.addClothes(
      Clothes(
        title: '린넨 셔츠',
        category: '상의',
        health: 88,
        materials: {'linen': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 2.1,
      ),
    );

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          home: Scaffold(body: ClosetScreen(onOpenReport: (_) {})),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), 'm');
    tester.view.viewInsets = const FakeViewPadding(bottom: 1098);
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('"m"에 맞는 의류가 없습니다.'), findsOneWidget);

    // 자리가 모자라도 스크롤해서 버튼까지 닿을 수 있어야 한다.
    await tester.ensureVisible(find.text('검색어 지우기'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('검색어 지우기'));
    await tester.pumpAndSettle();

    expect(find.text('린넨 셔츠'), findsOneWidget);
  });

  testWidgets('옷장 검색은 저장 키와 다른 언어의 소재명으로도 같은 소재를 찾는다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());

    // 같은 면 소재가 등록 경로에 따라 한글 키와 영문 키로 저장돼 있다.
    // 리포트에는 둘 다 설정 언어의 같은 이름으로 보이므로 검색도 같아야 한다.
    for (final (title, materials) in [
      ('스캔한 셔츠', {'면': 100.0}),
      ('직접 입력한 셔츠', {'cotton': 100.0}),
      ('모달 티셔츠', {'modal': 100.0}),
    ]) {
      await provider.addClothes(
        Clothes(
          title: title,
          category: '상의',
          health: 88,
          materials: materials,
          careInstruction: '찬물 세탁',
          carbonFootprint: 2.1,
        ),
      );
    }

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          home: Scaffold(body: ClosetScreen(onOpenReport: (_) {})),
        ),
      ),
    );
    await tester.pumpAndSettle();

    for (final query in ['면', 'cotton', 'COTTON']) {
      await tester.enterText(find.byType(TextField), query);
      await tester.pumpAndSettle();

      expect(find.text('스캔한 셔츠'), findsOneWidget, reason: query);
      expect(find.text('직접 입력한 셔츠'), findsOneWidget, reason: query);
      expect(find.text('모달 티셔츠'), findsNothing, reason: query);
    }
  });

  testWidgets('길게 눌러 선택한 의류를 확인 다이얼로그를 거쳐 삭제한다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    await provider.addClothes(
      Clothes(
        title: '홍길동 삭제 대상 니트',
        category: '상의',
        health: 80,
        materials: {'wool': 100},
        careInstruction: '드라이클리닝',
        carbonFootprint: 4.4,
      ),
    );

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          home: Scaffold(
            body: ClosetScreen(onOpenReport: (_) {}),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.longPress(find.text('홍길동 삭제 대상 니트'));
    await tester.pumpAndSettle();

    expect(find.text('1개 선택됨'), findsOneWidget);

    await tester.tap(find.text('선택 삭제'));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(ElevatedButton, '삭제'));
    await tester.pumpAndSettle();

    expect(find.text('1개의 의류가 삭제되었습니다.'), findsOneWidget);
    expect(provider.items, isEmpty);
    expect(find.text('1개 선택됨'), findsNothing);

    // 스낵바 타이머를 흘려보내 테스트 종료 시 잔여 타이머가 없게 합니다.
    await tester.pumpAndSettle(const Duration(seconds: 5));
  });

  testWidgets('선택 모드에서 시스템 뒤로가기는 앱 종료 대신 선택만 해제한다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    await provider.addClothes(
      Clothes(
        title: '홍길동 선택 해제 셔츠',
        category: '상의',
        health: 85,
        materials: {'cotton': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 3.1,
      ),
    );

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          home: Scaffold(
            body: ClosetScreen(onOpenReport: (_) {}),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.longPress(find.text('홍길동 선택 해제 셔츠'));
    await tester.pumpAndSettle();

    expect(find.text('1개 선택됨'), findsOneWidget);

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

    expect(find.text('1개 선택됨'), findsNothing);
    expect(provider.items, hasLength(1));
    expect(find.text('홍길동 선택 해제 셔츠'), findsOneWidget);
  });

  testWidgets('정렬 시트에서 기준을 고르면 현재 정렬 안내가 갱신된다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    await provider.addClothes(
      Clothes(
        title: '홍길동 정렬 확인 티셔츠',
        category: '상의',
        health: 90,
        materials: {'cotton': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 2.0,
      ),
    );

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          home: Scaffold(
            body: ClosetScreen(onOpenReport: (_) {}),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('옷장 정렬'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('건강도 순'));
    await tester.pumpAndSettle();

    expect(find.textContaining('현재 정렬: 건강도 순'), findsOneWidget);
  });

  testWidgets('정렬 시트는 선택한 항목에만 체크를 두고 나머지는 비운다', (tester) async {
    final semanticsHandle = tester.ensureSemantics();
    final provider = ClosetProvider(
      storage: FakeClosetStorage(),
      authSessionStorage: FakeAuthSessionStorage(),
    );

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          home: Scaffold(body: ClosetScreen(onOpenReport: (_) {})),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('옷장 정렬'));
    await tester.pumpAndSettle();

    // 넷 중 하나를 고르는 자리다. 체크와 빈 원을 섞으면 짝이 맞지 않고,
    // 전부 라디오 원으로 맞추면 입력 폼처럼 번잡해 체크 방식으로 정했다.
    expect(find.byIcon(Icons.check), findsOneWidget);
    expect(find.byIcon(Icons.radio_button_unchecked), findsNothing);
    expect(find.byIcon(Icons.radio_button_off), findsNothing);
    expect(find.byIcon(Icons.radio_button_checked), findsNothing);

    // 체크는 현재 기준(기본값 친환경 순) 줄에 있어야 한다.
    expect(
      find.descendant(
        of: find.widgetWithText(InkWell, '친환경 순'),
        matching: find.byIcon(Icons.check),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: find.widgetWithText(InkWell, '내 설정 순'),
        matching: find.byIcon(Icons.check),
      ),
      findsNothing,
    );

    // 색과 아이콘만으로 알리면 낭독기에서는 네 항목이 구분되지 않는다.
    expect(find.bySemanticsLabel('친환경 순 정렬'), findsOneWidget);
    expect(find.bySemanticsLabel('내 설정 순 정렬'), findsOneWidget);
    expect(
      tester.getSemantics(find.bySemanticsLabel('친환경 순 정렬')),
      isSemantics(isSelected: true, isButton: true),
    );
    expect(
      tester.getSemantics(find.bySemanticsLabel('내 설정 순 정렬')),
      isSemantics(isSelected: false),
    );

    semanticsHandle.dispose();
  });

  // 2026-09-24: 기본 모양은 카드+아래 여백을 배경색 네모 판째 들어 올려 "블럭"처럼 보였다(사용자 피드백).
  group('순서 바꾸기에서 집어 든 카드', () {
    Future<void> pumpReorderMode(
      WidgetTester tester, {
      List<String> titles = const ['홍길동 린넨 셔츠', '홍길동 데님 바지'],
    }) async {
      final provider = ClosetProvider(
        storage: FakeClosetStorage(),
        authSessionStorage: FakeAuthSessionStorage(),
      );
      for (final title in titles) {
        await provider.addClothes(
          Clothes(
            title: title,
            category: '상의',
            health: 88,
            materials: {'linen': 100},
            careInstruction: '찬물 세탁',
            carbonFootprint: 2.1,
          ),
        );
      }

      await tester.pumpWidget(
        ChangeNotifierProvider.value(
          value: provider,
          child: MaterialApp(
            home: Scaffold(body: ClosetScreen(onOpenReport: (_) {})),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byTooltip('옷장 정렬'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('내 설정 순'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('편집'));
      await tester.pumpAndSettle();
    }

    // 길게 눌러 집어 든 뒤 조금 움직이고, 들어 올리는 애니메이션이 끝날 때까지 기다린다.
    Future<TestGesture> liftFirstCard(
      WidgetTester tester, {
      String title = '홍길동 린넨 셔츠',
    }) async {
      final gesture = await tester.startGesture(
        tester.getCenter(find.text(title)),
      );
      await tester.pump(kLongPressTimeout + const Duration(milliseconds: 50));
      await gesture.moveBy(const Offset(0, 20));
      await tester.pump(const Duration(milliseconds: 400));
      return gesture;
    }

    Finder liftedScale() => find.byWidgetPredicate(
      (widget) =>
          widget is Transform &&
          (widget.transform.getMaxScaleOnAxis() - 1.03).abs() < 0.001,
    );

    testWidgets('네모 판 없이 카드만 3% 커지고 카드 모서리를 따라 그림자가 진다', (tester) async {
      await pumpReorderMode(tester);
      final gesture = await liftFirstCard(tester);

      expect(liftedScale(), findsOneWidget);
      // 기본 모양의 배경색 네모 판(elevation 이 있는 Material)이 없어야 한다.
      expect(
        find.byWidgetPredicate(
          (widget) => widget is Material && widget.elevation > 0,
        ),
        findsNothing,
      );
      expect(
        find.byWidgetPredicate((widget) {
          if (widget is! DecoratedBox) return false;
          final decoration = widget.decoration;
          return decoration is BoxDecoration &&
              decoration.borderRadius == BorderRadius.circular(16) &&
              (decoration.boxShadow?.any((s) => s.blurRadius == 22) ?? false);
        }),
        findsOneWidget,
      );

      await gesture.up();
      await tester.pumpAndSettle();

      expect(liftedScale(), findsNothing);
    });

    // 울린 진동 종류를 차례로 모은다(HapticFeedbackType.mediumImpact 등).
    List<String?> recordHaptics(WidgetTester tester) {
      final haptics = <String?>[];
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        (call) async {
          if (call.method == 'HapticFeedback.vibrate') {
            haptics.add(call.arguments as String?);
          }
          return null;
        },
      );
      addTearDown(
        () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
          SystemChannels.platform,
          null,
        ),
      );
      return haptics;
    }

    testWidgets('집어 드는 순간 짧은 진동이 한 번 울린다', (tester) async {
      final haptics = recordHaptics(tester);

      await pumpReorderMode(tester);
      final gesture = await liftFirstCard(tester);
      await gesture.up();
      await tester.pumpAndSettle();

      expect(haptics, ['HapticFeedbackType.mediumImpact']);
    });

    // 2026-09-25 사용자 요청: 끄는 동안 부딪히는(밀어내는) 카드마다 가벼운 틱.
    // 판정은 화면의 카드 글자 위치로 잰다. 끌고 있는 카드 아래의 카드는 제자리(0)와
    // 한 칸 위(-간격) 두 곳만 쉬는 자리이고, 쉬는 자리를 떠나기 시작한 프레임에 틱이 울려야 한다.
    group('끄는 동안 밀려나는 카드마다 가벼운 틱', () {
      const titles = ['홍길동 카드 1', '홍길동 카드 2', '홍길동 카드 3', '홍길동 카드 4'];
      const others = ['홍길동 카드 2', '홍길동 카드 3', '홍길동 카드 4'];

      int ticks(List<String?> haptics) =>
          haptics.where((h) => h == 'HapticFeedbackType.selectionClick').length;

      testWidgets('카드가 밀려나기 시작하는 프레임마다 틱이 한 번씩 울리고, 내려놓을 때는 울리지 않는다', (
        tester,
      ) async {
        // 자동 스크롤이 끼어들지 않게 화면을 넉넉히 키운다.
        await tester.binding.setSurfaceSize(const Size(800, 1600));
        addTearDown(() => tester.binding.setSurfaceSize(null));
        final haptics = recordHaptics(tester);
        await pumpReorderMode(tester, titles: titles);

        double top(String title) => tester.getTopLeft(find.text(title)).dy;
        final home = {for (final t in others) t: top(t)};
        final gap = home['홍길동 카드 3']! - home['홍길동 카드 2']!;
        bool atRest(double d) => d.abs() < 0.5 || (d + gap).abs() < 0.5;

        final gesture = await liftFirstCard(tester, title: '홍길동 카드 1');
        expect(ticks(haptics), 0, reason: '집어 들고 조금 움직인 것만으로는 틱이 없다');

        var previous = {for (final t in others) t: top(t) - home[t]!};
        final tickFrames = <int>[];
        final leaveRestFrames = <int>[];
        var frame = 0;

        Future<void> moveInSteps(double distance) async {
          final steps = (distance.abs() / 8).round();
          for (var i = 0; i < steps; i++) {
            final before = ticks(haptics);
            await gesture.moveBy(Offset(0, distance.sign * 8));
            await tester.pump(const Duration(milliseconds: 16));
            frame++;

            final now = {for (final t in others) t: top(t) - home[t]!};
            if (others.any((t) => atRest(previous[t]!) && !atRest(now[t]!))) {
              leaveRestFrames.add(frame);
            }
            if (ticks(haptics) > before) tickFrames.add(frame);
            previous = now;
          }
          // 손가락을 멈추고 움직이던 카드가 자리를 잡을 때까지 기다린다.
          await tester.pump(const Duration(milliseconds: 300));
          previous = {for (final t in others) t: top(t) - home[t]!};
        }

        // 카드 두 장 높이만큼 내린다: 2·3번 카드가 차례로 한 칸씩 올라간다.
        await moveInSteps(2 * gap - 20);
        expect(ticks(haptics), 2);
        expect(top('홍길동 카드 2') - home['홍길동 카드 2']!, closeTo(-gap, 0.5));
        expect(top('홍길동 카드 3') - home['홍길동 카드 3']!, closeTo(-gap, 0.5));
        expect(top('홍길동 카드 4') - home['홍길동 카드 4']!, closeTo(0, 0.5));

        // 한 장 높이만큼 되돌린다: 3번 카드가 제자리로 돌아간다.
        await moveInSteps(-gap);
        expect(ticks(haptics), 3);
        expect(top('홍길동 카드 3') - home['홍길동 카드 3']!, closeTo(0, 0.5));

        expect(tickFrames, leaveRestFrames);

        await gesture.up();
        await tester.pumpAndSettle();

        expect(ticks(haptics), 3, reason: '내려놓으며 카드들이 제자리로 돌아가는 건 밀어낸 게 아니다');
        expect(haptics.first, 'HapticFeedbackType.mediumImpact');
      });

      testWidgets('자동 스크롤 중에도 밀려나는 카드에만 울리고, 스크롤만으로는 울리지 않는다', (tester) async {
        await tester.binding.setSurfaceSize(const Size(800, 700));
        addTearDown(() => tester.binding.setSurfaceSize(null));
        final haptics = recordHaptics(tester);
        final many = [for (var i = 1; i <= 9; i++) '홍길동 카드 $i'];
        await pumpReorderMode(tester, titles: many);

        final scrollable = Scrollable.of(tester.element(find.text('홍길동 카드 2')));
        final pixelsAtStart = scrollable.position.pixels;

        // 스크롤을 뺀 목록 내용 기준 위치. 아직 만들어지지 않은 카드는 null.
        // 화면 바로 밖에 미리 만들어 둔 카드도 잰다 — 보이기 전에 밀려나기 시작할 수 있다.
        double? contentTop(String title) {
          final finder = find.text(title, skipOffstage: false);
          if (finder.evaluate().isEmpty) return null;
          return tester.getTopLeft(finder).dy + scrollable.position.pixels;
        }

        final gesture = await liftFirstCard(tester, title: '홍길동 카드 1');
        final start = tester.getCenter(find.text('홍길동 카드 1'));
        // 목록 아래 끝 가까이로 끌고 가서 멈춘다: 목록이 저절로 내려가며 카드들이 밀려난다.
        final bottomEdge = tester
            .getBottomLeft(find.byType(Scrollable).last)
            .dy;
        final target = bottomEdge - 10 - start.dy;

        final firstSeen = <String, double>{};
        var previous = <String, double>{};
        final tickFrames = <int>[];
        final leaveRestFrames = <int>[];
        double? gap;

        for (var frame = 1; frame <= 150; frame++) {
          final before = ticks(haptics);
          if (frame <= 20) {
            await gesture.moveBy(Offset(0, target / 20));
          }
          await tester.pump(const Duration(milliseconds: 16));

          final now = <String, double>{};
          for (final t in many.skip(1)) {
            final y = contentTop(t);
            if (y == null) continue;
            now[t] = y;
            firstSeen.putIfAbsent(t, () => y);
          }
          gap ??= firstSeen['홍길동 카드 3']! - firstSeen['홍길동 카드 2']!;
          bool atRest(String t, double y) {
            final d = y - firstSeen[t]!;
            return d.abs() < 0.5 || (d + gap!).abs() < 0.5;
          }

          final leftRest = now.keys.any(
            (t) =>
                previous.containsKey(t) &&
                atRest(t, previous[t]!) &&
                !atRest(t, now[t]!),
          );
          if (leftRest) leaveRestFrames.add(frame);
          if (ticks(haptics) > before) tickFrames.add(frame);
          previous = now;
        }

        expect(
          scrollable.position.pixels,
          greaterThan(pixelsAtStart + gap!),
          reason: '자동 스크롤이 실제로 일어나야 이 테스트가 의미가 있다',
        );
        expect(tickFrames, isNotEmpty);
        expect(tickFrames, leaveRestFrames);

        await gesture.up();
        await tester.pumpAndSettle();
      });
    });
  });
}
