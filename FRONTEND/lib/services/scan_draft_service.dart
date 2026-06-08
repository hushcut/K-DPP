import '../models/clothing_type_option.dart';
import '../models/scan_result.dart';
import '../utils/clothing_type_catalog.dart';

class ScanDraft {
  const ScanDraft({
    required this.clothingType,
    required this.materials,
    required this.careInstruction,
    required this.title,
    required this.isManualMaterialMode,
    this.serverHealth,
    this.serverCarbonFootprint,
    this.serverWeightGram,
    this.serverCalculationMethod,
  });

  final ClothingTypeOption clothingType;
  final Map<String, double> materials;
  final String careInstruction;
  final String title;
  final bool isManualMaterialMode;
  final int? serverHealth;
  final double? serverCarbonFootprint;
  final double? serverWeightGram;
  final String? serverCalculationMethod;

  String get category => clothingType.category;
}

class ScanDraftService {
  const ScanDraftService();

  ClothingTypeOption inferInitialType(ScanResult result) {
    return ClothingTypeCatalog.inferFromCategory(result.category);
  }

  ScanDraft buildFromResult({
    required ScanResult result,
    required ClothingTypeOption clothingType,
  }) {
    final scannedTitle = result.title?.trim();

    return ScanDraft(
      clothingType: clothingType,
      materials: result.displayMaterials,
      careInstruction: result.careInstruction,
      title: scannedTitle?.isNotEmpty == true
          ? scannedTitle!
          : clothingType.defaultTitle,
      isManualMaterialMode: false,
      serverHealth: result.health,
      serverCarbonFootprint: result.carbonFootprint,
      serverWeightGram: result.weightGram,
      serverCalculationMethod: result.calculationMethod,
    );
  }

  ScanDraft buildManual({required ClothingTypeOption clothingType}) {
    return ScanDraft(
      clothingType: clothingType,
      materials: const {},
      careInstruction: '라벨의 세탁 지침을 확인해 주세요.',
      title: clothingType.defaultTitle,
      isManualMaterialMode: true,
    );
  }
}
