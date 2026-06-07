import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/main_screen.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/models/main_screen_arguments.dart';
import 'package:provider/provider.dart';

import 'helpers/fake_closet_storage.dart';

void main() {
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
