import '../models/clothing_type_option.dart';

/// 소재 비율과 의류의 추정 무게를 이용해 저장 전 기본 지표를 계산한다.
class ClothingEstimator {
  const ClothingEstimator._();

  /// 입력된 모든 소재 비율의 합을 계산한다.
  static double calculateMaterialsTotal(Map<String, double> materials) {
    return materials.values.fold(0.0, (sum, value) => sum + value);
  }

  /// 소재 합계가 허용 범위인 99.5~100.5%인지 검사한다.
  static bool isMaterialsTotalValid(Map<String, double> materials) {
    final total = calculateMaterialsTotal(materials);
    return total >= 99.5 && total <= 100.5;
  }

  /// 소재별 배출계수와 의류 무게를 가중 합산해 탄소 배출량을 추정한다.
  /// 소재가 없거나 알 수 없는 경우에는 기본 배출계수를 사용한다.
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

  /// 소재 구성의 단순성 및 소재 종류에 따라 초기 건강 점수를 60~95로 산정한다.
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
