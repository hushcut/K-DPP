enum CarbonFootprintSource {
  server,
  localEstimate;

  static CarbonFootprintSource fromJson(dynamic value) {
    return values.firstWhere(
      (source) => source.name == value?.toString(),
      orElse: () => CarbonFootprintSource.localEstimate,
    );
  }
}

class Clothes {
  final String title;
  final String category;
  final int health;
  final Map<String, double> materials;
  final String careInstruction;
  final double carbonFootprint;
  final CarbonFootprintSource carbonFootprintSource;
  final double carbonFootprintMin;
  final double carbonFootprintMax;
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
    double? carbonFootprintMin,
    double? carbonFootprintMax,
    this.minWeightGram,
    this.maxWeightGram,
    this.savedResultId,
  })  : carbonFootprintMin = carbonFootprintMin ?? carbonFootprint,
        carbonFootprintMax = carbonFootprintMax ?? carbonFootprint;

  String get carbonFootprintRangeText {
    if ((carbonFootprintMin - carbonFootprintMax).abs() < 0.05) {
      return '${carbonFootprint.toStringAsFixed(1)} kg CO2eq';
    }

    return '${carbonFootprintMin.toStringAsFixed(1)}~${carbonFootprintMax.toStringAsFixed(1)} kg CO2eq';
  }

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

  factory Clothes.fromJson(Map<String, dynamic> json) {
    final rawMaterials = json['materials'];
    final parsedMaterials = <String, double>{};

    if (rawMaterials is Map) {
      for (final entry in rawMaterials.entries) {
        parsedMaterials[entry.key.toString()] =
            double.tryParse(entry.value.toString()) ?? 0.0;
      }
    }

    final footprint = _parseDouble(
      json['carbonFootprint'] ?? json['carbon_footprint'],
    );

    return Clothes(
      title: json['title']?.toString() ?? '이름 없는 의류',
      category: json['category']?.toString() ?? '기타',
      health: _parseInt(json['health']),
      materials: parsedMaterials,
      careInstruction: json['careInstruction']?.toString() ??
          json['care_instruction']?.toString() ??
          '',
      carbonFootprint: footprint,
      carbonFootprintSource: CarbonFootprintSource.fromJson(
        json['carbonFootprintSource'] ?? json['carbon_footprint_source'],
      ),
      carbonFootprintMin: _parseNullableDouble(
            json['carbonFootprintMin'] ?? json['carbon_footprint_min'],
          ) ??
          footprint,
      minWeightGram: _parseNullableDouble(
        json['minWeightGram'] ?? json['min_weight_grams'],
      ),
      maxWeightGram: _parseNullableDouble(
        json['maxWeightGram'] ?? json['max_weight_grams'],
      ),
      savedResultId: _parseNullableInt(
        json['savedResultId'] ?? json['saved_result_id'],
      ),
      carbonFootprintMax: _parseNullableDouble(
            json['carbonFootprintMax'] ?? json['carbon_footprint_max'],
          ) ??
          footprint,
    );
  }

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
    if (value is int) return value.toDouble();
    return double.tryParse(value.toString());
  }

  static int? _parseNullableInt(dynamic value) {
    if (value == null) return null;
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value.toString());
  }
}
