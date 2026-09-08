import '../models/clothing_type_option.dart';

/// 소재 비율과 의류의 추정 무게를 이용해 저장 전 기본 지표를 계산한다.
///
/// 아래 두 표(`_standardNamesByAlias`·`_emissionFactorsByStandardName`)는
/// **서버 소재 표(`BACKEND/init_data.py`의 `MATERIAL_SEEDS`)를 그대로 옮긴 사본**이다.
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
    final keys = materials.keys.map(_standardizeMaterialName).toList();

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

  /// 서버 소재 표가 쓰는 한글명과 별칭을 영문 표준명으로 되돌린다.
  ///
  /// 스캔이 성공하면 서버가 `material_details.display_name`으로 내려준 **한글명**이
  /// 그대로 편집 폼의 소재 키가 된다(`ScanDraftService.buildFromResult`).
  /// 아래 계수·건강도 조회는 영문 표준명 기준이므로, 이 표가 없으면 스캔한 옷은
  /// 소재와 무관하게 기본계수로 계산되고 건강도도 소재 가·감점을 받지 못한다.
  /// 탄소값은 저장 단계에서 서버 계산으로 덮이지만 **건강도는 덮이지 않아**
  /// 잘못된 값이 옷장·홈 평균에 그대로 남는다.
  ///
  /// **완전 일치로만 찾는다.** 서버 별칭에는 '모'(wool)·'마'(linen)처럼 다른
  /// 소재명의 부분 문자열인 것이 있어, 부분 일치를 쓰면 '모달'(modal)이 울로 잡힌다.
  static const Map<String, String> _standardNamesByAlias = {
    '면': 'cotton',
    '코튼': 'cotton',
    '폴리에스터': 'polyester',
    'poly': 'polyester',
    '레이온': 'rayon',
    '나일론': 'nylon',
    'polyamide': 'nylon',
    '울': 'wool',
    '모': 'wool',
    '아크릴': 'acrylic',
    'polyacryl': 'acrylic',
    '스판덱스': 'spandex',
    '엘라스테인': 'spandex',
    'elastane': 'spandex',
    'lycra': 'spandex',
    '린넨': 'linen',
    '리넨': 'linen',
    '마': 'linen',
    '비스코스': 'viscose',
    'viskose': 'viscose',
    '실크': 'silk',
    '견': 'silk',
    '모달': 'modal',
    '캐시미어': 'cashmere',
    'kashmir': 'cashmere',
    '폴리우레탄': 'polyurethane',
    'pu': 'polyurethane',
    '가죽': 'leather',
    '라미': 'ramie',
    '리오셀': 'lyocell',
    '텐셀': 'lyocell',
    'tencel': 'lyocell',
    '다운': 'down',
    '우모': 'down',
    '오리솜털': 'down',
    '거위솜털': 'down',
    '깃털': 'feather',
    '오리깃털': 'feather',
    '거위깃털': 'feather',
    '야크': 'yak',
    '모헤어': 'mohair',
    '대나무': 'bamboo',
    '큐프로': 'cupro',
  };

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

  /// 소재명을 계수·건강도 조회에 쓸 영문 표준명으로 바꾼다.
  /// 표에 없는 이름은 소문자로만 정리해 그대로 돌려준다.
  static String _standardizeMaterialName(String material) {
    final normalized = material.trim().toLowerCase();
    return _standardNamesByAlias[normalized] ?? normalized;
  }

  static double _findMaterialEmissionFactor(String material) {
    return _emissionFactorsByStandardName[_standardizeMaterialName(material)] ??
        defaultEmissionFactor;
  }
}
