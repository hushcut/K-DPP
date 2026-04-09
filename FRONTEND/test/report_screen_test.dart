import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/report_screen.dart';
import 'package:provider/provider.dart';

void main() {
  testWidgets('ReportScreen은 arguments가 없어도 currentReportItem을 표시한다',
          (tester) async {
        final provider = ClosetProvider();

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

        expect(find.text('홍길동님의 테스트 코튼 후드'), findsOneWidget);
        expect(find.textContaining('찬물 세탁 후 자연 건조'), findsOneWidget);
        expect(find.textContaining('COTTON 80%'), findsOneWidget);
      });
}