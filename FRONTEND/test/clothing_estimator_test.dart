import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/models/clothing_type_option.dart';
import 'package:k_dpp/utils/clothing_estimator.dart';

void main() {
  const clothingType = ClothingTypeOption(
    label: 'Test top',
    category: 'Top',
    weightRangeLabel: '500g',
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

  test('estimateCarbonFootprint uses material ratio and clothing weight', () {
    final carbon = ClothingEstimator.estimateCarbonFootprint({
      'cotton': 80,
      'polyester': 20,
    }, clothingType);

    expect(carbon, 4.4);
  });

  test('estimateInitialHealth keeps existing material scoring behavior', () {
    final health = ClothingEstimator.estimateInitialHealth({
      'cotton': 80,
      'polyester': 20,
    });

    expect(health, 85);
  });
}
