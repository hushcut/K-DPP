import '../models/clothes.dart';
import '../models/clothing_type_option.dart';
import '../utils/clothing_estimator.dart';
import '../utils/scan_calculation_resolver.dart';

sealed class ScanSaveResult {
  const ScanSaveResult();
}

class ScanSaveSuccess extends ScanSaveResult {
  const ScanSaveSuccess(this.clothes);

  final Clothes clothes;
}

class ScanSaveFailure extends ScanSaveResult {
  const ScanSaveFailure(this.message);

  final String message;
}

class ScanSaveService {
  const ScanSaveService();

  ScanSaveResult buildClothes({
    required String title,
    required String category,
    required Map<String, double> materials,
    required String careInstruction,
    required ClothingTypeOption clothingType,
    Map<String, double> originalMaterials = const {},
    int? serverHealth,
    double? serverCarbonFootprint,
    double? serverWeightGram,
    String? serverCalculationMethod,
  }) {
    if (materials.isEmpty) {
      return const ScanSaveFailure('소재를 1개 이상 추가해 주세요.');
    }

    final total = ClothingEstimator.calculateMaterialsTotal(materials);

    if (!ClothingEstimator.isMaterialsTotalValid(materials)) {
      return ScanSaveFailure(
        '소재 비율 합계가 100%가 되도록 맞춰 주세요. (현재 ${total.toStringAsFixed(1)}%)',
      );
    }

    final calculation = ScanCalculationResolver.resolve(
      materials: materials,
      clothingType: clothingType,
      originalMaterials: originalMaterials,
      serverHealth: serverHealth,
      serverCarbonFootprint: serverCarbonFootprint,
      serverWeightGram: serverWeightGram,
      serverCalculationMethod: serverCalculationMethod,
    );

    return ScanSaveSuccess(
      Clothes(
        title: title.trim(),
        category: category,
        health: calculation.health,
        materials: materials,
        careInstruction: careInstruction,
        carbonFootprint: calculation.carbonFootprint,
        carbonFootprintSource: calculation.usesServerCarbon
            ? CarbonFootprintSource.server
            : CarbonFootprintSource.localEstimate,
        minWeightGram: clothingType.minWeightGram,
        maxWeightGram: clothingType.maxWeightGram,
      ),
    );
  }
}
