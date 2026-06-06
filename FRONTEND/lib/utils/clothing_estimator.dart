class ClothingEstimator {
  const ClothingEstimator._();

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
}
