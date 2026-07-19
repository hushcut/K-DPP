import '../models/clothes.dart';
import '../models/clothing_type_option.dart';
import '../utils/clothing_estimator.dart';
import '../utils/scan_calculation_resolver.dart';

/// 스캔 결과를 의류 모델로 변환한 결과를 성공과 실패로 구분한다.
sealed class ScanSaveResult {
  const ScanSaveResult();
}

/// 소재 합계 확인과 계산을 거쳐 생성된 [Clothes]를 담는 상태다.
class ScanSaveSuccess extends ScanSaveResult {
  const ScanSaveSuccess(this.clothes);

  final Clothes clothes;
}

/// 소재 입력이 저장 조건을 충족하지 못한 상태와 사용자 안내 문구를 담는다.
class ScanSaveFailure extends ScanSaveResult {
  const ScanSaveFailure(this.message);

  final String message;
}

/// 편집된 소재 구성을 확인하고 최종 [Clothes] 객체를 조립한다.
class ScanSaveService {
  const ScanSaveService();

  /// 소재 합계를 검증한 뒤 서버값 또는 로컬 추정값을 선택해 저장 모델을 만든다.
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
