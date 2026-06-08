import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../models/clothing_type_option.dart';

class ClothingTypeApiService {
  const ClothingTypeApiService({
    this.baseUrl = const String.fromEnvironment(
      'AUTH_API_BASE_URL',
      defaultValue: 'http://10.0.2.2:8000',
    ),
    this.endpoint,
    this.requestTimeout = const Duration(seconds: 5),
    this.client,
  });

  final String baseUrl;
  final String? endpoint;
  final Duration requestTimeout;
  final http.Client? client;

  Future<List<ClothingTypeOption>> fetchOptions() async {
    final activeClient = client ?? http.Client();
    final shouldCloseClient = client == null;

    try {
      final uri = endpoint == null
          ? Uri.parse(baseUrl).resolve('/clothing-types')
          : Uri.parse(endpoint!);
      final response = await activeClient
          .get(
            uri,
            headers: const {
              'Accept': 'application/json',
              'ngrok-skip-browser-warning': 'true',
            },
          )
          .timeout(requestTimeout);

      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw HttpException('의류 무게 기준을 불러오지 못했습니다.', uri: uri);
      }

      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is! Map<String, dynamic> || decoded['items'] is! List) {
        throw const FormatException('의류 무게 기준 응답 형식이 올바르지 않습니다.');
      }

      final options = (decoded['items'] as List)
          .whereType<Map>()
          .map((item) => _parseOption(Map<String, dynamic>.from(item)))
          .toList(growable: true);

      if (options.isEmpty) {
        throw const FormatException('사용 가능한 의류 무게 기준이 없습니다.');
      }

      options.add(
        const ClothingTypeOption(
          label: '직접 입력',
          category: '상의',
          weightRangeLabel: '실제 무게 입력',
          estimatedWeightGram: 500,
          icon: Icons.scale_outlined,
          isDirectWeightPlaceholder: true,
        ),
      );
      return options;
    } finally {
      if (shouldCloseClient) {
        activeClient.close();
      }
    }
  }

  ClothingTypeOption _parseOption(Map<String, dynamic> json) {
    final id = json['id']?.toString().trim() ?? '';
    final label = json['label']?.toString().trim() ?? '';
    final category = json['category']?.toString().trim() ?? '';
    final minWeight = _parseDouble(json['min_weight_grams']);
    final maxWeight = _parseDouble(json['max_weight_grams']);
    final estimatedWeight = _parseDouble(json['estimated_weight_grams']);

    if (label.isEmpty ||
        category.isEmpty ||
        minWeight == null ||
        maxWeight == null ||
        estimatedWeight == null) {
      throw const FormatException('의류 무게 기준 항목이 올바르지 않습니다.');
    }

    return ClothingTypeOption(
      label: label,
      category: category,
      weightRangeLabel:
          '${ClothingTypeOption.formatWeightGram(minWeight)}~'
          '${ClothingTypeOption.formatWeightGram(maxWeight)}g',
      estimatedWeightGram: estimatedWeight,
      minimumWeightGram: minWeight,
      maximumWeightGram: maxWeight,
      icon: _iconFor(id),
    );
  }

  static double? _parseDouble(dynamic value) {
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString() ?? '');
  }

  static IconData _iconFor(String id) {
    if (id.contains('pants') || id.contains('skirt')) {
      return Icons.accessibility_new_outlined;
    }
    if (id.contains('dress')) return Icons.woman_outlined;
    if (id.contains('outer') || id.contains('coat')) {
      return Icons.ac_unit_outlined;
    }
    if (id.contains('knit')) return Icons.texture_outlined;
    if (id.contains('shirt') || id.contains('blouse')) {
      return Icons.dry_cleaning_outlined;
    }
    return Icons.checkroom_outlined;
  }
}
