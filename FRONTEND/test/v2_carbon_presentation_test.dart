import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/home_screen.dart';
import 'package:k_dpp/material_name_display_provider.dart';
import 'package:k_dpp/models/analysis_history_record.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/report_screen.dart';
import 'package:k_dpp/services/carbon_api_service.dart';
import 'package:provider/provider.dart';

import 'helpers/fake_closet_storage.dart';
import 'helpers/report_basis.dart';

const source =
    'IDEMAT 2026 RevB2; data from www.ecocostsvalue.com · 정책 2026-10-18-v1';

Clothes garment({bool v2 = true, double carbon = 0.85}) => Clothes(
  title: '테스트 의류',
  category: '상의',
  health: 80,
  materials: {'cotton': 60, 'polyester': 40},
  careInstruction: '찬물 세탁',
  carbonFootprint: carbon,
  carbonFootprintSource: CarbonFootprintSource.server,
  savedResultId: 123,
  minWeightGram: 500,
  maxWeightGram: 500,
  calculationScope: v2 ? 'fiber_production_estimate' : null,
  calculationSource: v2 ? source : null,
  calculationBasis: v2 ? '혼용률 × 계수 × 무게 ÷ 1000' : null,
  calculationNote: v2 ? '무료 교육용 추정치. 폴리에스터는 버진 필라멘트 대체값입니다.' : null,
);

Widget host(ClosetProvider provider, Widget child) => MultiProvider(
  providers: [
    ChangeNotifierProvider.value(value: provider),
    ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
  ],
  child: MaterialApp(home: Scaffold(body: child)),
);

void main() {
  // 출처('data from www.ecocostsvalue.com')는 IDEMAT 를 쓰는 조건이라 접지 않고 한 번만 보인다.
  // 무료 교육용 제한·폴리에스터 가정은 '계산 기준 보기' 안에 있다(DECISIONS 2026-11-07).
  testWidgets('V2 출처는 접지 않고 한 번 보이고, 무료 교육용 안내는 계산 기준 안에 있다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    await provider.addClothes(garment());
    await tester.pumpWidget(host(provider, const ReportScreen()));
    await tester.pumpAndSettle();
    expect(find.text('출처: $source', skipOffstage: false), findsOneWidget);
    expect(find.textContaining('ecocostsvalue', skipOffstage: false), findsOneWidget);
    expect(
      find.textContaining('무료 교육용 추정치', skipOffstage: false),
      findsNothing,
    );

    await openCalculationBasis(tester);
    expect(
      find.textContaining('무료 교육용 추정치', skipOffstage: false),
      findsOneWidget,
    );
    // 계산식은 무게 줄과 겹쳐 보이지 않는다.
    expect(find.text('혼용률 × 계수 × 무게 ÷ 1000', skipOffstage: false), findsNothing);
    expect(find.textContaining('K-DPP 소재별', skipOffstage: false), findsNothing);
    expect(find.text('백엔드 계산값', skipOffstage: false), findsNothing);
    expect(tester.takeException(), isNull);
  });

  // '섬유'는 원단(textile)으로도 읽혀 실제보다 넓게 계산한 것처럼 보이므로, 범위 줄은 이름 대신
  // 들어간 것과 빠진 것을 적는다(DECISIONS 2026-11-07).
  testWidgets('V2 범위 줄은 원료에서 섬유까지이고 실·원단·염색·봉제가 빠졌다고 알린다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    await provider.addClothes(garment());
    await tester.pumpWidget(host(provider, const ReportScreen()));
    await tester.pumpAndSettle();
    await openCalculationBasis(tester);
    expect(
      find.text('범위: 원료에서 섬유까지(실·원단 만들기, 염색, 봉제는 빠짐)', skipOffstage: false),
      findsOneWidget,
    );
    expect(find.textContaining('섬유 생산 단계', skipOffstage: false), findsNothing);
  });

  // 서버 안내문이 '총무게를 섬유 무게로 가정'을 이미 말하면 앱 가정 문장은 되풀이하지 않고,
  // 안내문이 없으면 앱 문장이 그 가정을 알린다(DECISIONS 2026-11-07).
  testWidgets('총무게를 섬유 무게로 가정한다는 말은 계산 기준 안에서 한 번만 나온다', (tester) async {
    const assumption = '총무게를 섬유 무게로';
    for (final note in [
      '총무게를 섬유 무게로 가정한 추정치입니다. 무료 교육용 추정치입니다.',
      null,
    ]) {
      final item = garment();
      final provider = ClosetProvider(storage: FakeClosetStorage());
      await provider.addClothes(
        Clothes.fromJson({...item.toJson(), 'calculationNote': note}),
      );
      await tester.pumpWidget(host(provider, const ReportScreen()));
      await tester.pumpAndSettle();
      await openCalculationBasis(tester);
      expect(
        find.textContaining(assumption, skipOffstage: false),
        findsOneWidget,
        reason: 'note=$note',
      );
      await tester.pumpWidget(const SizedBox.shrink());
    }
  });

  testWidgets('옛 결과에 IDEMAT 출처를 소급 적용하지 않는다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    await provider.addClothes(garment(v2: false, carbon: 7.5));
    await tester.pumpWidget(host(provider, const ReportScreen()));
    await tester.pumpAndSettle();
    expect(find.textContaining('IDEMAT', skipOffstage: false), findsNothing);
    expect(
      find.text('출처: 기존 서버 계산 · 계수 출처 미확인', skipOffstage: false),
      findsOneWidget,
    );
    expect(provider.items.single.carbonFootprint, 7.5);
  });

  testWidgets('홈에서 기존 추정과 V2를 합산하지 않고 별도로 보여 준다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    await provider.addClothes(garment());
    await provider.addClothes(garment(v2: false, carbon: 7.5));
    await tester.pumpWidget(host(provider, const HomeScreen()));
    await tester.pumpAndSettle();
    expect(find.text('계산 기준별 탄소 현황'), findsOneWidget);
    expect(find.textContaining('서로의 차이는 감축량이 아닙니다.'), findsOneWidget);
    expect(find.text('8.3'), findsNothing);
    expect(find.text('0.8'), findsOneWidget);
    expect(find.text('7.5'), findsOneWidget);
  });

  test('이력의 출처가 숫자 변경 없이도 동기화되고 저장·복원된다', () async {
    final storage = FakeClosetStorage();
    final provider = ClosetProvider(storage: storage);
    await provider.addClothes(garment(v2: false));
    final record = AnalysisHistoryRecord.fromJson({
      'id': 123,
      'materials': {'cotton': 60, 'polyester': 40},
      'carbon_footprint': 0.85,
      'min_weight_grams': 500,
      'max_weight_grams': 500,
      'calculation_scope': 'fiber_production_estimate',
      'calculation_source': source,
    });
    expect(await provider.synchronizeServerHistory([record]), 1);
    expect(provider.items.single.calculationSource, source);
    expect(await provider.synchronizeServerHistory([record]), 0);
    final restored = Clothes.fromJson(provider.items.single.toJson());
    expect(restored.calculationSource, source);
    expect(restored.calculationScope, 'fiber_production_estimate');
  });

  test('미등록 V2 정책 오류는 임시값 저장으로 숨기지 않는다', () {
    final error = CarbonApiException.fromStatusCode(
      statusCode: 503,
      responseBody: '{"error_code":"CALCULATION_PROFILE_UNAVAILABLE"}',
    );
    expect(error.blocksLocalEstimate, isTrue);
    expect(error.userMessage, contains('저장하지 못했어요'));
    expect(error.userMessage, isNot(contains('저장했어요')));
  });
}
