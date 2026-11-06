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
  testWidgets('두 출처 영역 모두 실제 V2 문헌과 정책 버전을 표시한다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    await provider.addClothes(garment());
    await tester.pumpWidget(host(provider, const ReportScreen()));
    await tester.pumpAndSettle();
    expect(find.text('출처: $source', skipOffstage: false), findsOneWidget);
    expect(find.text(source, skipOffstage: false), findsOneWidget);
    expect(
      find.textContaining('무료 교육용 추정치', skipOffstage: false),
      findsOneWidget,
    );
    expect(find.textContaining('K-DPP 소재별', skipOffstage: false), findsNothing);
    expect(find.text('백엔드 계산값', skipOffstage: false), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('옛 결과에 IDEMAT 출처를 소급 적용하지 않는다', (tester) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    await provider.addClothes(garment(v2: false, carbon: 7.5));
    await tester.pumpWidget(host(provider, const ReportScreen()));
    await tester.pumpAndSettle();
    expect(find.textContaining('IDEMAT', skipOffstage: false), findsNothing);
    expect(
      find.text('기존 서버 계산 · 계수 출처 미확인', skipOffstage: false),
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
