/// 의류 라벨 스캔 API가 반환한 소재 구성과 분석 부가 정보를 담는 모델입니다.
///
/// [materials]는 생성 시 수정 불가능한 맵으로 복사되어 이후 분석 원본이
/// 의도치 않게 바뀌지 않도록 합니다.
class ScanResult {
  ScanResult({
    required Map<String, double> materials,
    required this.careInstruction,
    this.title,
    this.category,
    this.health,
    this.carbonFootprint,
    this.weightGram,
    this.calculationMethod,
    this.unit,
    this.savedResultId,
  }) : materials = Map.unmodifiable(materials);

  static const String defaultCareInstruction = '라벨의 세탁 지침을 확인해 주세요.';

  /// 인식한 소재명과 함유율(%)의 대응 관계입니다.
  final Map<String, double> materials;

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
}
