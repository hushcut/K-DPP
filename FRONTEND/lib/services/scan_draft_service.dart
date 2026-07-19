import '../models/clothing_type_option.dart';
import '../models/scan_result.dart';
import '../utils/clothing_type_catalog.dart';

/// 스캔 결과 편집 화면을 초기화하는 데 필요한 임시 입력 상태다.
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

/// AI 스캔 결과 또는 수동 입력 선택을 화면용 초안으로 변환한다.
class ScanDraftService {
  const ScanDraftService();

  /// 스캔 결과의 카테고리로 최초 의류 유형을 추론한다.
  ClothingTypeOption inferInitialType(ScanResult result) {
    return ClothingTypeCatalog.inferFromCategory(result.category);
  }

  /// 서버 분석값을 보존하면서 비어 있는 제목은 유형별 기본 제목으로 보완한다.
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
      serverHealth: result.health,
      serverCarbonFootprint: result.carbonFootprint,
      serverWeightGram: result.weightGram,
      serverCalculationMethod: result.calculationMethod,
    );
  }

  /// 소재를 직접 입력할 수 있도록 빈 소재 목록의 수동 초안을 만든다.
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
