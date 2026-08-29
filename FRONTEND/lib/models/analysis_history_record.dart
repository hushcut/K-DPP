/// 서버에 저장된 한 번의 소재 분석 및 탄소 배출량 계산 이력을 표현합니다.
class AnalysisHistoryRecord {
  const AnalysisHistoryRecord({
    required this.id,
    required this.materials,
    required this.carbonFootprint,
    this.userId,
    this.carbonFootprintMin,
    this.carbonFootprintMax,
    this.minWeightGram,
    this.maxWeightGram,
    this.createdAt,
  });

  // 이력과 사용자의 서버 식별자를 묶어 둡니다.
  final int id;
  final int? userId;
  // 분석 당시의 소재 비율과 대표 탄소 배출량입니다.
  final Map<String, double> materials;
  final double carbonFootprint;
  // 계산 결과와 무게의 선택적 최소·최대 범위 및 생성 시각입니다.
  final double? carbonFootprintMin;
  final double? carbonFootprintMax;
  final double? minWeightGram;
  final double? maxWeightGram;
  final DateTime? createdAt;

  /// 서버 JSON을 이력으로 변환하며 필수 값이 없거나 형식이 맞지 않으면 [FormatException]을 던집니다.
  factory AnalysisHistoryRecord.fromJson(Map<String, dynamic> json) {
    final id = _parseInt(json['id']);
    final carbonFootprint = _parseDouble(json['carbon_footprint']);
    final rawMaterials = json['materials'];

    if (id == null || carbonFootprint == null || rawMaterials is! Map) {
      throw const FormatException('서버 의류 기록 형식이 올바르지 않습니다.');
    }

    final materials = <String, double>{};

    for (final entry in rawMaterials.entries) {
      final name = entry.key.toString().trim();
      final percentage = _parseDouble(entry.value);

      if (name.isNotEmpty && percentage != null) {
        materials[name] = percentage;
      }
    }

    return AnalysisHistoryRecord(
      id: id,
      userId: _parseInt(json['user_id']),
      materials: materials,
      carbonFootprint: carbonFootprint,
      carbonFootprintMin: _parseDouble(json['carbon_footprint_min']),
      carbonFootprintMax: _parseDouble(json['carbon_footprint_max']),
      minWeightGram: _parseDouble(json['min_weight_grams']),
      maxWeightGram: _parseDouble(json['max_weight_grams']),
      createdAt: DateTime.tryParse(json['created_at']?.toString() ?? ''),
    );
  }

  static int? _parseInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '');
  }

  static double? _parseDouble(dynamic value) {
    if (value is double) return value;
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString() ?? '');
  }
}
