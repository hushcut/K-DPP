class ScanResult {
  final Map<String, double> materials;
  final String careInstruction;
  final String? title;
  final String? category;
  final int? health;
  final double? carbonFootprint;

  ScanResult({
    required this.materials,
    required this.careInstruction,
    this.title,
    this.category,
    this.health,
    this.carbonFootprint,
  });

  factory ScanResult.fromJson(Map<String, dynamic> json) {
    final rawMaterials = json['materials'];

    if (rawMaterials is! Map) {
      throw const FormatException('materials 형식이 올바르지 않습니다.');
    }

    final parsedMaterials = <String, double>{};
    for (final entry in rawMaterials.entries) {
      parsedMaterials[entry.key.toString()] =
          double.tryParse(entry.value.toString()) ?? 0.0;
    }

    return ScanResult(
      materials: parsedMaterials,
      careInstruction: json['care_instruction']?.toString() ?? '',
      title: json['title']?.toString(),
      category: json['category']?.toString(),
      health: _parseNullableInt(json['health']),
      carbonFootprint: _parseNullableDouble(
        json['carbon_footprint'] ?? json['carbonFootprint'],
      ),
    );
  }

  static int? _parseNullableInt(dynamic value) {
    if (value == null) return null;
    if (value is int) return value;
    if (value is double) return value.round();
    return int.tryParse(value.toString());
  }

  static double? _parseNullableDouble(dynamic value) {
    if (value == null) return null;
    if (value is double) return value;
    if (value is int) return value.toDouble();
    return double.tryParse(value.toString());
  }
}