import '../models/clothing_type_option.dart';
import 'material_name.dart';

/// 소재 비율과 의류의 추정 무게를 이용해 저장 전 기본 지표를 계산한다.
///
/// 아래 `_emissionFactorsByStandardName`는 **서버 소재 표
/// (`BACKEND/init_data.py`의 `MATERIAL_SEEDS`)의 `carbon_factor`를 그대로 옮긴 사본**이다.
/// 소재명을 표준명으로 되돌리는 표는 [MaterialName]에 있다(리포트·홈 화면도 같은 것을 쓴다).
/// 두 표가 서버와 어긋나면 `BACKEND/tests/test_material_name_contract.py`가 실패한다.
///
/// ⚠️ **이 동기화는 임시다.** 서버 시드의 `carbon_factor`는 그 파일 주석대로
/// "개발용 추정값, 최종 발표 전 팀 승인 출처로 교체" 상태다. 승인 출처가 정해지면
/// 서버가 먼저 바뀌고 여기가 따라와야 한다. 계수 정본을 서버 한 곳에 두고
/// 프론트가 `/materials`에서 받아 캐시하는 구조로 갈지는 미결(`NEXT_WORK.md` D08).
class ClothingEstimator {
  const ClothingEstimator._();

  /// 서버가 모르는 소재에 쓰는 배출계수다.
  /// 소재를 아직 하나도 넣지 않은 상태의 프리뷰에도 같은 값을 쓴다.
  ///
  /// ⚠️ **이 값은 프리뷰에서 끝나지 않는다.** 서버는 모르는 소재를
  /// 400 `MATERIAL_NOT_FOUND`로 거부하지만, `scan_save_actions.dart`의 저장 경로는
  /// 인증 오류가 아닌 서버 실패를 저장 중단 사유로 보지 않는다. 안내 문구만 띄우고
  /// **이 추정값 그대로 옷장에 저장**하며, 그 항목은 `savedResultId`가 null이라
  /// 서버 이력에 행이 없고 이후 동기화 갱신 대상도 되지 못한다
  /// (HANDOFF '발견했으나 미해결' 1번). 표시는 '임시 추정값'으로 정직하다.
  static const double defaultEmissionFactor = 10.0;

  /// 입력된 모든 소재 비율의 합을 계산한다.
  static double calculateMaterialsTotal(Map<String, double> materials) {
    return materials.values.fold(0.0, (sum, value) => sum + value);
  }

  // 소재 합계로 인정하는 범위다. 소수점 반올림 오차를 받아 준다.
  static const double _materialsTotalMin = 99.5;
  static const double _materialsTotalMax = 100.5;

  /// 소재 합계가 허용 범위인 99.5~100.5%인지 검사한다.
  static bool isMaterialsTotalValid(Map<String, double> materials) {
    final total = calculateMaterialsTotal(materials);
    return total >= _materialsTotalMin && total <= _materialsTotalMax;
  }

  /// 소재 합계가 허용 범위의 위쪽(100.5%)을 넘었는지 검사한다.
  /// 넘었으면 소재를 더 추가해도 합계를 맞출 수 없다.
  static bool isMaterialsTotalOver(Map<String, double> materials) {
    return calculateMaterialsTotal(materials) > _materialsTotalMax;
  }

  /// 소재별 배출계수와 의류 무게를 가중 합산해 탄소 배출량을 추정한다.
  /// 소재가 없거나 알 수 없는 경우에는 기본 배출계수를 사용한다.
  static double estimateCarbonFootprint(
    Map<String, double> materials,
    ClothingTypeOption clothingType,
  ) {
    final weightKg = clothingType.estimatedWeightGram / 1000;

    if (materials.isEmpty) {
      return double.parse(
        (weightKg * defaultEmissionFactor).toStringAsFixed(1),
      );
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
    // 개수도 표준명 기준으로 센다. 원문 키로 세면 사용자가 같은 소재를 두 이름으로
    // 적었을 때('면' 50 + 'cotton' 50) 100% 단일 소재인데 2종으로 계산돼
    // 단일 소재 가점을 못 받는다. 서버는 둘 다 cotton으로 풀어 저장을 통과시키므로
    // 어긋난 건강도만 조용히 남는다.
    final keys = MaterialName.standardizeAll(materials.keys);
    final distinctMaterialCount = keys.toSet().length;

    if (distinctMaterialCount == 1) score += 8;
    if (distinctMaterialCount >= 3) score -= 8;

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

  /// 소재별 배출계수(kg CO2eq/kg textile). **서버 시드의 `carbon_factor`와 1:1이다.**
  ///
  /// 이전에는 프론트가 자체 숫자를 갖고 있었고, 서버와 겹치는 10종이 **전부**
  /// 달랐다(cotton 8.0/8.3 · linen 6.0/4.5 · polyester 12.0/9.5 · nylon 14.0/11.0 ·
  /// wool 25.0/13.9 · silk 20.0/15.0 · viscose 10.0/6.4 · rayon 10.0/6.4 ·
  /// polyurethane 15.0/12.0 · spandex 15.0/12.0 — 일치 0종).
  /// 서버 전용 12종은 분기가 아예 없어 기본계수로 떨어졌다
  /// (캐시미어 30.0을 10.0으로 계산해 실제의 1/3이 나왔다).
  /// 저장 시 서버 계산으로 덮이는 값이라 화면에서만 어긋났지만, 사용자는 같은 옷의
  /// 탄소값이 저장 전후로 달라지는 것을 그대로 봤다.
  ///
  /// 서버에 없는 소재(`organic cotton`·`recycled polyester` 등)는 넣지 않는다.
  /// 프론트만 알아보면 프리뷰에는 그럴듯한 값이 뜨는데 저장은
  /// 400 `MATERIAL_NOT_FOUND`로 거부돼 어긋남이 생긴다.
  static const Map<String, double> _emissionFactorsByStandardName = {
    'cotton': 8.3,
    'polyester': 9.5,
    'rayon': 6.4,
    'nylon': 11.0,
    'wool': 13.9,
    'acrylic': 10.0,
    'spandex': 12.0,
    'linen': 4.5,
    'viscose': 6.4,
    'silk': 15.0,
    'modal': 6.0,
    'cashmere': 30.0,
    'polyurethane': 12.0,
    'leather': 20.0,
    'ramie': 4.5,
    'lyocell': 5.5,
    'down': 18.0,
    'feather': 12.0,
    'yak': 18.0,
    'mohair': 18.0,
    'bamboo': 5.0,
    'cupro': 6.0,
  };

  static double _findMaterialEmissionFactor(String material) {
    return _emissionFactorsByStandardName[MaterialName.standardize(material)] ??
        defaultEmissionFactor;
  }
}
