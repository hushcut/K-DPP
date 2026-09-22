import '../models/clothing_type_option.dart';
import 'clothing_estimator.dart';

/// 최종 지표가 서버 계산값인지 로컬 추정값인지 나타낸다.
enum ScanCalculationSource { server, localEstimate }

/// 선택된 건강 점수와 탄소 배출량 및 각 값의 출처를 묶은 결과다.
class ResolvedScanCalculation {
  const ResolvedScanCalculation({
    required this.health,
    required this.carbonFootprint,
    required this.healthSource,
    required this.carbonSource,
  });

  final int health;
  final double carbonFootprint;
  final ScanCalculationSource healthSource;
  final ScanCalculationSource carbonSource;

  bool get usesServerHealth => healthSource == ScanCalculationSource.server;

  bool get usesServerCarbon => carbonSource == ScanCalculationSource.server;
}

/// 스캔 이후 사용자가 편집한 데이터와 서버 원본을 비교해 신뢰 가능한 계산값을 선택한다.
class ScanCalculationResolver {
  const ScanCalculationResolver._();

  static const String trustedServerCalculationMethod = 'weight_based_v1';

  /// 소재 동일성과 건강 점수·탄소값별 유효 조건을 검사해 사용할 값을 선택한다.
  /// 조건을 만족하지 않은 지표만 [ClothingEstimator]의 로컬 계산으로 대체한다.
  static ResolvedScanCalculation resolve({
    required Map<String, double> materials,
    required ClothingTypeOption clothingType,
    Map<String, double> originalMaterials = const {},
    int? serverHealth,
    double? serverCarbonFootprint,
    double? serverWeightGram,
    String? serverCalculationMethod,
  }) {
    final materialsAreUnchanged = _materialsMatch(materials, originalMaterials);
    final canUseServerHealth =
        materialsAreUnchanged &&
        serverHealth != null &&
        serverHealth >= 0 &&
        serverHealth <= 100;
    final canUseServerCarbon =
        materialsAreUnchanged &&
        serverCarbonFootprint != null &&
        serverCarbonFootprint > 0 &&
        serverWeightGram != null &&
        serverWeightGram > 0 &&
        serverCalculationMethod == trustedServerCalculationMethod &&
        (serverWeightGram - clothingType.estimatedWeightGram).abs() <= 0.5;

    return ResolvedScanCalculation(
      health: canUseServerHealth
          ? serverHealth
          : ClothingEstimator.estimateInitialHealth(materials),
      carbonFootprint: canUseServerCarbon
          ? serverCarbonFootprint
          : ClothingEstimator.estimateCarbonFootprint(materials, clothingType),
      healthSource: canUseServerHealth
          ? ScanCalculationSource.server
          : ScanCalculationSource.localEstimate,
      carbonSource: canUseServerCarbon
          ? ScanCalculationSource.server
          : ScanCalculationSource.localEstimate,
    );
  }

  static bool _materialsMatch(
    Map<String, double> current,
    Map<String, double> original,
  ) {
    if (current.isEmpty || original.isEmpty) return false;

    final normalizedCurrent = _normalizeMaterials(current);
    final normalizedOriginal = _normalizeMaterials(original);

    if (normalizedCurrent.length != normalizedOriginal.length) return false;

    for (final entry in normalizedOriginal.entries) {
      final currentPercentage = normalizedCurrent[entry.key];

      if (currentPercentage == null ||
          (currentPercentage - entry.value).abs() > 0.05) {
        return false;
      }
    }

    return true;
  }

  static Map<String, double> _normalizeMaterials(
    Map<String, double> materials,
  ) {
    final normalized = <String, double>{};

    materials.forEach((name, percentage) {
      final normalizedName = name.trim().toLowerCase();

      if (normalizedName.isEmpty) return;

      normalized.update(
        normalizedName,
        (value) => value + percentage,
        ifAbsent: () => percentage,
      );
    });

    return normalized;
  }
}
