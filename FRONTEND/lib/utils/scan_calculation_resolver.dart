import '../models/clothing_type_option.dart';
import 'clothing_estimator.dart';

enum ScanCalculationSource { server, localEstimate }

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

class ScanCalculationResolver {
  const ScanCalculationResolver._();

  static const String trustedServerCalculationMethod = 'weight_based_v1';

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
