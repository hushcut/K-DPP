/// 소재명을 서버 표준명(영문)으로 되돌린다.
///
/// **왜 필요한가.** 스캔이 성공하면 서버가 `material_details.display_name`으로 내려준
/// **한글명**('면','울')이 그대로 편집 폼의 소재 키가 되고(`ScanDraftService`),
/// 저장 시 `Clothes.materials`의 키로 옷장에 남는다. 반면 사용자가 영문('cotton')을
/// 직접 입력했거나 2026-09-13 이전에 자동완성으로 고른 옷(`option.nameEn`)은 영문 키다
/// (그 뒤로 자동완성·소재 선택창은 한글명 `nameKo`를 넣는다). 즉 **같은 소재가 등록
/// 경로와 시점에 따라 다른 문자열로 저장된다.** 소재를 문자열로 판별하는 코드가
/// 한쪽만 알아보면 다른 쪽 옷에서만 조용히 기능이 죽는다.
///
/// 실제로 그런 결함이 세 곳에서 났다 — 배출계수·건강도 조회(`ClothingEstimator`),
/// 리포트의 관리·보관·폐기 안내(`report_guide_sections.dart`),
/// 홈의 '코튼 소재 관리 팁'(`home_screen.dart`). 사본을 늘리지 않도록 이 파일 한 곳에 둔다.
///
/// 표는 서버 소재 표(`BACKEND/init_data.py`의 `MATERIAL_SEEDS`)의 `name_ko`·`aliases`를
/// 옮긴 것이며, 어긋나면 `BACKEND/tests/test_material_name_contract.py`가 실패한다.
library;

class MaterialName {
  const MaterialName._();

  /// 서버 소재 표가 쓰는 한글명과 별칭을 영문 표준명으로 되돌리는 표다.
  ///
  /// **완전 일치로만 찾는다.** 서버 별칭에는 '모'(wool)·'마'(linen)처럼 다른 소재명의
  /// 부분 문자열인 것이 있어, 부분 일치를 쓰면 '모달'(modal)·'모헤어'(mohair)가 울로 잡힌다.
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

  /// 소재명 하나를 영문 표준명으로 바꾼다.
  /// 표에 없는 이름은 앞뒤 공백과 대소문자만 정리해 그대로 돌려준다
  /// (사용자가 자유 입력한 이름을 지어내지 않는다).
  static String standardize(String material) {
    final normalized = material.trim().toLowerCase();
    return _standardNamesByAlias[normalized] ?? normalized;
  }

  /// 소재 이름 목록을 표준명 목록으로 바꾼다.
  static List<String> standardizeAll(Iterable<String> materials) {
    return materials.map(standardize).toList(growable: false);
  }

  /// 표준화한 소재명 중 하나라도 [keywords]에 걸리는지 확인한다.
  ///
  /// 키워드는 `contains`로 맞춘다 — 서버에 없는 자유 입력('organic cotton' 등)도
  /// 계열 판정에는 걸리게 하기 위함이다. 표준화가 먼저이므로 '모달'은
  /// 표준명 `modal`이 되어 `wool` 키워드에 걸리지 않는다.
  static bool matchesAny(Iterable<String> materials, List<String> keywords) {
    final standardNames = standardizeAll(materials);

    return standardNames.any(
      (name) => keywords.any((keyword) => name.contains(keyword)),
    );
  }
}
