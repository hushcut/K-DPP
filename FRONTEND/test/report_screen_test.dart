import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/report_screen.dart';
import 'package:provider/provider.dart';
import 'helpers/fake_closet_storage.dart';

void main() {
  testWidgets('ReportScreen은 arguments가 없어도 currentReportItem을 표시한다',
      (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());

    final selected = Clothes(
      title: '테스트 코튼 후드',
      category: '상의',
      health: 82,
      materials: {'cotton': 80, 'polyester': 20},
      careInstruction: '찬물 세탁 후 자연 건조',
      carbonFootprint: 9.2,
    );

    await provider.addClothes(selected);

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: const MaterialApp(
          home: Scaffold(
            body: ReportScreen(),
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('테스트 코튼 후드'), findsOneWidget);
    expect(
      find.textContaining('의류 상태와 관리 가이드를 확인하세요.'),
      findsOneWidget,
    );
    expect(find.textContaining('라벨 지침: 찬물 세탁 후 자연 건조'), findsOneWidget);
    expect(find.text('찬물 세탁 후 자연 건조'), findsOneWidget);
    expect(find.textContaining('COTTON 80%'), findsWidgets);
  });
}
