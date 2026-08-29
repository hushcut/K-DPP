/// 탄소 배출량이 서버 계산값인지 로컬 추정값인지 구분합니다.
enum CarbonFootprintSource {
  server,
  localEstimate;

  /// JSON 값이 `server`일 때만 서버값으로, 나머지는 로컬 추정값으로 해석합니다.
  static CarbonFootprintSource fromJson(dynamic value) {
    return value?.toString() == server.name ? server : localEstimate;
  }
}

/// 옷장에 저장되는 의류의 기본 정보, 소재 구성, 탄소 분석 결과를 담는 모델입니다.
class Clothes {
  // 의류 식별 정보와 분석에 사용되는 소재·관리·탄소 배출량 값입니다.
  final String title;
  final String category;
  final int health;
  final Map<String, double> materials;
  final String careInstruction;
  final double carbonFootprint;
  final CarbonFootprintSource carbonFootprintSource;
  // 추정치의 범위, 계산 무게 범위 및 서버 저장 식별자입니다.
  final double? carbonFootprintMin;
  final double? carbonFootprintMax;
  final double? minWeightGram;
  final double? maxWeightGram;
  final int? savedResultId;
  // 옷장에 등록한 시각입니다. 필드 도입 전에 저장된 의류는 null입니다.
  final DateTime? registeredAt;
  // 서버 계산의 무게 출처와 계산 범위·근거·출처·비고 설명입니다.
  final String? weightSource;
  final String? calculationScope;
  final String? calculationBasis;
  final String? calculationSource;
  final String? calculationNote;

  Clothes({
    required this.title,
    required this.category,
    required this.health,
    required this.materials,
    required this.careInstruction,
    required this.carbonFootprint,
    this.carbonFootprintSource = CarbonFootprintSource.localEstimate,
    this.carbonFootprintMin,
    this.carbonFootprintMax,
    this.minWeightGram,
    this.maxWeightGram,
    this.savedResultId,
    this.registeredAt,
    this.weightSource,
    this.calculationScope,
    this.calculationBasis,
    this.calculationSource,
    this.calculationNote,
  });

  /// 등록 시각 기준 최신순 비교값을 반환합니다.
  /// 시각이 없는 옛 항목은 더 오래된 것으로 취급하고,
  /// 둘 다 시각이 없거나 같으면 0을 반환해 호출부의 위치 기준을 따릅니다.
  static int compareByRecency(Clothes a, Clothes b) {
    final aTime = a.registeredAt;
    final bTime = b.registeredAt;

    if (aTime != null && bTime != null) {
      return bTime.compareTo(aTime);
    }
    if (aTime != null) return -1;
    if (bTime != null) return 1;
    return 0;
  }

  /// 지정한 필드만 바꾼 새 [Clothes] 인스턴스를 반환합니다.
  Clothes copyWith({
    String? title,
    String? category,
    int? health,
    Map<String, double>? materials,
    String? careInstruction,
    double? carbonFootprint,
    CarbonFootprintSource? carbonFootprintSource,
    double? carbonFootprintMin,
    double? carbonFootprintMax,
    double? minWeightGram,
    double? maxWeightGram,
    int? savedResultId,
    DateTime? registeredAt,
    String? weightSource,
    String? calculationScope,
    String? calculationBasis,
    String? calculationSource,
    String? calculationNote,
  }) {
    return Clothes(
      title: title ?? this.title,
      category: category ?? this.category,
      health: health ?? this.health,
      materials: materials ?? this.materials,
      careInstruction: careInstruction ?? this.careInstruction,
      carbonFootprint: carbonFootprint ?? this.carbonFootprint,
      carbonFootprintSource:
          carbonFootprintSource ?? this.carbonFootprintSource,
      carbonFootprintMin: carbonFootprintMin ?? this.carbonFootprintMin,
      carbonFootprintMax: carbonFootprintMax ?? this.carbonFootprintMax,
      minWeightGram: minWeightGram ?? this.minWeightGram,
      maxWeightGram: maxWeightGram ?? this.maxWeightGram,
      savedResultId: savedResultId ?? this.savedResultId,
      registeredAt: registeredAt ?? this.registeredAt,
      weightSource: weightSource ?? this.weightSource,
      calculationScope: calculationScope ?? this.calculationScope,
      calculationBasis: calculationBasis ?? this.calculationBasis,
      calculationSource: calculationSource ?? this.calculationSource,
      calculationNote: calculationNote ?? this.calculationNote,
    );
  }

