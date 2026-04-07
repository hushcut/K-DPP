class Clothes {
  final String title;
  final String category;
  final int health;
  final Map<String, double> materials;
  final String careInstruction;
  final double carbonFootprint;

  Clothes({
    required this.title,
    required this.category,
    required this.health,
    required this.materials,
    required this.careInstruction,
    required this.carbonFootprint,
  });

  Clothes copyWith({
    String? title,
    String? category,
    int? health,
    Map<String, double>? materials,
    String? careInstruction,
    double? carbonFootprint,
  }) {
    return Clothes(
      title: title ?? this.title,
      category: category ?? this.category,
      health: health ?? this.health,
      materials: materials ?? this.materials,
      careInstruction: careInstruction ?? this.careInstruction,
      carbonFootprint: carbonFootprint ?? this.carbonFootprint,
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
      careInstruction: json['careInstruction']?.toString() ??
          json['care_instruction']?.toString() ??
          '',
      carbonFootprint: _parseDouble(json['carbonFootprint'] ?? json['carbon_footprint']),
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
}