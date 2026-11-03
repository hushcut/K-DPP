import '../models/clothing_type_option.dart';
import '../models/scan_result.dart';
import '../utils/clothing_type_catalog.dart';
import '../utils/material_name.dart';
import '../utils/scan_warning_notices.dart';

/// 스캔 결과 편집 화면을 초기화하는 데 필요한 임시 입력 상태다.
class ScanDraft {
  const ScanDraft({
    required this.clothingType,
    required this.materials,
    required this.careInstruction,
    required this.title,
    required this.isManualMaterialMode,
    this.rawOcrPreview = '',
    this.notices = const [],
    this.unsupportedMaterials = const [],
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

  /// 서버가 인식한 라벨 원문이다. 직접 입력 시 참고용으로만 보여 주며,
  /// 값이 없으면 빈 문자열이다.
  final String rawOcrPreview;

  /// AI 가 보낸 공개 코드를 바꾼 안내 문구(부위·가죽 추정 — R4)다. 소재를 확인하는 동안 결과 화면에
  /// 보이기만 하고 저장 이력·옷장에는 남기지 않는다. 없으면 빈 목록이다.
  final List<String> notices;

  /// 서버가 `is_supported: false` 로 표시한 소재의 표시명이다. 사용자가 폼에서 고치거나 지우면
  /// 안내도 사라져야 하므로 문구가 아니라 이름으로 넘긴다. 없으면 빈 목록이다.
  final List<String> unsupportedMaterials;

  final int? serverHealth;
  final double? serverCarbonFootprint;
  final double? serverWeightGram;
  final String? serverCalculationMethod;

  String get category => clothingType.category;
}

/// AI 스캔 결과 또는 수동 입력 선택을 화면용 초안으로 변환한다.
class ScanDraftService {
  const ScanDraftService();

  static const int _maxOcrPreviewLength = 300;

  /// 실패했지만 폼을 미리 채울 때 '직접 입력해 주세요' 대신 보이는 문구다. 채운 값은 확정이 아니라
  /// 사진에서 읽은 값이므로 확인을 부탁한다. 계산은 저장 때만 한다(DECISIONS 237·288).
  static const String prefilledFailureMessage =
      '라벨을 확실히 읽지 못했어요. 사진에서 읽은 값이 맞는지 확인해 주세요.';

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
      // 서버가 정규화한 표시명(한글 등)을 편집 폼에 그대로 사용합니다.
      materials: result.displayMaterials,
      careInstruction: result.careInstruction,
      title: scannedTitle?.isNotEmpty == true
          ? scannedTitle!
          : clothingType.defaultTitle,
      isManualMaterialMode: false,
      notices: ScanWarningNotices.forSuccess(result.warnings),
      unsupportedMaterials: List.unmodifiable([
        for (final detail in result.materialDetails)
          if (!detail.isSupported) detail.displayName,
      ]),
      serverHealth: result.health,
      serverCarbonFootprint: result.carbonFootprint,
      serverWeightGram: result.weightGram,
      serverCalculationMethod: result.calculationMethod,
    );
  }

  /// 소재를 직접 입력하는 수동 초안을 만든다.
  ///
  /// 자동 분석이 실패해도 서버가 부분 인식 결과를 함께 보내면 [prefillMaterials]로
  /// 초기값에 채워, 이미 인식된 값을 사용자가 다시 입력하지 않게 한다. 서버가 보내지
  /// 않으면 종전과 같이 빈 소재 목록과 기본 안내 문구를 쓴다.
  ScanDraft buildManual({
    required ClothingTypeOption clothingType,
    Map<String, double> partialMaterials = const {},
    String? careInstruction,
    String? rawOcrPreview,
  }) {
    final normalizedCare = careInstruction?.trim();

    return ScanDraft(
      clothingType: clothingType,
      materials: prefillMaterials(partialMaterials),
      careInstruction: normalizedCare?.isNotEmpty == true
          ? normalizedCare!
          : ScanResult.defaultCareInstruction,
      title: clothingType.defaultTitle,
      isManualMaterialMode: true,
      rawOcrPreview: _sanitizeOcrPreview(rawOcrPreview),
    );
  }

  /// 서버가 보낸 부분 인식 결과를 폼에 넣을 값으로 바꾼다. 비어 있으면 미리 채우지 않는다.
  ///
  /// 이름이 비었거나 폼에서 고칠 수 없는 비율(NaN·무한대·음수)은 제외한다. 서버는 표준명
  /// (`cotton`)으로 보내므로 성공 경로의 표시명처럼 한글로 바꾸고, 같은 소재는 합친다.
  Map<String, double> prefillMaterials(Map<String, double> materials) {
    final prefilled = <String, double>{};

    for (final entry in materials.entries) {
      final ratio = entry.value;

      if (entry.key.trim().isEmpty || !ratio.isFinite || ratio < 0) continue;

      final name = MaterialName.formName(entry.key);
      prefilled[name] = (prefilled[name] ?? 0) + ratio;
    }

    return Map.unmodifiable(prefilled);
  }

  /// 서버가 상한(220자)을 지키지 않아도 화면이 무너지지 않도록 길이를 자른다.
  String _sanitizeOcrPreview(String? rawOcrPreview) {
    final preview = rawOcrPreview?.trim() ?? '';

    if (preview.length <= _maxOcrPreviewLength) return preview;

    return '${preview.substring(0, _maxOcrPreviewLength)}...';
  }
}
