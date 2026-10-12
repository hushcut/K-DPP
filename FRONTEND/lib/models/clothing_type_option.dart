import 'package:flutter/material.dart';

/// 탄소 배출량 계산의 무게 기준으로 선택할 의류 종류 한 항목을 표현합니다.
///
/// 일반 항목은 예상 무게 범위([minWeightGram]~[maxWeightGram])를 사용하고,
/// 직접 입력 항목은 사용자가 입력한 실제 무게를 세 값 모두에 저장합니다.
/// 범위는 서버 `GET /clothing-types`가 숫자로 내려주는 값과 같은 모양이며,
/// 화면 문구([weightRangeLabel])는 이 숫자에서 만듭니다.
class ClothingTypeOption {
  const ClothingTypeOption({
    this.id,
    required this.label,
    required this.category,
    required this.minWeightGram,
    required this.maxWeightGram,
    required this.estimatedWeightGram,
    required this.icon,
    this.isDirectWeightPlaceholder = false,
    this.isDirectWeight = false,
  });

  /// 사용자가 입력한 의류명과 실제 무게로 직접 입력 옵션을 만듭니다.
  factory ClothingTypeOption.directWeight({
    required String label,
    required String category,
    required double weightGram,
  }) {
    return ClothingTypeOption(
      label: label,
      category: category,
      minWeightGram: weightGram,
      maxWeightGram: weightGram,
      estimatedWeightGram: weightGram,
      icon: Icons.scale_outlined,
      isDirectWeight: true,
    );
  }

  /// 서버 `GET /clothing-types`의 항목 하나를 옵션으로 바꿉니다.
  ///
  /// 계산에 그대로 쓰이는 값이라 조금이라도 이상하면 받아들이지 않고 null을 돌려줍니다 —
  /// 식별자·이름이 비었거나, 분류가 옷장 탭(상의/하의)에 없거나, 무게가 유한한 양수가
  /// 아니거나, 최소 ≤ 대표 ≤ 최대가 아닌 경우입니다.
  static ClothingTypeOption? fromServerJson(Map<String, dynamic> json) {
    final id = json['id']?.toString().trim() ?? '';
    final label = json['label']?.toString().trim() ?? '';
    final category = json['category']?.toString().trim() ?? '';
    final minWeight = _parseWeight(json['min_weight_grams']);
    final maxWeight = _parseWeight(json['max_weight_grams']);
    final estimatedWeight = _parseWeight(json['estimated_weight_grams']);

    if (id.isEmpty || label.isEmpty) return null;
    if (category != '상의' && category != '하의') return null;
    if (minWeight == null || maxWeight == null || estimatedWeight == null) {
      return null;
    }
    if (minWeight > estimatedWeight || estimatedWeight > maxWeight) {
      return null;
    }

    return ClothingTypeOption(
      id: id,
      label: label,
      category: category,
      minWeightGram: minWeight,
      maxWeightGram: maxWeight,
      estimatedWeightGram: estimatedWeight,
      icon: iconForId(id),
    );
  }

  /// 서버 항목에는 아이콘이 없어 식별자로 정합니다. 모르는 식별자는 기본 옷 아이콘입니다.
  static IconData iconForId(String id) {
    return switch (id) {
      'shirt_blouse' => Icons.dry_cleaning_outlined,
      'knit' => Icons.texture_outlined,
      'pants' || 'skirt' => Icons.accessibility_new_outlined,
      'dress' => Icons.woman_outlined,
      'outer' => Icons.ac_unit_outlined,
      _ => Icons.checkroom_outlined,
    };
  }

  static double? _parseWeight(dynamic value) {
    final number = value is num ? value.toDouble() : null;
    if (number == null || !number.isFinite || number <= 0) return null;
    return number;
  }

  /// 서버 무게표의 식별자입니다. 직접 입력 항목에는 없습니다.
  final String? id;
  // 선택 화면에 표시할 이름, 분류, 무게 정보와 아이콘입니다.
  final String label;
  final String category;

  /// 계산에 사용할 최소·최대·대표 무게(g)입니다.
  final double minWeightGram;
  final double maxWeightGram;
  final double estimatedWeightGram;
  final IconData icon;
  // 직접 입력 진입용 항목인지, 실제 무게가 입력된 항목인지 구분합니다.
  final bool isDirectWeightPlaceholder;
  final bool isDirectWeight;

  /// 선택 화면에 보여 줄 무게 문구입니다('100~250g', '612.5g', '실제 무게 입력').
  String get weightRangeLabel {
    if (isDirectWeightPlaceholder) return '실제 무게 입력';

    if (isDirectWeight || minWeightGram == maxWeightGram) {
      return '${formatWeightGram(estimatedWeightGram)}g';
    }

    return '${formatWeightGram(minWeightGram)}~${formatWeightGram(maxWeightGram)}g';
  }

  /// 선택한 옵션을 새 의류의 기본 제목으로 변환합니다.
  String get defaultTitle {
    if (isDirectWeightPlaceholder) return '기타 의류';
    return label;
  }

  /// 예상 범위 또는 실제 무게를 사용자용 문구로 반환합니다.
  String get weightDisplayText {
    if (isDirectWeight) {
      return '실제 무게 ${formatWeightGram(estimatedWeightGram)}g';
    }

    if (isDirectWeightPlaceholder) {
      return '실제 무게 입력';
    }

    return '예상 무게 $weightRangeLabel';
  }

  /// 정수는 소수점 없이, 그 외 값은 소수 첫째 자리로 반올림해 표시 문자열로 바꿉니다.
  static String formatWeightGram(double value) {
    if (value % 1 == 0) {
      return value.toInt().toString();
    }

    return value.toStringAsFixed(1);
  }
}
