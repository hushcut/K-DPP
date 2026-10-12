import 'package:flutter/material.dart';

import '../models/clothing_type_option.dart';

/// 선택 가능한 의류 유형과 유형별 무게 범위를 담은 앱 내장 카탈로그다.
///
/// 서버 `GET /clothing-types`를 받기 전이나 받지 못했을 때 쓰는 대체 표다.
/// 값은 서버 `BACKEND/main.py`의 `CLOTHING_TYPE_OPTIONS`와 같아야 하며,
/// 어긋나면 `BACKEND/tests/test_clothing_type_contract.py`가 실패한다.
class ClothingTypeCatalog {
  const ClothingTypeCatalog._();

  static const List<ClothingTypeOption> options = [
    ClothingTypeOption(
      id: 'short_sleeve_tshirt',
      label: '반팔 티셔츠',
      category: '상의',
      minWeightGram: 100,
      maxWeightGram: 250,
      estimatedWeightGram: 180,
      icon: Icons.checkroom_outlined,
    ),
    ClothingTypeOption(
      id: 'shirt_blouse',
      label: '셔츠 / 블라우스',
      category: '상의',
      minWeightGram: 150,
      maxWeightGram: 350,
      estimatedWeightGram: 240,
      icon: Icons.dry_cleaning_outlined,
    ),
    ClothingTypeOption(
      id: 'long_sleeve_sweatshirt',
      label: '긴팔 / 맨투맨',
      category: '상의',
      minWeightGram: 350,
      maxWeightGram: 750,
      estimatedWeightGram: 520,
      icon: Icons.checkroom_outlined,
    ),
    ClothingTypeOption(
      id: 'knit',
      label: '니트',
      category: '상의',
      minWeightGram: 400,
      maxWeightGram: 900,
      estimatedWeightGram: 620,
      icon: Icons.texture_outlined,
    ),
    ClothingTypeOption(
      id: 'pants',
      label: '바지',
      category: '하의',
      minWeightGram: 450,
      maxWeightGram: 900,
      estimatedWeightGram: 680,
      icon: Icons.accessibility_new_outlined,
    ),
    ClothingTypeOption(
      id: 'skirt',
      label: '스커트',
      category: '하의',
      minWeightGram: 250,
      maxWeightGram: 650,
      estimatedWeightGram: 420,
      icon: Icons.accessibility_new_outlined,
    ),
    ClothingTypeOption(
      id: 'dress',
      label: '원피스',
      category: '상의',
      minWeightGram: 350,
      maxWeightGram: 850,
      estimatedWeightGram: 560,
      icon: Icons.woman_outlined,
    ),
    ClothingTypeOption(
      id: 'outer',
      label: '아우터',
      category: '상의',
      minWeightGram: 800,
      maxWeightGram: 1800,
      estimatedWeightGram: 1200,
      icon: Icons.ac_unit_outlined,
    ),
    ClothingTypeOption(
      label: '직접 입력',
      category: '상의',
      minWeightGram: 500,
      maxWeightGram: 500,
      estimatedWeightGram: 500,
      icon: Icons.scale_outlined,
      isDirectWeightPlaceholder: true,
    ),
  ];

  /// 분류할 단서가 없을 때 사용할 기본 의류 유형이다.
  static ClothingTypeOption get defaultOption => options.first;

  /// 서버 카테고리에 포함된 한국어·영어 키워드를 순서대로 찾아 대응 유형을 반환한다.
  static ClothingTypeOption inferFromCategory(String? category) {
    final text = category?.toLowerCase().trim() ?? '';

    if (text.contains('아우터') ||
        text.contains('outer') ||
        text.contains('jacket') ||
        text.contains('coat')) {
      return _findByLabel('아우터');
    }

    if (text.contains('니트') || text.contains('knit')) {
      return _findByLabel('니트');
    }

    if (text.contains('바지') ||
        text.contains('하의') ||
        text.contains('pants') ||
        text.contains('bottom')) {
      return _findByLabel('바지');
    }

    if (text.contains('스커트') || text.contains('skirt')) {
      return _findByLabel('스커트');
    }

    if (text.contains('원피스') || text.contains('dress')) {
      return _findByLabel('원피스');
    }

    // '티셔츠'·'sweatshirt'가 일반 '셔츠'/'shirt' 검사에 먼저 걸리면
    // 240g짜리 셔츠 무게로 잘못 추정되므로, 구체적인 유형을 앞서 확인한다.
    if (text.contains('맨투맨') ||
        text.contains('긴팔') ||
        text.contains('스웨트') ||
        text.contains('후드') ||
        text.contains('sweatshirt') ||
        text.contains('hoodie')) {
      return _findByLabel('긴팔 / 맨투맨');
    }

    if (text.contains('티셔츠') ||
        text.contains('반팔') ||
        text.contains('t-shirt') ||
        text.contains('tshirt')) {
      return _findByLabel('반팔 티셔츠');
    }

    if (text.contains('셔츠') ||
        text.contains('블라우스') ||
        text.contains('shirt') ||
        text.contains('blouse')) {
      return _findByLabel('셔츠 / 블라우스');
    }

    return defaultOption;
  }

  /// 제목이 현재 또는 이전 버전에서 자동 생성한 기본 제목인지 판별한다.
  static bool hasDefaultTitle(String title) {
    final normalizedTitle = title.trim();

    return options.any((option) {
      final legacyTitle = option.isDirectWeightPlaceholder
          ? '홍길동 기타 의류'
          : '홍길동 ${option.label}';

      return option.defaultTitle == normalizedTitle ||
          legacyTitle == normalizedTitle;
    });
  }

  static ClothingTypeOption _findByLabel(String label) {
    return options.firstWhere((item) => item.label == label);
  }
}
