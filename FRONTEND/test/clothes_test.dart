import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/models/clothes.dart';

void main() {
  test('keeps the carbon calculation source through JSON storage', () {
    final clothes = Clothes(
      title: '홍길동 코튼 셔츠',
      category: '상의',
      health: 85,
      materials: const {'cotton': 100},
      careInstruction: '찬물 세탁',
      carbonFootprint: 3.2,
      carbonFootprintSource: CarbonFootprintSource.server,
      carbonFootprintMin: 2.4,
      carbonFootprintMax: 4.0,
      minWeightGram: 300,
      maxWeightGram: 500,
      savedResultId: 17,
    );

    final restored = Clothes.fromJson(clothes.toJson());

    expect(restored.carbonFootprint, 3.2);
    expect(restored.carbonFootprintSource, CarbonFootprintSource.server);
    expect(restored.carbonFootprintMin, 2.4);
    expect(restored.carbonFootprintMax, 4.0);
    expect(restored.minWeightGram, 300);
    expect(restored.maxWeightGram, 500);
    expect(restored.savedResultId, 17);
  });

  test('treats legacy stored clothes as a local estimate', () {
    final restored = Clothes.fromJson({
      'title': '홍길동 기존 의류',
      'category': '상의',
      'health': 80,
      'materials': {'cotton': 100},
      'careInstruction': '찬물 세탁',
      'carbonFootprint': 2.4,
    });

    expect(restored.carbonFootprintSource, CarbonFootprintSource.localEstimate);
  });

  test('서버 계산 기준 필드는 저장·복원을 거쳐도 유지된다', () {
    final clothes = Clothes(
      title: '홍길동 계산 기준 셔츠',
      category: '상의',
      health: 88,
      materials: {'cotton': 100},
      careInstruction: '찬물 세탁',
      carbonFootprint: 4.2,
      weightSource: 'category_average',
      calculationScope: 'material_production_estimate',
      calculationBasis: '소재 배출계수 × 의류 무게',
      calculationSource: '소재별 공개 배출계수 정리표',
      calculationNote: '운송·사용 단계는 포함하지 않습니다.',
    );

    final restored = Clothes.fromJson(clothes.toJson());

    expect(restored.weightSource, 'category_average');
    expect(restored.calculationScope, 'material_production_estimate');
    expect(restored.calculationBasis, '소재 배출계수 × 의류 무게');
    expect(restored.calculationSource, '소재별 공개 배출계수 정리표');
    expect(restored.calculationNote, '운송·사용 단계는 포함하지 않습니다.');
  });
}
