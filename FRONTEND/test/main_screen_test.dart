import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/main_screen.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/models/main_screen_arguments.dart';
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
      ChangeNotifierProvider.value(
        value: provider,
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
      ChangeNotifierProvider.value(
        value: provider,
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
      ChangeNotifierProvider.value(
        value: provider,
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
}