  /// 서버 또는 로컬 저장소의 JSON을 의류 모델로 변환합니다.
  factory Clothes.fromJson(Map<String, dynamic> json) {
    final rawMaterials = json['materials'];
    final parsedMaterials = <String, double>{};

    if (rawMaterials is Map) {
      for (final entry in rawMaterials.entries) {
        parsedMaterials[entry.key.toString()] =
            double.tryParse(entry.value.toString()) ?? 0.0;
      }
    }

    return Clothes(
      title: json['title']?.toString() ?? '이름 없는 의류',
      category: json['category']?.toString() ?? '기타',
      health: _parseInt(json['health']),
      materials: parsedMaterials,
      careInstruction:
          json['careInstruction']?.toString() ??
          json['care_instruction']?.toString() ??
          '',
      carbonFootprint: _parseDouble(
        json['carbonFootprint'] ?? json['carbon_footprint'],
      ),
      carbonFootprintSource: CarbonFootprintSource.fromJson(
        json['carbonFootprintSource'] ?? json['carbon_footprint_source'],
      ),
      carbonFootprintMin: _parseNullableDouble(
        json['carbonFootprintMin'] ?? json['carbon_footprint_min'],
      ),
      carbonFootprintMax: _parseNullableDouble(
        json['carbonFootprintMax'] ?? json['carbon_footprint_max'],
      ),
      minWeightGram: _parseNullableDouble(
        json['minWeightGram'] ?? json['min_weight_grams'],
      ),
      maxWeightGram: _parseNullableDouble(
        json['maxWeightGram'] ?? json['max_weight_grams'],
      ),
      savedResultId: _parseNullableInt(
        json['savedResultId'] ?? json['saved_result_id'],
      ),
      registeredAt: _parseNullableDateTime(
        json['registeredAt'] ?? json['registered_at'],
      ),
      weightSource: _parseNullableString(
        json['weightSource'] ?? json['weight_source'],
      ),
      calculationScope: _parseNullableString(
        json['calculationScope'] ?? json['calculation_scope'],
      ),
      calculationBasis: _parseNullableString(
        json['calculationBasis'] ?? json['calculation_basis'],
      ),
      calculationSource: _parseNullableString(
        json['calculationSource'] ?? json['calculation_source'],
      ),
      calculationNote: _parseNullableString(
        json['calculationNote'] ?? json['calculation_note'],
      ),
    );
  }

  /// 현재 의류 정보를 로컬 저장용 JSON 맵으로 반환합니다.
  Map<String, dynamic> toJson() {
    return {
      'title': title,
      'category': category,
      'health': health,
      'materials': materials,
      'careInstruction': careInstruction,
      'carbonFootprint': carbonFootprint,
      'carbonFootprintSource': carbonFootprintSource.name,
      'carbonFootprintMin': carbonFootprintMin,
      'carbonFootprintMax': carbonFootprintMax,
      'minWeightGram': minWeightGram,
      'maxWeightGram': maxWeightGram,
      'savedResultId': savedResultId,
      'registeredAt': registeredAt?.toIso8601String(),
      'weightSource': weightSource,
      'calculationScope': calculationScope,
      'calculationBasis': calculationBasis,
      'calculationSource': calculationSource,
      'calculationNote': calculationNote,
    };
  }

  static int _parseInt(dynamic value) {
    if (value is int) return value;
    if (value is double) return value.round();
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }

  static double _parseDouble(dynamic value) {
    if (value is double) return value;
    if (value is int) return value.toDouble();
    return double.tryParse(value?.toString() ?? '') ?? 0.0;
  }

  static double? _parseNullableDouble(dynamic value) {
    if (value == null) return null;
    if (value is double) return value;
    if (value is num) return value.toDouble();
    return double.tryParse(value.toString());
  }

  static int? _parseNullableInt(dynamic value) {
    if (value == null) return null;
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value.toString());
  }

  static DateTime? _parseNullableDateTime(dynamic value) {
    if (value == null) return null;
    return DateTime.tryParse(value.toString());
  }

  static String? _parseNullableString(dynamic value) {
    final text = value?.toString().trim();
    return text?.isNotEmpty == true ? text : null;
  }
}
