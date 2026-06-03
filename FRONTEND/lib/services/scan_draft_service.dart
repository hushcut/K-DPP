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
  });

  final ClothingTypeOption clothingType;
  final Map<String, double> materials;
  final String careInstruction;
  final String title;
  final bool isManualMaterialMode;

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
      materials: result.materials,
      careInstruction: result.careInstruction,
      title: scannedTitle?.isNotEmpty == true
          ? scannedTitle!
          : clothingType.defaultTitle,
      isManualMaterialMode: false,
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
