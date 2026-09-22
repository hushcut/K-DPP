/// 의류 라벨 스캔 API가 반환한 소재 구성과 분석 부가 정보를 담는 모델입니다.
///
/// [materials]는 생성 시 수정 불가능한 맵으로 복사되어 이후 분석 원본이
/// 의도치 않게 바뀌지 않도록 합니다.
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

  /// 인식한 소재명과 함유율(%)의 대응 관계입니다.
  final Map<String, double> materials;

  /// 서버가 정규화한 소재별 표시명·표준명·지원 여부 정보입니다.
  final List<ScanMaterialDetail> materialDetails;

  /// 소재명에 대응하는 서버 표시명을 돌려주고, 정보가 없으면 원래 이름을 씁니다.
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

  /// 화면 표기에 쓰는 표시명 기준 소재 구성입니다.
  Map<String, double> get displayMaterials {
    return Map.unmodifiable({
      for (final entry in materials.entries)
        displayNameFor(entry.key): entry.value,
    });
  }

  // 세탁·관리 지침과 화면 표시에 사용할 선택적 분석 메타데이터입니다.
  final String careInstruction;
  final String? title;
  final String? category;
  final int? health;
  final double? carbonFootprint;
  final double? weightGram;
  final String? calculationMethod;
  final String? unit;
  final int? savedResultId;

  /// 여러 버전의 서버 키 이름을 허용해 JSON을 모델로 변환합니다.
  ///
  /// 소재 값이 맵이나 목록 형식이 아니면 [FormatException]을 발생시킵니다.
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
}

/// 서버가 소재명을 정규화한 결과(원본명·표준명·표시명·지원 여부)입니다.
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
