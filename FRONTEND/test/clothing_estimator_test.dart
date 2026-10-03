import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/models/clothing_type_option.dart';
import 'package:k_dpp/utils/clothing_estimator.dart';

void main() {
  const clothingType = ClothingTypeOption(
    label: 'Test top',
    category: 'Top',
    minWeightGram: 500,
    maxWeightGram: 500,
    estimatedWeightGram: 500,
    icon: Icons.checkroom_outlined,
  );

  test('calculateMaterialsTotal returns summed material percentages', () {
    final total = ClothingEstimator.calculateMaterialsTotal({
      'cotton': 80,
      'polyester': 20,
    });

    expect(total, 100);
  });

  test('isMaterialsTotalValid allows small rounding differences', () {
    expect(
      ClothingEstimator.isMaterialsTotalValid({
        'cotton': 66.7,
        'polyester': 33.3,
      }),
      isTrue,
    );
  });

  test('isMaterialsTotalOver is true only above the 100.5 tolerance', () {
    expect(
      ClothingEstimator.isMaterialsTotalOver({'cotton': 60, 'polyester': 40.5}),
      isFalse,
    );
    expect(
      ClothingEstimator.isMaterialsTotalOver({'cotton': 60, 'polyester': 40.6}),
      isTrue,
    );
  });

  test('estimateCarbonFootprint uses material ratio and clothing weight', () {
    // 서버 시드 계수 기준: (0.8 × 8.3 + 0.2 × 9.5) × 0.5kg = 4.27
    final carbon = ClothingEstimator.estimateCarbonFootprint({
      'cotton': 80,
      'polyester': 20,
    }, clothingType);

    expect(carbon, 4.3);
  });

  test('estimateInitialHealth keeps existing material scoring behavior', () {
    final health = ClothingEstimator.estimateInitialHealth({
      'cotton': 80,
      'polyester': 20,
    });

    expect(health, 85);
  });

  // 프론트 계수표는 서버 시드(BACKEND/init_data.py MATERIAL_SEEDS)의 사본이다.
  // 두 표가 어긋나는지는 BACKEND/tests/test_material_name_contract.py가 검사한다.
  // 여기서는 그 숫자가 실제 계산에 쓰이는지를 확인한다.
  group('서버 시드 계수 반영', () {
    const serverFactors = <String, double>{
      'cotton': 8.3,
      'polyester': 9.5,
      'rayon': 6.4,
      'nylon': 11.0,
      'wool': 13.9,
      'acrylic': 10.0,
      'spandex': 12.0,
      'linen': 4.5,
      'viscose': 6.4,
      'silk': 15.0,
      'modal': 6.0,
      'cashmere': 30.0,
      'polyurethane': 12.0,
      'leather': 20.0,
      'ramie': 4.5,
      'lyocell': 5.5,
      'down': 18.0,
      'feather': 12.0,
      'yak': 18.0,
      'mohair': 18.0,
      'bamboo': 5.0,
      'cupro': 6.0,
    };

    test('22종 모두 서버 계수 × 무게로 계산된다', () {
      serverFactors.forEach((name, factor) {
        final expected = double.parse((factor * 0.5).toStringAsFixed(1));

        expect(
          ClothingEstimator.estimateCarbonFootprint({name: 100}, clothingType),
          expected,
          reason: '$name 의 계수가 서버 시드($factor)와 다릅니다.',
        );
      });
    });

    test('프론트에 분기가 없던 소재도 기본계수로 떨어지지 않는다', () {
      // 캐시미어는 서버 30.0인데 기본계수 10.0으로 계산돼 실제의 1/3이 나왔다.
      expect(
        ClothingEstimator.estimateCarbonFootprint({
          'cashmere': 100,
        }, clothingType),
        15.0,
      );
      expect(
        ClothingEstimator.estimateCarbonFootprint({'다운': 100}, clothingType),
        9.0,
      );
      expect(
        ClothingEstimator.estimateCarbonFootprint({'가죽': 100}, clothingType),
        10.0,
      );
    });

    test('서버에 없는 소재는 기본계수를 쓴다', () {
      // 서버가 400 MATERIAL_NOT_FOUND로 거부하는 이름들이다.
      // 프론트만 알아보면 프리뷰는 뜨는데 저장이 실패하는 어긋남이 생긴다.
      for (final name in const [
        'organic cotton',
        'recycled polyester',
        '알 수 없는 소재',
      ]) {
        expect(
          ClothingEstimator.estimateCarbonFootprint({name: 100}, clothingType),
          5.0,
          reason: '$name 은 기본계수 10.0 × 0.5kg = 5.0이어야 합니다.',
        );
      }
    });
  });

  // 스캔 성공 경로는 서버가 정규화한 한글 표시명('면'·'울')을 그대로 소재 키로
  // 쓰므로, 영문 이름만 알아보면 모든 스캔 의류가 기본계수로 계산된다.
  group('서버 한글 소재명 해석', () {
    // 서버 시드의 한글명·별칭 → 영문 표준명 대응이다.
    const aliasPairs = <String, String>{
      '면': 'cotton',
      '코튼': 'cotton',
      '폴리에스터': 'polyester',
      'poly': 'polyester',
      '레이온': 'rayon',
      '나일론': 'nylon',
      'polyamide': 'nylon',
      '울': 'wool',
      '모': 'wool',
      '아크릴': 'acrylic',
      '스판덱스': 'spandex',
      '엘라스테인': 'spandex',
      'lycra': 'spandex',
      '린넨': 'linen',
      '마': 'linen',
      '실크': 'silk',
      '견': 'silk',
      '비스코스': 'viscose',
      '모달': 'modal',
      '캐시미어': 'cashmere',
      '폴리우레탄': 'polyurethane',
      'pu': 'polyurethane',
      '가죽': 'leather',
      '라미': 'ramie',
      '텐셀': 'lyocell',
      '다운': 'down',
      '깃털': 'feather',
      '야크': 'yak',
      '모헤어': 'mohair',
      '대나무': 'bamboo',
      '큐프로': 'cupro',
    };

    test('별칭은 영문 표준명과 같은 배출계수·건강도를 낸다', () {
      aliasPairs.forEach((alias, standardName) {
        expect(
          ClothingEstimator.estimateCarbonFootprint({alias: 100}, clothingType),
          ClothingEstimator.estimateCarbonFootprint({
            standardName: 100,
          }, clothingType),
          reason: '$alias 의 배출계수가 $standardName 과 다릅니다.',
        );
        expect(
          ClothingEstimator.estimateInitialHealth({alias: 100}),
          ClothingEstimator.estimateInitialHealth({standardName: 100}),
          reason: '$alias 의 건강도가 $standardName 과 다릅니다.',
        );
      });
    });

    test('한글명이 기본계수로 뭉개지지 않는다', () {
      // 500g · 100%이므로 계수 × 0.5가 그대로 나온다. 기본계수라면 전부 5.0이다.
      expect(
        ClothingEstimator.estimateCarbonFootprint({'면': 100}, clothingType),
        4.2,
      );
      expect(
        ClothingEstimator.estimateCarbonFootprint({'울': 100}, clothingType),
        7.0,
      );
      expect(
        ClothingEstimator.estimateCarbonFootprint({'린넨': 100}, clothingType),
        2.3,
      );
      expect(ClothingEstimator.estimateInitialHealth({'면': 100}), 93);
      expect(ClothingEstimator.estimateInitialHealth({'울': 100}), 83);
      expect(ClothingEstimator.estimateInitialHealth({'스판덱스': 100}), 85);
    });

    // 서버 별칭 '모'(울)는 '모달'·'모헤어'의 부분 문자열이다. 부분 일치로 찾으면
    // 모달 니트가 울로 계산된다.
    test("'모'로 시작하는 다른 소재를 울로 오인하지 않는다", () {
      expect(
        ClothingEstimator.estimateCarbonFootprint({'모달': 100}, clothingType),
        3.0,
      );
      expect(
        ClothingEstimator.estimateCarbonFootprint({'모헤어': 100}, clothingType),
        9.0,
      );
      expect(ClothingEstimator.estimateInitialHealth({'모달': 100}), 88);
    });

    // 사용자가 스캔이 채운 '면' 행 옆에 자동완성으로 'cotton' 행을 더할 수 있다.
    // 개수를 원문 키로 세면 100% 면인데 2종으로 계산돼 단일 소재 가점(+8)을 잃는다.
    // 서버는 둘 다 cotton으로 풀어 저장을 통과시키므로 어긋난 건강도만 남는다.
    test('같은 소재를 두 이름으로 적어도 한 종으로 센다', () {
      expect(
        ClothingEstimator.estimateInitialHealth({'면': 50, 'cotton': 50}),
        ClothingEstimator.estimateInitialHealth({'cotton': 100}),
      );
      expect(
        ClothingEstimator.estimateInitialHealth({'면': 50, 'cotton': 50}),
        93,
      );
      // 서로 다른 소재는 그대로 2종으로 센다.
      expect(
        ClothingEstimator.estimateInitialHealth({'면': 50, '폴리에스터': 50}),
        85,
      );
      // 3종 감점도 표준명 기준이다.
      expect(
        ClothingEstimator.estimateInitialHealth({
          '면': 40,
          'cotton': 20,
          '울': 20,
          '나일론': 20,
        }),
        ClothingEstimator.estimateInitialHealth({
          'cotton': 60,
          'wool': 20,
          'nylon': 20,
        }),
      );
    });

    test('앞뒤 공백과 대문자 표기를 정리한 뒤 찾는다', () {
      expect(
        ClothingEstimator.estimateCarbonFootprint({' 면 ': 100}, clothingType),
        4.2,
      );
      expect(
        ClothingEstimator.estimateCarbonFootprint({'PU': 100}, clothingType),
        6.0,
      );
    });
  });
}
