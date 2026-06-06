import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/models/clothing_type_option.dart';
import 'package:k_dpp/utils/scan_calculation_resolver.dart';

void main() {
  const clothingType = ClothingTypeOption(
    label: '긴팔 / 맨투맨',
    category: '상의',
    weightRangeLabel: '350~750g',
    estimatedWeightGram: 520,
    icon: Icons.checkroom_outlined,
  );
  const originalMaterials = {'cotton': 80.0, 'polyester': 20.0};

  test('uses server values when materials and weight still match', () {
    final result = ScanCalculationResolver.resolve(
      materials: originalMaterials,
      clothingType: clothingType,
      originalMaterials: originalMaterials,
      serverHealth: 91,
      serverCarbonFootprint: 7.25,
      serverWeightGram: 520,
      serverCalculationMethod: 'weight_based_v1',
    );

    expect(result.health, 91);
    expect(result.carbonFootprint, 7.25);
    expect(result.usesServerHealth, isTrue);
    expect(result.usesServerCarbon, isTrue);
  });

  test('uses local carbon when server response has no weight', () {
    final result = ScanCalculationResolver.resolve(
      materials: originalMaterials,
      clothingType: clothingType,
      originalMaterials: originalMaterials,
      serverHealth: 91,
      serverCarbonFootprint: 7.25,
    );

    expect(result.health, 91);
    expect(result.carbonFootprint, 4.6);
    expect(result.usesServerHealth, isTrue);
    expect(result.usesServerCarbon, isFalse);
  });

  test('uses local carbon when the server calculation method is missing', () {
    final result = ScanCalculationResolver.resolve(
      materials: originalMaterials,
      clothingType: clothingType,
      originalMaterials: originalMaterials,
      serverCarbonFootprint: 7.25,
      serverWeightGram: 520,
    );

    expect(result.carbonFootprint, 4.6);
    expect(result.usesServerCarbon, isFalse);
  });

  test('uses local values after materials are edited', () {
    final result = ScanCalculationResolver.resolve(
      materials: const {'cotton': 100},
      clothingType: clothingType,
      originalMaterials: originalMaterials,
      serverHealth: 91,
      serverCarbonFootprint: 7.25,
      serverWeightGram: 520,
      serverCalculationMethod: 'weight_based_v1',
    );

    expect(result.health, 93);
    expect(result.carbonFootprint, 4.2);
    expect(result.usesServerHealth, isFalse);
    expect(result.usesServerCarbon, isFalse);
  });

  test('keeps server health but recalculates carbon after weight changes', () {
    const changedWeightType = ClothingTypeOption(
      label: '직접 입력',
      category: '상의',
      weightRangeLabel: '600g',
      estimatedWeightGram: 600,
      icon: Icons.scale_outlined,
      isDirectWeight: true,
    );

    final result = ScanCalculationResolver.resolve(
      materials: originalMaterials,
      clothingType: changedWeightType,
      originalMaterials: originalMaterials,
      serverHealth: 91,
      serverCarbonFootprint: 7.25,
      serverWeightGram: 520,
      serverCalculationMethod: 'weight_based_v1',
    );

    expect(result.health, 91);
    expect(result.carbonFootprint, 5.3);
    expect(result.usesServerHealth, isTrue);
    expect(result.usesServerCarbon, isFalse);
  });
}
