import 'package:flutter/material.dart';
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
}
