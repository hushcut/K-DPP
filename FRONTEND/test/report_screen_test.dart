import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/material_name_display_provider.dart';
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
    );

    await provider.addClothes(selected);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: provider),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
        ],
        child: const MaterialApp(home: Scaffold(body: ReportScreen())),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('테스트 코튼 후드'), findsOneWidget);
    expect(find.textContaining('소재 정보와 생산·제조 탄소 추정값을 확인하세요.'), findsOneWidget);
    expect(find.text('현재 건강 상태'), findsNothing);
    expect(find.textContaining('단계별 탄소 배출량'), findsNothing);
    expect(find.text('생산·제조 탄소 배출량'), findsOneWidget);
    expect(find.text('탄소 배출량 체감'), findsOneWidget);
    expect(find.text('계산 기준'), findsOneWidget);
    expect(find.text('앱 임시 추정값'), findsWidgets);
    expect(find.text('저장된 소재와 의류 유형 기준'), findsOneWidget);
    expect(find.textContaining('전체 생애주기 배출량이 아닙니다'), findsOneWidget);
    expect(find.text('자동차'), findsOneWidget);
    expect(find.text('스마트폰'), findsOneWidget);
    expect(find.text('LED 전구'), findsOneWidget);
    expect(find.textContaining('라벨 지침: 찬물 세탁 후 자연 건조'), findsOneWidget);
    expect(find.text('찬물 세탁 후 자연 건조'), findsOneWidget);
    // 소재 이름의 기본 표시 언어는 한글이다(D16). 영문 키로 저장된 옷도 한글명으로 보인다.
    expect(find.textContaining('면 80%'), findsWidgets);
  });

  // 2026-09-24 사용자 요청: 맞춤 관리 가이드를 탄소 배출량보다 위에 둔다.
  testWidgets('맞춤 관리 가이드는 요약 카드 아래, 생산·제조 탄소 배출량 위에 있다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    await provider.addClothes(
      Clothes(
        title: '순서 확인 셔츠',
        category: '상의',
        health: 82,
        materials: {'cotton': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 3.0,
      ),
    );

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: provider),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
        ],
        child: const MaterialApp(home: Scaffold(body: ReportScreen())),
      ),
    );
    await tester.pumpAndSettle();

    double top(String text) => tester.getTopLeft(find.text(text)).dy;

    expect(top('탄소 추정값'), lessThan(top('맞춤 관리 가이드')));
    expect(top('맞춤 관리 가이드'), lessThan(top('생산·제조 탄소 배출량')));
    expect(top('생산·제조 탄소 배출량'), lessThan(top('관리 정보')));
  });

  testWidgets('상세 리포트에서 의류 이름과 세탁 지침을 수정할 수 있다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());

    final selected = Clothes(
      title: '수정 전 셔츠',
      category: '상의',
      health: 82,
      materials: {'cotton': 100},
      careInstruction: '찬물 세탁',
      carbonFootprint: 3.2,
    );

    await provider.addClothes(selected);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: provider),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
        ],
        child: const MaterialApp(home: Scaffold(body: ReportScreen())),
      ),
    );

    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.edit_outlined));
    await tester.pumpAndSettle();

    expect(find.text('의류 정보 수정'), findsOneWidget);

    await tester.enterText(find.byType(TextFormField).first, '수정 후 셔츠');
    await tester.enterText(find.byType(TextFormField).last, '찬물 손세탁');
    await tester.tap(find.text('수정 완료'));
    await tester.pumpAndSettle();

    expect(provider.items.single.title, '수정 후 셔츠');
    expect(provider.items.single.careInstruction, '찬물 손세탁');
    expect(find.text('수정 후 셔츠'), findsOneWidget);
    expect(find.text('의류 정보가 수정되었습니다.'), findsOneWidget);
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
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: provider),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
        ],
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

    expect(provider.items, isEmpty);
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
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: provider),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
        ],
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

  // 리포트는 하단 메뉴까지 덮는 라우트라(6d9ed80) 예전 메뉴 자리 140 대신 안전 영역만 비운다.
  testWidgets('끝까지 내리면 삭제 버튼 아래 여백은 안전 영역 + 24다', (tester) async {
    tester.view.physicalSize = const Size(440, 956);
    tester.view.devicePixelRatio = 1;
    tester.view.padding = const FakeViewPadding(bottom: 34);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPadding);

    final provider = ClosetProvider(storage: FakeClosetStorage());
    await provider.addClothes(
      Clothes(
        title: '여백 확인용 셔츠',
        category: '상의',
        health: 82,
        materials: {'cotton': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 5.0,
      ),
    );

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: provider),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
        ],
        child: const MaterialApp(home: Scaffold(body: ReportScreen())),
      ),
    );
    await tester.pumpAndSettle();

    final scrollable = tester.state<ScrollableState>(
      find
          .descendant(
            of: find.byType(SingleChildScrollView),
            matching: find.byType(Scrollable),
          )
          .first,
    );
    scrollable.position.jumpTo(scrollable.position.maxScrollExtent);
    await tester.pump();

    final deleteButton = tester.getRect(
      find.widgetWithText(OutlinedButton, '이 의류 삭제하기'),
    );
    expect(956 - deleteButton.bottom, 34 + 24);
  });
}
