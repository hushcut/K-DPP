import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/report_screen.dart';
import 'package:provider/provider.dart';
import 'helpers/fake_closet_storage.dart';

void main() {
  testWidgets('ReportScreen은 arguments가 없어도 currentReportItem을 표시한다', (
    tester,
  ) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());

    final selected = Clothes(
      title: '테스트 코튼 후드',
      category: '상의',
      health: 82,
      materials: {'cotton': 80, 'polyester': 20},
      careInstruction: '찬물 세탁 후 자연 건조',
      carbonFootprint: 9.2,
      carbonFootprintSource: CarbonFootprintSource.server,
      calculationScope: 'material_production_estimate',
      calculationSource: 'K-DPP 소재 배출계수 표',
      calculationNote: '개발용 추정값입니다.',
    );

    await provider.addClothes(selected);

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: const MaterialApp(home: Scaffold(body: ReportScreen())),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('테스트 코튼 후드'), findsOneWidget);
    expect(
      find.textContaining('소재 정보와 원료·소재 생산 단계 탄소 추정값을 확인하세요.'),
      findsOneWidget,
    );
    expect(find.text('현재 건강 상태'), findsNothing);
    expect(find.textContaining('단계별 탄소 배출량'), findsNothing);
    expect(find.text('원료·소재 생산 단계 탄소 배출량'), findsOneWidget);
    expect(find.text('탄소 배출량 체감'), findsOneWidget);
    expect(find.textContaining('전체 생애주기 배출량이 아닙니다'), findsOneWidget);
    expect(find.text('자동차'), findsOneWidget);
    expect(find.text('스마트폰'), findsOneWidget);
    expect(find.text('LED 전구'), findsOneWidget);
    expect(find.text('계산 범위: 원료·소재 생산 단계 중심 추정'), findsOneWidget);
    expect(find.text('계산 출처: K-DPP 소재 배출계수 표'), findsOneWidget);
    expect(find.textContaining('라벨 지침: 찬물 세탁 후 자연 건조'), findsOneWidget);
    expect(find.text('찬물 세탁 후 자연 건조'), findsOneWidget);
    expect(find.textContaining('면 80%'), findsWidgets);
  });

  testWidgets('내장 리포트에서 의류를 삭제하면 콜백으로 옷장 화면 복귀를 요청한다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    final selected = Clothes(
      title: '삭제 테스트 셔츠',
      category: '상의',
      health: 75,
      materials: {'cotton': 100},
      careInstruction: '찬물 세탁',
      carbonFootprint: 5.0,
    );
    var deleteCallbackCount = 0;

    await provider.addClothes(selected);

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          home: Scaffold(
            body: ReportScreen(
              onDeleted: () {
                deleteCallbackCount++;
              },
            ),
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('이 의류 삭제하기'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('이 의류 삭제하기'));
    await tester.pumpAndSettle();

    expect(find.text('의류 삭제'), findsOneWidget);

    await tester.tap(find.widgetWithText(ElevatedButton, '삭제'));
    await tester.pumpAndSettle();

    expect(provider.items.contains(selected), isFalse);
    expect(deleteCallbackCount, 1);
  });

  testWidgets('긴 소재명과 큰 글자에서도 리포트 요약 카드가 넘치지 않는다', (tester) async {
    tester.view.physicalSize = const Size(320, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final provider = ClosetProvider(storage: FakeClosetStorage());
    final selected = Clothes(
      title: '긴 이름의 테스트용 친환경 혼방 아우터',
      category: '상의',
      health: 82,
      materials: {
        'recycled polyester with long material name': 70,
        'organic cotton': 30,
      },
      careInstruction: '찬물에서 단독 세탁 후 그늘에서 자연 건조해 주세요.',
      carbonFootprint: 12.4,
    );
    await provider.addClothes(selected);

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: const MaterialApp(
          home: MediaQuery(
            data: MediaQueryData(textScaler: TextScaler.linear(1.6)),
            child: Scaffold(body: ReportScreen()),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('긴 이름의 테스트용 친환경 혼방 아우터'), findsOneWidget);
  });
}
