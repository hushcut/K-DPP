import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/closet_screen.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:provider/provider.dart';

import 'helpers/fake_closet_storage.dart';

void main() {
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
}
