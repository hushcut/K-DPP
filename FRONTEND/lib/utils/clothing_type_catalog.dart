import 'package:flutter/material.dart';

import '../models/clothing_type_option.dart';

class ClothingTypeCatalog {
  const ClothingTypeCatalog._();

  static const List<ClothingTypeOption> options = [
    ClothingTypeOption(
      label: '반팔 티셔츠',
      category: '상의',
      weightRangeLabel: '100~250g',
      estimatedWeightGram: 180,
      icon: Icons.checkroom_outlined,
    ),
    ClothingTypeOption(
      label: '셔츠 / 블라우스',
      category: '상의',
      weightRangeLabel: '150~350g',
      estimatedWeightGram: 240,
      icon: Icons.dry_cleaning_outlined,
    ),
    ClothingTypeOption(
      label: '긴팔 / 맨투맨',
      category: '상의',
      weightRangeLabel: '350~750g',
      estimatedWeightGram: 520,
      icon: Icons.checkroom_outlined,
    ),
    ClothingTypeOption(
      label: '니트',
      category: '상의',
      weightRangeLabel: '400~900g',
      estimatedWeightGram: 620,
      icon: Icons.texture_outlined,
    ),
    ClothingTypeOption(
      label: '바지',
      category: '하의',
      weightRangeLabel: '450~900g',
      estimatedWeightGram: 680,
      icon: Icons.accessibility_new_outlined,
    ),
    ClothingTypeOption(
      label: '스커트',
      category: '하의',
      weightRangeLabel: '250~650g',
      estimatedWeightGram: 420,
      icon: Icons.accessibility_new_outlined,
    ),
    ClothingTypeOption(
      label: '원피스',
      category: '상의',
      weightRangeLabel: '350~850g',
      estimatedWeightGram: 560,
      icon: Icons.woman_outlined,
    ),
    ClothingTypeOption(
      label: '아우터',
      category: '상의',
      weightRangeLabel: '800~1800g',
      estimatedWeightGram: 1200,
      icon: Icons.ac_unit_outlined,
    ),
    ClothingTypeOption(
      label: '직접 입력',
      category: '상의',
      weightRangeLabel: '실제 무게 입력',
      estimatedWeightGram: 500,
      icon: Icons.scale_outlined,
      isDirectWeightPlaceholder: true,
    ),
  ];

  static ClothingTypeOption get defaultOption => options.first;

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

    if (text.contains('셔츠') ||
        text.contains('블라우스') ||
        text.contains('shirt') ||
        text.contains('blouse')) {
      return _findByLabel('셔츠 / 블라우스');
    }

    if (text.contains('맨투맨') ||
        text.contains('긴팔') ||
        text.contains('sweatshirt')) {
      return _findByLabel('긴팔 / 맨투맨');
    }

    return defaultOption;
  }

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
