import 'package:flutter/material.dart';

/// 탄소 배출량 계산의 무게 기준으로 선택할 의류 종류 한 항목을 표현합니다.
///
/// 일반 항목은 예상 무게 범위를 사용하고, 직접 입력 항목은 사용자가 입력한
/// 실제 무게를 [estimatedWeightGram]에 저장합니다.
class ClothingTypeOption {
  const ClothingTypeOption({
    required this.label,
    required this.category,
    required this.weightRangeLabel,
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
      weightRangeLabel: '${formatWeightGram(weightGram)}g',
      estimatedWeightGram: weightGram,
      icon: Icons.scale_outlined,
      isDirectWeight: true,
    );
  }

  // 선택 화면에 표시할 이름, 분류, 무게 정보와 아이콘입니다.
  final String label;
  final String category;
  final String weightRangeLabel;
  final double estimatedWeightGram;
  final IconData icon;
  // 직접 입력 진입용 항목인지, 실제 무게가 입력된 항목인지 구분합니다.
  final bool isDirectWeightPlaceholder;
  final bool isDirectWeight;

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

  /// 계산에 사용할 최소 무게를 범위 문자열에서 읽어 반환합니다.
  double get minWeightGram {
    if (isDirectWeight || isDirectWeightPlaceholder) return estimatedWeightGram;

    final match = RegExp(
      r'(\d+(?:\.\d+)?)~(\d+(?:\.\d+)?)g',
    ).firstMatch(weightRangeLabel);

    if (match == null) return estimatedWeightGram;
    return double.tryParse(match.group(1) ?? '') ?? estimatedWeightGram;
  }

  /// 계산에 사용할 최대 무게를 범위 문자열에서 읽어 반환합니다.
  double get maxWeightGram {
    if (isDirectWeight || isDirectWeightPlaceholder) return estimatedWeightGram;

    final match = RegExp(
      r'(\d+(?:\.\d+)?)~(\d+(?:\.\d+)?)g',
    ).firstMatch(weightRangeLabel);

    if (match == null) return estimatedWeightGram;
    return double.tryParse(match.group(2) ?? '') ?? estimatedWeightGram;
  }

  /// 정수는 소수점 없이, 그 외 값은 소수 첫째 자리로 반올림해 표시 문자열로 바꿉니다.
  static String formatWeightGram(double value) {
    if (value % 1 == 0) {
      return value.toInt().toString();
    }

    return value.toStringAsFixed(1);
  }
}
