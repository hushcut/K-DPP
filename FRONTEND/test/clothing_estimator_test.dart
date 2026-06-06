import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/utils/clothing_estimator.dart';

void main() {
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

  test('estimateInitialHealth keeps existing material scoring behavior', () {
    final health = ClothingEstimator.estimateInitialHealth({
      'cotton': 80,
      'polyester': 20,
    });

    expect(health, 85);
  });
}
