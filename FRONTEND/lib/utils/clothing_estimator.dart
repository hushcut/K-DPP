import '../models/clothing_type_option.dart';

class ClothingEstimator {
  const ClothingEstimator._();

  static const Map<String, double> _localCarbonFactors = {
    'cotton': 8.1,
    '면': 8.1,
    'polyester': 11.9,
    '폴리에스터': 11.9,
    'nylon': 11.0,
    '나일론': 11.0,
    'rayon': 6.4,
    '레이온': 6.4,
    'viscose': 6.4,
    '비스코스': 6.4,
    'spandex': 12.0,
    'elastane': 12.0,
    '스판덱스': 12.0,
    'polyurethane': 12.0,
    '폴리우레탄': 12.0,
    'wool': 13.9,
    '울': 13.9,
  };

  static double calculateMaterialsTotal(Map<String, double> materials) {
    return materials.values.fold(0.0, (sum, value) => sum + value);
  }

  static bool isMaterialsTotalValid(Map<String, double> materials) {
    final total = calculateMaterialsTotal(materials);
    return total >= 99.5 && total <= 100.5;
  }

  static int estimateInitialHealth(Map<String, double> materials) {
    if (materials.isEmpty) return 80;

    double score = 80.0;
    final keys = materials.keys.map((e) => e.toLowerCase()).toList();

    if (materials.length == 1) score += 8;
    if (materials.length >= 3) score -= 8;

    if (keys.any((e) => e.contains('cotton') || e.contains('linen'))) {
      score += 5;
    }

    if (keys.any((e) => e.contains('silk') || e.contains('wool'))) {
      score -= 5;
    }

    if (keys.any((e) => e.contains('polyurethane') || e.contains('spandex'))) {
      score -= 3;
    }

    final clamped = score.round().clamp(60, 95);
    return clamped.toInt();
  }

  static double estimateCarbonFootprint(
    Map<String, double> materials,
    ClothingTypeOption clothingType,
  ) {
    if (materials.isEmpty) return 0;

    final total = calculateMaterialsTotal(materials);
    if (total <= 0) return 0;

    var mixedFactor = 0.0;
    for (final entry in materials.entries) {
      final normalizedName = entry.key.trim().toLowerCase();
      final factor = _localCarbonFactors[normalizedName] ?? 8.0;
      mixedFactor += factor * (entry.value / total);
    }

    final footprint = mixedFactor * clothingType.estimatedWeightGram / 1000;
    return double.parse(footprint.toStringAsFixed(1));
  }
}
