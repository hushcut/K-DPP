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

  final int id;
  final int? userId;
  final Map<String, double> materials;
  final double carbonFootprint;
  final double? carbonFootprintMin;
  final double? carbonFootprintMax;
  final double? minWeightGram;
  final double? maxWeightGram;
  final DateTime? createdAt;

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
