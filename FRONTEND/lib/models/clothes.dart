enum CarbonFootprintSource {
  server,
  localEstimate;

  static CarbonFootprintSource fromJson(dynamic value) {
    return value?.toString() == server.name ? server : localEstimate;
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
  final double? carbonFootprintMin;
  final double? carbonFootprintMax;
  final double? minWeightGram;
  final double? maxWeightGram;
  final int? savedResultId;
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
    this.weightSource,
    this.calculationScope,
    this.calculationBasis,
    this.calculationSource,
    this.calculationNote,
  });

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
      weightSource: weightSource ?? this.weightSource,
      calculationScope: calculationScope ?? this.calculationScope,
      calculationBasis: calculationBasis ?? this.calculationBasis,
      calculationSource: calculationSource ?? this.calculationSource,
      calculationNote: calculationNote ?? this.calculationNote,
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

  static String? _parseNullableString(dynamic value) {
    final text = value?.toString().trim();
    return text?.isNotEmpty == true ? text : null;
  }
}
