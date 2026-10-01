import 'dart:async';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/closet_screen.dart';
import 'package:k_dpp/models/closet_sort_option.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/widgets/reorder_bump_haptics.dart';
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

  testWidgets('선택으로 고른 의류를 왼쪽 아래 휴지통과 확인 다이얼로그를 거쳐 삭제한다', (tester) async {
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
    // 옷장이 비지 않아도(자동 종료와 상관없이) 삭제가 끝나면 선택 모드가 끝나는지 본다.
    await provider.addClothes(_clothes('홍길동 남길 셔츠', carbonFootprint: 5));

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

    await tester.tap(find.text('선택'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('홍길동 삭제 대상 니트'));
    await tester.pumpAndSettle();

    expect(find.text('1개 선택됨'), findsOneWidget);

    await tester.tap(_trashButton());
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(ElevatedButton, '삭제'));
    await tester.pumpAndSettle();

    expect(find.text('1개의 의류가 삭제되었습니다.'), findsOneWidget);
    expect(provider.items.map((c) => c.title), ['홍길동 남길 셔츠']);
    expect(find.textContaining('개 선택됨'), findsNothing);
    expect(find.text('내 옷장'), findsOneWidget);
    expect(_trashButton(), findsNothing);

    // 스낵바 타이머를 흘려보내 테스트 종료 시 잔여 타이머가 없게 합니다.
    await tester.pumpAndSettle(const Duration(seconds: 5));
  });

  testWidgets('선택 모드에서 시스템 뒤로가기는 앱 종료 대신 선택 모드만 끝낸다(고른 것이 없어도)', (
    tester,
  ) async {
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

    for (final pick in [true, false]) {
      await tester.tap(find.text('선택'));
      await tester.pumpAndSettle();
      if (pick) {
        await tester.tap(find.text('홍길동 선택 해제 셔츠'));
        await tester.pumpAndSettle();
      }

      expect(find.text(pick ? '1개 선택됨' : '0개 선택됨'), findsOneWidget);

      await _sendSystemBack(tester);

      expect(find.textContaining('개 선택됨'), findsNothing, reason: '$pick');
      expect(find.text('내 옷장'), findsOneWidget);
      expect(provider.items, hasLength(1));
      expect(find.text('홍길동 선택 해제 셔츠'), findsOneWidget);
    }
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

      // 2026-10-01: 순서 편집 모드('편집'↔'완료')가 없어졌다. 내 설정 순이면 바로 ≡ 로 끈다.
      await tester.tap(find.byTooltip('옷장 정렬'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('내 설정 순'));
      await tester.pumpAndSettle();
    }

    // ≡ 손잡이를 잡고 기다림 없이 조금 움직이고, 들어 올리는 애니메이션이 끝날 때까지 기다린다.
    Future<TestGesture> liftFirstCard(
      WidgetTester tester, {
      String title = '홍길동 린넨 셔츠',
    }) async {
      final gesture = await tester.startGesture(
        tester.getCenter(_dragHandleOf(title)),
      );
      await gesture.moveBy(const Offset(0, 20));
      // 끌기는 움직이는 순간 시작되므로 다음 프레임이 들어 올리는 애니메이션의 첫 틱이다.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      return gesture;
    }

    testWidgets('네모 판 없이 카드만 3% 커지고 카드 모서리를 따라 그림자가 진다', (tester) async {
      await pumpReorderMode(tester);
      final gesture = await liftFirstCard(tester);

      expect(_liftedCard(), findsOneWidget);
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

      expect(_liftedCard(), findsNothing);
    });

    testWidgets('집어 드는 순간 강한 진동(heavyImpact)이 한 번 울린다', (tester) async {
      final haptics = _recordHaptics(tester);

      await pumpReorderMode(tester);
      final gesture = await liftFirstCard(tester);
      await gesture.up();
      await tester.pumpAndSettle();

      expect(haptics, ['HapticFeedbackType.heavyImpact']);
    });

    // 2026-09-25 사용자 요청: 끄는 동안 부딪히는(밀어내는) 카드마다 가벼운 틱.
    // 2026-10-01 한 단계 강하게 바꿨다(selectionClick → lightImpact).
    // 판정은 화면의 카드 글자 위치로 잰다. 끌고 있는 카드 아래의 카드는 제자리(0)와
    // 한 칸 위(-간격) 두 곳만 쉬는 자리이고, 쉬는 자리를 떠나기 시작한 프레임에 틱이 울려야 한다.
    group('끄는 동안 밀려나는 카드마다 가벼운 틱', () {
      const titles = ['홍길동 카드 1', '홍길동 카드 2', '홍길동 카드 3', '홍길동 카드 4'];
      const others = ['홍길동 카드 2', '홍길동 카드 3', '홍길동 카드 4'];

      int ticks(List<String?> haptics) =>
          haptics.where((h) => h == 'HapticFeedbackType.lightImpact').length;

      testWidgets('카드가 밀려나기 시작하는 프레임마다 틱이 한 번씩 울리고, 내려놓을 때는 울리지 않는다', (
        tester,
      ) async {
        // 자동 스크롤이 끼어들지 않게 화면을 넉넉히 키운다.
        await tester.binding.setSurfaceSize(const Size(800, 1600));
        addTearDown(() => tester.binding.setSurfaceSize(null));
        final haptics = _recordHaptics(tester);
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
        expect(haptics.first, 'HapticFeedbackType.heavyImpact');
      });

      // Flutter 는 끌기가 취소되면(전화가 오는 등) onReorderEnd 를 부르지 않는다
      // (widgets/reorderable_list.dart 의 취소 경로). 손가락이 떨어질 때 함께 멈춰야 한다.
      testWidgets('끌기가 취소돼도 틱 추적이 멈춰, 카드들이 제자리로 돌아갈 때 울리지 않는다', (tester) async {
        await tester.binding.setSurfaceSize(const Size(800, 1600));
        addTearDown(() => tester.binding.setSurfaceSize(null));
        final haptics = _recordHaptics(tester);
        await pumpReorderMode(tester, titles: titles);

        final gap =
            tester.getTopLeft(find.text('홍길동 카드 3')).dy -
            tester.getTopLeft(find.text('홍길동 카드 2')).dy;
        final gesture = await liftFirstCard(tester, title: '홍길동 카드 1');
        for (var i = 0; i < 20; i++) {
          await gesture.moveBy(Offset(0, (2 * gap - 20) / 20));
          await tester.pump(const Duration(milliseconds: 16));
        }
        await tester.pump(const Duration(milliseconds: 300));
        expect(ticks(haptics), 2);

        await gesture.cancel();
        await tester.pumpAndSettle();
        // 다른 손가락으로 목록을 건드려 카드들이 다시 그려져도 조용해야 한다.
        await tester.drag(find.text('홍길동 카드 4'), const Offset(0, -30));
        await tester.pumpAndSettle();

        expect(ticks(haptics), 2);
      });

      testWidgets('자동 스크롤 중에도 밀려나는 카드에만 울리고, 스크롤만으로는 울리지 않는다', (tester) async {
        await tester.binding.setSurfaceSize(const Size(800, 700));
        addTearDown(() => tester.binding.setSurfaceSize(null));
        final haptics = _recordHaptics(tester);
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

  // 2026-10-01 팀원 피드백 → DECISIONS 74·75·78: 순서 편집 모드와 꾹 눌러 선택을 없애고,
  // 내 설정 순에서만 ≡ 손잡이로 바로 끌며, 삭제는 모든 정렬의 '선택' 모드에서 한다.
  group('선택 모드와 ≡ 손잡이', () {
    testWidgets('≡ 는 아이콘 모양뿐 아니라 48×48 칸 어디를 잡아도 끌린다', (tester) async {
      await _pumpCloset(
        tester,
        clothes: _numbered(2),
        sort: ClosetSortOption.custom,
      );

      final cell = tester.getRect(
        find
            .ancestor(
              of: _dragHandleOf('홍길동 카드 1'),
              matching: find.byType(SizedBox),
            )
            .first,
      );
      expect(cell.size, const Size(48, 48));

      final gesture = await tester.startGesture(
        cell.topLeft + const Offset(3, 3),
      );
      await gesture.moveBy(const Offset(0, 20));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(_liftedCard(), findsOneWidget);

      await gesture.up();
      await tester.pumpAndSettle();
    });

    testWidgets('꾹 누르기는 어느 정렬에서도 선택·끌기를 하지 않고, 꾹 눌렀다 떼면 탭처럼 리포트를 연다', (
      tester,
    ) async {
      for (final sort in [ClosetSortOption.eco, ClosetSortOption.custom]) {
        final opened = <String>[];
        final haptics = _recordHaptics(tester);
        await _pumpCloset(
          tester,
          clothes: _numbered(2),
          sort: sort,
          onOpenReport: (item) => opened.add(item.title),
        );

        // 꾹 누른 채 움직여도 카드가 들리지 않고 선택도 되지 않는다(움직였으니 탭도 아니다).
        final moved = await tester.startGesture(
          tester.getCenter(find.text('홍길동 카드 1')),
        );
        await tester.pump(kLongPressTimeout + const Duration(milliseconds: 50));
        await moved.moveBy(const Offset(0, 40));
        await tester.pump(const Duration(milliseconds: 400));
        expect(_liftedCard(), findsNothing, reason: '$sort');
        await moved.up();
        await tester.pumpAndSettle();
        expect(opened, isEmpty, reason: '$sort');

        // 꾹 눌렀다 그 자리에서 떼면 탭과 같다.
        final held = await tester.startGesture(
          tester.getCenter(find.text('홍길동 카드 1')),
        );
        await tester.pump(kLongPressTimeout + const Duration(milliseconds: 50));
        await held.up();
        await tester.pumpAndSettle();

        expect(opened, ['홍길동 카드 1'], reason: '$sort');
        expect(find.textContaining('개 선택됨'), findsNothing, reason: '$sort');
        expect(haptics, isEmpty, reason: '$sort');
      }
    });

    testWidgets('≡ 는 내 설정 순 평소에만 있고, 탭만 하면 아무 일도 없다', (tester) async {
      final opened = <String>[];
      final haptics = _recordHaptics(tester);
      final provider = await _pumpCloset(
        tester,
        clothes: _numbered(2),
        onOpenReport: (item) => opened.add(item.title),
      );

      expect(find.byIcon(Icons.drag_handle), findsNothing);
      expect(find.byIcon(Icons.chevron_right), findsNWidgets(2));

      await provider.setClosetSortOption(ClosetSortOption.custom);
      await tester.pumpAndSettle();

      // 끌 수 있는 목록에서는 '>' 대신 손잡이가 그 자리에 선다.
      expect(find.byIcon(Icons.drag_handle), findsNWidgets(2));
      expect(find.byIcon(Icons.chevron_right), findsNothing);

      await tester.tap(_dragHandleOf('홍길동 카드 1'));
      await tester.pumpAndSettle();

      expect(opened, isEmpty, reason: '손잡이는 카드 누름 영역 밖이다');
      expect(find.textContaining('개 선택됨'), findsNothing);
      expect(haptics, isEmpty);
      expect(_liftedCard(), findsNothing);

      await tester.tap(find.text('선택'));
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.drag_handle), findsNothing);
      expect(find.byIcon(Icons.radio_button_unchecked), findsNWidgets(2));
    });

    testWidgets(
      '선택은 0개로 들어가 위쪽 윗줄만 바뀌고, 마지막 하나를 풀어도 모드가 남으며, 탭을 옮겨도 고른 것이 그대로다',
      (tester) async {
        final provider = await _pumpCloset(
          tester,
          clothes: [
            _clothes('홍길동 셔츠', carbonFootprint: 1),
            _clothes('홍길동 바지', category: '하의', carbonFootprint: 2),
          ],
        );

        bool searchFocused() => tester
            .widget<EditableText>(find.byType(EditableText))
            .focusNode
            .hasFocus;

        await tester.enterText(find.byType(TextField), '홍길동');
        await tester.pump();
        expect(searchFocused(), isTrue);

        await tester.tap(find.text('선택'));
        await tester.pumpAndSettle();

        expect(find.text('0개 선택됨'), findsOneWidget);
        expect(find.text('내 옷장'), findsNothing);
        expect(find.byTooltip('옷장 정렬'), findsNothing);
        // 헤더 틀은 그대로라 정렬 안내와 검색창(검색어 포함)이 남지만, 입력은 막힌다.
        expect(find.text('현재 정렬: 친환경 순'), findsOneWidget);
        expect(
          tester.widget<TextField>(find.byType(TextField)).enabled,
          isFalse,
        );
        expect(find.text('홍길동'), findsOneWidget);
        expect(searchFocused(), isFalse);
        expect(tester.widget<IconButton>(_trashButton()).onPressed, isNull);

        await tester.tap(find.text('홍길동 셔츠'));
        await tester.pumpAndSettle();
        expect(find.text('1개 선택됨'), findsOneWidget);
        expect(tester.widget<IconButton>(_trashButton()).onPressed, isNotNull);

        // 카테고리 탭을 옮겨도 고른 것은 남는다.
        await tester.tap(_categoryTab('하의'));
        await tester.pumpAndSettle();
        expect(find.text('1개 선택됨'), findsOneWidget);
        await tester.tap(_categoryTab('전체'));
        await tester.pumpAndSettle();

        await tester.tap(find.text('홍길동 셔츠'));
        await tester.pumpAndSettle();
        expect(find.text('0개 선택됨'), findsOneWidget);

        await tester.tap(find.text('취소'));
        await tester.pumpAndSettle();

        expect(find.textContaining('개 선택됨'), findsNothing);
        expect(find.text('내 옷장'), findsOneWidget);
        expect(_trashButton(), findsNothing);
        expect(
          tester.widget<TextField>(find.byType(TextField)).enabled,
          isTrue,
        );
        expect(provider.items, hasLength(2));
      },
    );

    testWidgets('옷이 없으면 선택을 누를 수 없고, 선택 중 옷이 모두 사라지면 선택 모드가 저절로 끝난다', (
      tester,
    ) async {
      final provider = await _pumpCloset(tester, clothes: const []);

      TextButton selectButton() =>
          tester.widget<TextButton>(find.widgetWithText(TextButton, '선택'));
      expect(selectButton().onPressed, isNull);

      await provider.addClothes(_clothes('홍길동 카드 1'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('선택'));
      await tester.pumpAndSettle();
      expect(find.text('0개 선택됨'), findsOneWidget);

      // 다른 화면(리포트)에서 마지막 옷을 지운 상황이다.
      await provider.removeClothes(provider.items.single);
      await tester.pumpAndSettle();

      expect(find.textContaining('개 선택됨'), findsNothing);
      expect(_trashButton(), findsNothing);
      expect(selectButton().onPressed, isNull);
    });

    testWidgets('탭마다 스크롤 위치를 기억해, 선택 모드를 오가거나 탭을 옮겨도 그 자리다', (tester) async {
      await _pumpCloset(
        tester,
        clothes: _numbered(12),
        sort: ClosetSortOption.custom,
      );

      ScrollPosition listPosition() => tester
          .state<ScrollableState>(
            find
                .byWidgetPredicate(
                  (w) =>
                      w is Scrollable && w.axisDirection == AxisDirection.down,
                )
                .first,
          )
          .position;

      listPosition().jumpTo(300);
      await tester.pumpAndSettle();

      // 내 설정 순에서는 선택 모드에 들어가며 끄는 목록이 일반 목록으로 바뀐다.
      await tester.tap(find.text('선택'));
      await tester.pumpAndSettle();
      expect(listPosition().pixels, 300);

      await tester.tap(find.text('취소'));
      await tester.pumpAndSettle();
      expect(listPosition().pixels, 300);

      await tester.tap(_categoryTab('하의'));
      await tester.pumpAndSettle();
      await tester.tap(_categoryTab('상의'));
      await tester.pumpAndSettle();
      expect(listPosition().pixels, 0, reason: '상의 탭은 따로 기억한다');

      await tester.tap(_categoryTab('전체'));
      await tester.pumpAndSettle();
      expect(listPosition().pixels, 300);
    });

    // 2026-10-01 실측(카드 3장, 가운데 카드): 한 칸의 0.6 만큼 내렸다가 0.3~0.5 만 되돌아와 놓으면
    // 카드는 하나도 안 움직였는데 onReorder(1, 2)(= 2번 앞에 넣기 = 제자리)가 온다.
    // 끝까지 되돌아오거나 위로 갔다 오면 onReorder 자체가 오지 않는다.
    testWidgets('≡ 로 집었다 제자리에 놓으면 순서를 다시 저장하지 않는다(아래·위로 갔다 덜 돌아와도)', (
      tester,
    ) async {
      await tester.binding.setSurfaceSize(const Size(800, 1600));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final storage = _CountingClosetStorage();
      final provider = await _pumpCloset(
        tester,
        clothes: _numbered(3),
        sort: ClosetSortOption.custom,
        storage: storage,
      );
      final titles = provider.items.map((c) => c.title).toList();
      final gap =
          tester.getTopLeft(find.text('홍길동 카드 3')).dy -
          tester.getTopLeft(find.text('홍길동 카드 2')).dy;
      storage.saveCount = 0;

      for (final (out, back) in [(0.6, -0.4), (-0.6, 0.4)]) {
        final gesture = await tester.startGesture(
          tester.getCenter(_dragHandleOf('홍길동 카드 2')),
        );
        for (final distance in [out * gap, back * gap]) {
          for (var i = 0; i < 10; i++) {
            await gesture.moveBy(Offset(0, distance / 10));
            await tester.pump(const Duration(milliseconds: 16));
          }
          await tester.pump(const Duration(milliseconds: 400));
        }
        await gesture.up();
        await tester.pumpAndSettle();

        expect(provider.items.map((c) => c.title), titles, reason: '$out');
        expect(storage.saveCount, 0, reason: '$out');
      }
    });

    testWidgets('상의 탭이나 검색으로 일부만 보일 때 끌어도 보이지 않는 옷의 자리는 그대로다', (tester) async {
      await tester.binding.setSurfaceSize(const Size(800, 1600));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final provider = await _pumpCloset(
        tester,
        clothes: [
          _clothes('홍길동 A'),
          _clothes('홍길동 B', category: '하의'),
          _clothes('홍길동 C'),
          _clothes('홍길동 D', category: '하의'),
        ],
        sort: ClosetSortOption.custom,
      );

      Future<void> dragAbove(String moving, String target) async {
        final distance =
            tester.getTopLeft(find.text(target)).dy -
            tester.getTopLeft(find.text(moving)).dy -
            20;
        final gesture = await tester.startGesture(
          tester.getCenter(_dragHandleOf(moving)),
        );
        for (var i = 0; i < 10; i++) {
          await gesture.moveBy(Offset(0, distance / 10));
          await tester.pump(const Duration(milliseconds: 16));
        }
        await tester.pump(const Duration(milliseconds: 300));
        await gesture.up();
        await tester.pumpAndSettle();
      }

      List<String> order() => provider.items.map((c) => c.title).toList();

      await tester.tap(_categoryTab('상의'));
      await tester.pumpAndSettle();
      await dragAbove('홍길동 C', '홍길동 A');
      expect(order(), ['홍길동 C', '홍길동 B', '홍길동 A', '홍길동 D']);

      await tester.tap(_categoryTab('전체'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), '하의');
      await tester.pumpAndSettle();
      await dragAbove('홍길동 D', '홍길동 B');
      expect(order(), ['홍길동 C', '홍길동 D', '홍길동 A', '홍길동 B']);
    });

    testWidgets('순서 이동 낭독기 동작은 내 설정 순 평소에만 있다', (tester) async {
      Finder reorderActions() => find.byWidgetPredicate(
        (w) =>
            w is Semantics &&
            (w.properties.customSemanticsActions?.isNotEmpty ?? false),
      );
      final provider = await _pumpCloset(tester, clothes: _numbered(2));
      expect(reorderActions(), findsNothing);

      await provider.setClosetSortOption(ClosetSortOption.custom);
      await tester.pumpAndSettle();
      expect(reorderActions(), findsNWidgets(2));

      await tester.tap(find.text('선택'));
      await tester.pumpAndSettle();
      expect(reorderActions(), findsNothing);
    });

    testWidgets('삭제를 저장하는 동안엔 취소·뒤로가 막히고, 저장에 실패하면 고른 채로 선택 모드에 남는다', (
      tester,
    ) async {
      final storage = _CountingClosetStorage();
      final provider = await _pumpCloset(
        tester,
        clothes: _numbered(1),
        storage: storage,
      );

      Future<void> confirmDelete() async {
        await tester.tap(_trashButton());
        await tester.pumpAndSettle();
        await tester.tap(find.widgetWithText(ElevatedButton, '삭제'));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
      }

      await tester.tap(find.text('선택'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('홍길동 카드 1'));
      await tester.pumpAndSettle();

      storage.gate = Completer<void>();
      storage.saveClothesError = Exception('저장소 오류');
      await confirmDelete();

      // 저장 중: 옷은 먼저 목록에서 빠지지만(옷장이 비어도) 선택 모드는 남고, 취소·뒤로는 듣지 않는다.
      expect(provider.items, isEmpty);
      expect(
        tester
            .widget<TextButton>(find.widgetWithText(TextButton, '취소'))
            .onPressed,
        isNull,
      );
      await _sendSystemBack(tester);
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.textContaining('개 선택됨'), findsOneWidget);

      storage.gate!.complete();
      await tester.pumpAndSettle();

      expect(find.text('의류 삭제를 저장하지 못했어요. 다시 시도해 주세요.'), findsOneWidget);
      expect(provider.items, hasLength(1));
      expect(find.text('1개 선택됨'), findsOneWidget);
      expect(tester.widget<IconButton>(_trashButton()).onPressed, isNotNull);
      await tester.pumpAndSettle(const Duration(seconds: 5));

      // 다시 시도해 저장되면 선택 모드가 끝난다.
      storage
        ..gate = null
        ..saveClothesError = null;
      await confirmDelete();
      await tester.pumpAndSettle();

      expect(find.text('1개의 의류가 삭제되었습니다.'), findsOneWidget);
      expect(provider.items, isEmpty);
      expect(find.textContaining('개 선택됨'), findsNothing);
      await tester.pumpAndSettle(const Duration(seconds: 5));
    });

    testWidgets('작은 화면·큰 글자에서도 제목과 오른쪽 버튼이 겹치지 않는다', (tester) async {
      // 너비 320(iPhone SE 1세대급)에 글자 2배.
      tester.view.physicalSize = const Size(960, 1920);
      tester.view.devicePixelRatio = 3;
      tester.platformDispatcher.textScaleFactorTestValue = 2;
      addTearDown(tester.view.reset);
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

      await _pumpCloset(tester, clothes: _numbered(3));
      expect(tester.takeException(), isNull);

      void expectApart(Finder title, List<Finder> buttons) {
        final titleRect = tester.getRect(title);
        expect(titleRect.left, greaterThanOrEqualTo(0));
        for (final button in buttons) {
          expect(titleRect.overlaps(tester.getRect(button)), isFalse);
        }
      }

      expectApart(find.text('내 옷장'), [
        find.widgetWithText(TextButton, '선택'),
        find.byTooltip('옷장 정렬'),
      ]);

      await tester.tap(find.text('선택'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('홍길동 카드 1'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expectApart(find.text('1개 선택됨'), [find.widgetWithText(TextButton, '취소')]);
    });
  });
}

Clothes _clothes(
  String title, {
  String category = '상의',
  double carbonFootprint = 2.1,
}) {
  return Clothes(
    title: title,
    category: category,
    health: 88,
    materials: {'linen': 100},
    careInstruction: '찬물 세탁',
    carbonFootprint: carbonFootprint,
  );
}

/// '홍길동 카드 1'부터 n까지. 친환경 순(기본)에서도 이 순서로 보이게 탄소량을 늘려 간다.
List<Clothes> _numbered(int count) => [
  for (var i = 1; i <= count; i++)
    _clothes('홍길동 카드 $i', carbonFootprint: i.toDouble()),
];

/// 옷장 화면 하나만 새로 띄운다. 이전 State 를 버리고 시작해 여러 번 불러도 서로 섞이지 않는다.
Future<ClosetProvider> _pumpCloset(
  WidgetTester tester, {
  required List<Clothes> clothes,
  ClosetSortOption sort = ClosetSortOption.eco,
  ValueChanged<Clothes>? onOpenReport,
  FakeClosetStorage? storage,
}) async {
  final provider = ClosetProvider(
    storage: storage ?? FakeClosetStorage(),
    authSessionStorage: FakeAuthSessionStorage(),
  );
  for (final item in clothes) {
    await provider.addClothes(item);
  }
  await provider.setClosetSortOption(sort);

  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pumpWidget(
    ChangeNotifierProvider.value(
      value: provider,
      child: MaterialApp(
        home: Scaffold(
          body: ClosetScreen(onOpenReport: onOpenReport ?? (_) {}),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return provider;
}

/// 선택 모드 왼쪽 아래 휴지통. 툴팁은 확인창 제목('선택한 의류 삭제')과 다르게 둔다.
Finder _trashButton() => find.ancestor(
  of: find.byTooltip('선택한 의류 지우기'),
  matching: find.byType(IconButton),
);

/// 그 옷 카드의 ≡ 손잡이.
Finder _dragHandleOf(String title) => find.descendant(
  of: find.ancestor(
    of: find.text(title),
    matching: find.byType(ReorderBumpProbe),
  ),
  matching: find.byIcon(Icons.drag_handle),
);

/// 카드의 분류 글자('상의' 등)와 구분해 위쪽 탭만 찾는다.
Finder _categoryTab(String label) =>
    find.descendant(of: find.byType(TabBar), matching: find.text(label));

/// 집어 든 카드(3% 커진 복사본).
Finder _liftedCard() => find.byWidgetPredicate(
  (widget) =>
      widget is Transform &&
      (widget.transform.getMaxScaleOnAxis() - 1.03).abs() < 0.001,
);

/// 울린 진동 종류를 차례로 모은다(HapticFeedbackType.heavyImpact 등).
List<String?> _recordHaptics(WidgetTester tester) {
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

/// Android 시스템 뒤로가기와 같은 popRoute 플랫폼 메시지를 보낸다.
Future<void> _sendSystemBack(WidgetTester tester) async {
  final backMessage = const JSONMethodCodec().encodeMethodCall(
    const MethodCall('popRoute'),
  );
  await tester.binding.defaultBinaryMessenger.handlePlatformMessage(
    'flutter/navigation',
    backMessage,
    (_) {},
  );
  await tester.pumpAndSettle();
}

/// 옷장 저장 횟수를 세고, [gate] 가 있으면 끝내라고 할 때까지 저장을 붙잡아 둔다.
class _CountingClosetStorage extends FakeClosetStorage {
  int saveCount = 0;
  Completer<void>? gate;

  Future<void> _hold() async {
    saveCount++;
    final pending = gate;
    if (pending != null) await pending.future;
  }

  @override
  Future<void> saveClothesList(List<Clothes> items) async {
    await _hold();
    return super.saveClothesList(items);
  }

  @override
  Future<void> saveClothesListFor(
    String ownerEmail,
    List<Clothes> items,
  ) async {
    await _hold();
    return super.saveClothesListFor(ownerEmail, items);
  }
}
