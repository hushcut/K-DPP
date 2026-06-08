class ScanResult {
  ScanResult({
    required Map<String, double> materials,
    required this.careInstruction,
    List<ScanMaterialDetail> materialDetails = const [],
    this.title,
    this.category,
    this.health,
    this.carbonFootprint,
    this.weightGram,
    this.calculationMethod,
    this.unit,
    this.savedResultId,
  }) : materials = Map.unmodifiable(materials),
       materialDetails = List.unmodifiable(materialDetails);

  static const String defaultCareInstruction = '라벨의 세탁 지침을 확인해 주세요.';

  final Map<String, double> materials;
  final List<ScanMaterialDetail> materialDetails;
  final String careInstruction;
  final String? title;
  final String? category;
  final int? health;
  final double? carbonFootprint;
  final double? weightGram;
  final String? calculationMethod;
  final String? unit;
  final int? savedResultId;

  String displayNameFor(String materialName) {
    final normalizedName = materialName.trim().toLowerCase();

    for (final detail in materialDetails) {
      if (detail.originalName.trim().toLowerCase() == normalizedName ||
          detail.standardName?.trim().toLowerCase() == normalizedName) {
        return detail.displayName;
      }
    }

    return materialName;
  }

  Map<String, double> get displayMaterials {
    return Map.unmodifiable({
      for (final entry in materials.entries)
        displayNameFor(entry.key): entry.value,
    });
  }

  factory ScanResult.fromJson(Map<String, dynamic> json) {
    final rawMaterials =
        json['materials'] ?? json['material'] ?? json['composition'];

    if (rawMaterials is! Map && rawMaterials is! List) {
      throw const FormatException('materials 형식이 올바르지 않습니다.');
    }

    return ScanResult(
      materials: _parseMaterials(rawMaterials),
      materialDetails: _parseMaterialDetails(json['material_details']),
      careInstruction:
          _readOptionalString(json, const [
            'care_instruction',
            'careInstruction',
            'care',
            'washingInstruction',
          ]) ??
          defaultCareInstruction,
      title: _readOptionalString(json, const ['title', 'name', 'clothingName']),
      category: _readOptionalString(json, const ['category', 'type']),
      health: _parseNullableInt(json['health']),
      carbonFootprint: _parseNullableDouble(
        json['carbon_footprint'] ?? json['carbonFootprint'],
      ),
      weightGram: _parseNullableDouble(
        json['weight_gram'] ?? json['weightGram'],
      ),
      calculationMethod: _readOptionalString(json, const [
        'calculation_method',
        'calculationMethod',
      ]),
      unit: _readOptionalString(json, const ['unit']),
      savedResultId: _parseNullableInt(
        json['saved_result_id'] ?? json['savedResultId'],
      ),
    );
  }

  static Map<String, double> _parseMaterials(Object rawMaterials) {
    final materials = <String, double>{};

    if (rawMaterials is Map) {
      rawMaterials.forEach((key, value) {
        final name = key.toString().trim();
        final percentage = _parsePercentage(value);

        if (name.isNotEmpty && percentage != null) {
          materials[name] = percentage;
        }
      });
    }

    if (rawMaterials is List) {
      for (final item in rawMaterials) {
        if (item is! Map) continue;

        final name =
            (item['name'] ?? item['material'] ?? item['label'] ?? item['type'])
                ?.toString()
                .trim();
        final percentage = _parsePercentage(
          item['percent'] ??
              item['percentage'] ??
              item['ratio'] ??
              item['value'],
        );

        if (name != null && name.isNotEmpty && percentage != null) {
          materials[name] = percentage;
        }
      }
    }

    return materials;
  }

  static List<ScanMaterialDetail> _parseMaterialDetails(dynamic value) {
    if (value is! List) return const [];

    return value
        .whereType<Map>()
        .map(
          (item) =>
              ScanMaterialDetail.fromJson(Map<String, dynamic>.from(item)),
        )
        .where((item) => item.originalName.isNotEmpty)
        .toList(growable: false);
  }

  static double? _parsePercentage(dynamic value) {
    if (value == null) return null;
    if (value is num) return value.toDouble();

    return double.tryParse(value.toString().replaceAll('%', '').trim());
  }

  static String? _readOptionalString(
    Map<String, dynamic> json,
    List<String> keys,
  ) {
    for (final key in keys) {
      final value = json[key]?.toString().trim();

      if (value != null && value.isNotEmpty) {
        return value;
      }
    }

    return null;
  }

  static int? _parseNullableInt(dynamic value) {
    if (value == null) return null;
    if (value is int) return value;
    if (value is num) return value.round();
    return int.tryParse(value.toString());
  }

  static double? _parseNullableDouble(dynamic value) {
    if (value == null) return null;
    if (value is num) return value.toDouble();
    return double.tryParse(value.toString());
  }
}

class ScanMaterialDetail {
  const ScanMaterialDetail({
    required this.originalName,
    required this.displayName,
    required this.ratio,
    required this.isSupported,
    this.standardName,
  });

  final String originalName;
  final String? standardName;
  final String displayName;
  final double ratio;
  final bool isSupported;

  factory ScanMaterialDetail.fromJson(Map<String, dynamic> json) {
    final originalName = json['original_name']?.toString().trim() ?? '';
    final displayName = json['display_name']?.toString().trim();

    return ScanMaterialDetail(
      originalName: originalName,
      standardName: _optionalString(json['standard_name']),
      displayName: displayName?.isNotEmpty == true
          ? displayName!
          : originalName,
      ratio: ScanResult._parsePercentage(json['ratio']) ?? 0,
      isSupported: json['is_supported'] == true,
    );
  }

  static String? _optionalString(dynamic value) {
    final text = value?.toString().trim();
    return text?.isNotEmpty == true ? text : null;
  }
}
