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
  });

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
}
