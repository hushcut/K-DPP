import '../models/clothing_type_option.dart';

class ClothingEstimator {
  const ClothingEstimator._();

  static double calculateMaterialsTotal(Map<String, double> materials) {
    return materials.values.fold(0.0, (sum, value) => sum + value);
  }

  static bool isMaterialsTotalValid(Map<String, double> materials) {
    final total = calculateMaterialsTotal(materials);
    return total >= 99.5 && total <= 100.5;
  }

  static double estimateCarbonFootprint(
    Map<String, double> materials,
    ClothingTypeOption clothingType,
  ) {
    final weightKg = clothingType.estimatedWeightGram / 1000;

    if (materials.isEmpty) {
      return double.parse((weightKg * 10.0).toStringAsFixed(1));
    }

    double totalPercent = calculateMaterialsTotal(materials);
    if (totalPercent <= 0) totalPercent = 100.0;

    double emission = 0.0;

    materials.forEach((material, percent) {
      final factor = _findMaterialEmissionFactor(material);
      emission += (percent / totalPercent) * weightKg * factor;
    });

    if (emission < 0.1) {
      emission = 0.1;
    }

    return double.parse(emission.toStringAsFixed(1));
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

  static double _findMaterialEmissionFactor(String material) {
    final m = material.toLowerCase();

    if (m.contains('organic cotton')) return 5.0;
    if (m.contains('cotton')) return 8.0;
    if (m.contains('linen')) return 6.0;
    if (m.contains('recycled polyester')) return 7.0;
    if (m.contains('polyester')) return 12.0;
    if (m.contains('nylon')) return 14.0;
    if (m.contains('wool')) return 25.0;
    if (m.contains('silk')) return 20.0;
    if (m.contains('viscose') || m.contains('rayon')) return 10.0;
    if (m.contains('polyurethane') || m.contains('spandex')) return 15.0;

    return 10.0;
  }
}
