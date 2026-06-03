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

  test('estimateCarbonFootprintRange uses category weight range', () {
    const rangedClothingType = ClothingTypeOption(
      label: 'Test top',
      category: 'Top',
      weightRangeLabel: '100~250g',
      estimatedWeightGram: 180,
      icon: Icons.checkroom_outlined,
    );

    final carbon = ClothingEstimator.estimateCarbonFootprintRange({
      'cotton': 100,
    }, rangedClothingType);

    expect(carbon.min, 0.8);
    expect(carbon.max, 2.0);
    expect(carbon.midpoint, 1.4);
    expect(carbon.displayText, '0.8~2.0 kg CO2eq');
  });

  test('estimateInitialHealth keeps existing material scoring behavior', () {
    final health = ClothingEstimator.estimateInitialHealth({
      'cotton': 80,
      'polyester': 20,
    });

    expect(health, 85);
  });
}
