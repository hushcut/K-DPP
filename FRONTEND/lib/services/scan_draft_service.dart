import '../models/clothing_type_option.dart';
import '../models/scan_result.dart';
import '../utils/clothing_type_catalog.dart';
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
      notices: List.unmodifiable([
        ...ScanWarningNotices.forSuccess(result.warnings),
        ?_unsupportedMaterialNotice(result),
      ]),
      serverHealth: result.health,
      serverCarbonFootprint: result.carbonFootprint,
      serverWeightGram: result.weightGram,
      serverCalculationMethod: result.calculationMethod,
    );
  }

  /// 소재를 직접 입력하는 수동 초안을 만든다.
  ///
  /// 자동 분석이 실패해도 서버가 부분 인식 결과를 함께 보내면 그대로 초기값에
  /// 채워, 이미 인식된 값을 사용자가 다시 입력하지 않게 한다. 서버가 보내지
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
      materials: _sanitizeMaterials(partialMaterials),
      careInstruction: normalizedCare?.isNotEmpty == true
          ? normalizedCare!
          : ScanResult.defaultCareInstruction,
      title: clothingType.defaultTitle,
      isManualMaterialMode: true,
      rawOcrPreview: _sanitizeOcrPreview(rawOcrPreview),
    );
  }

  /// 서버가 `is_supported: false` 로 표시한 소재(AI 는 읽지만 서버 계수표에 없는 소재)를
  /// 결과 화면에서 미리 알린다. 서버 계산은 이 소재를 거절하고 앱은 그때 저장하지 않으므로
  /// (AI 연동 협의안 R1), 저장 버튼을 누르기 전에 소재를 확인하게 한다. 이름은 편집 폼에 보이는
  /// 표시명이고, 계산 거절 배너(`CarbonApiException.userMessage`)처럼 첫 소재와 남은 개수만 쓴다.
  String? _unsupportedMaterialNotice(ScanResult result) {
    final names = [
      for (final detail in result.materialDetails)
        if (!detail.isSupported) detail.displayName,
    ];

    if (names.isEmpty) return null;

    final others = names.length - 1;
    final label = others == 0 ? names.first : '${names.first} 외 $others개';

    return '$label 소재는 탄소 계산 기준이 없어 이대로는 저장할 수 없어요. 소재를 확인해 주세요.';
  }

  /// 이름이 비었거나 폼에서 고칠 수 없는 비율(NaN·무한대·음수)은 제외한다.
  Map<String, double> _sanitizeMaterials(Map<String, double> materials) {
    final sanitized = <String, double>{};

    for (final entry in materials.entries) {
      final name = entry.key.trim();
      final ratio = entry.value;

      if (name.isEmpty || !ratio.isFinite || ratio < 0) continue;

      sanitized[name] = ratio;
    }

    return Map.unmodifiable(sanitized);
  }

  /// 서버가 상한(220자)을 지키지 않아도 화면이 무너지지 않도록 길이를 자른다.
  String _sanitizeOcrPreview(String? rawOcrPreview) {
    final preview = rawOcrPreview?.trim() ?? '';

    if (preview.length <= _maxOcrPreviewLength) return preview;

    return '${preview.substring(0, _maxOcrPreviewLength)}...';
  }
}
