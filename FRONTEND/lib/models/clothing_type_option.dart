import 'package:flutter/material.dart';

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

  final String label;
  final String category;
  final String weightRangeLabel;
  final double estimatedWeightGram;
  final IconData icon;
  final bool isDirectWeightPlaceholder;
  final bool isDirectWeight;

  String get defaultTitle {
    if (isDirectWeightPlaceholder) return '기타 의류';
    return label;
  }

  String get weightDisplayText {
    if (isDirectWeight) {
      return '실제 무게 ${formatWeightGram(estimatedWeightGram)}g';
    }

    if (isDirectWeightPlaceholder) {
      return '실제 무게 입력';
    }

    return '예상 무게 $weightRangeLabel';
  }

  double get minWeightGram {
    if (isDirectWeight || isDirectWeightPlaceholder) return estimatedWeightGram;

    final match = RegExp(
      r'(\d+(?:\.\d+)?)~(\d+(?:\.\d+)?)g',
    ).firstMatch(weightRangeLabel);

    if (match == null) return estimatedWeightGram;
    return double.tryParse(match.group(1) ?? '') ?? estimatedWeightGram;
  }

  double get maxWeightGram {
    if (isDirectWeight || isDirectWeightPlaceholder) return estimatedWeightGram;

    final match = RegExp(
      r'(\d+(?:\.\d+)?)~(\d+(?:\.\d+)?)g',
    ).firstMatch(weightRangeLabel);

    if (match == null) return estimatedWeightGram;
    return double.tryParse(match.group(2) ?? '') ?? estimatedWeightGram;
  }

  static String formatWeightGram(double value) {
    if (value % 1 == 0) {
      return value.toInt().toString();
    }

    return value.toStringAsFixed(1);
  }
}
