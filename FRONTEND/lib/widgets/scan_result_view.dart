import 'package:flutter/material.dart';

import '../models/clothing_type_option.dart';
import '../services/material_catalog_controller.dart';
import '../theme/app_palette.dart';
import '../utils/clothing_estimator.dart';
import '../utils/leading_zero_trimmer.dart';
import '../utils/percent_limit_formatter.dart';
import '../utils/scan_calculation_resolver.dart';
import '../utils/scan_form_validator.dart';
import 'material_edit_controller.dart';
import 'material_input_collection.dart';
import 'material_picker_sheet.dart';
import 'number_keyboard_toolbar.dart';

/// 스캔한 의류 정보를 검토·수정하고 옷장 저장을 요청하는 결과 폼입니다.
///
/// 분석값과 편집 컨트롤러는 상위 화면이 소유하며, 이 위젯은 계산 미리보기와
/// 유효성 상태를 표시한 뒤 사용자 동작을 각 콜백으로 전달합니다.
class ScanResultView extends StatelessWidget {
  const ScanResultView({
    super.key,
    required this.formKey,
    required this.hasTriedSubmit,
    required this.isSaving,
    required this.isScanFailed,
    this.scanFailureMessage,
    required this.titleController,
    required this.selectedClothingType,
    required this.materialInputs,
    this.materialCatalog,
    required this.scannedCare,
    this.rawOcrPreview = '',
    required this.originalMaterials,
    this.serverHealth,
    this.serverCarbonFootprint,
    this.serverWeightGram,
    this.serverCalculationMethod,
    required this.validateTitle,
    required this.validateMaterialName,
    required this.validateMaterialValue,
    required this.onSelectClothingType,
    required this.onAddMaterial,
    required this.onRemoveMaterial,
    required this.onSubmit,
    required this.onReset,
  });

  /// 상위 화면이 폼 검증을 실행할 때 사용하는 키입니다.
  final GlobalKey<FormState> formKey;

  // 검증, 저장, 스캔 실패 및 수동 입력 화면 상태입니다.
  final bool hasTriedSubmit;
  final bool isSaving;
  final bool isScanFailed;
  /// 스캔 실패 시 사용자에게 보여 줄 선택적 상세 메시지입니다.
  final String? scanFailureMessage;

  // 사용자가 편집하는 의류명, 의류 종류, 소재 입력 목록입니다.
  final TextEditingController titleController;
  final ClothingTypeOption selectedClothingType;
  final MaterialInputCollection materialInputs;
  /// 소재 선택창이 쓰는 서버 소재 카탈로그입니다.
  /// 없으면 선택창 아이콘이 보이지 않습니다.
  final MaterialCatalogController? materialCatalog;

  // 원본 스캔의 관리 지침과 소재 구성입니다.
  final String scannedCare;

  /// 서버가 인식한 라벨 원문입니다. 직접 입력 모드에서만, 값이 있을 때만
  /// 참고용으로 표시합니다.
  final String rawOcrPreview;

  final Map<String, double> originalMaterials;
  // 소재 동일성 및 값·무게·계산 방식 검증을 통과할 때 활용하는 서버 계산 정보입니다.
  final int? serverHealth;
  final double? serverCarbonFootprint;
  final double? serverWeightGram;
  final String? serverCalculationMethod;
  // 제목·소재명·함유율 입력에 적용할 상위 폼 검증 함수입니다.
  final FormFieldValidator<String> validateTitle;
  final FormFieldValidator<String> validateMaterialName;
  final FormFieldValidator<String> validateMaterialValue;
  // 선택, 소재 추가·삭제, 저장 및 초기화 동작을 상위 화면에 전달하는 콜백입니다.
  // (소재 텍스트 변경은 materialInputs 구독으로 자체 갱신되어 콜백이 필요 없습니다)
  final VoidCallback onSelectClothingType;
  final VoidCallback onAddMaterial;
  final ValueChanged<int> onRemoveMaterial;
  final VoidCallback onSubmit;
  final VoidCallback onReset;

  @override
  Widget build(BuildContext context) {
    // 소재 입력에 반응하는 계산(합계·미리보기)은 화면 전체를 다시 그리지 않고
    // 아래 ListenableBuilder 구역 안에서만 수행합니다. 키 입력마다 이미지
    // 미리보기까지 통째로 리빌드되던 비용을 없애기 위함입니다.
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);
    final backgroundColor = palette.background;
    final cardColor = palette.card;
    final borderColor = isDark ? const Color(0xFF2C2C2E) : Colors.grey.shade300;
    final primaryText = palette.textPrimary;
    final secondaryText = palette.textSecondary;
    final inputFillColor = isDark ? const Color(0xFF2A2A2E) : Colors.white;
    final previewBoxColor = isDark
        ? const Color(0xFF1F2A3D)
        : Colors.green.shade50;
    final previewBorderColor = isDark
        ? const Color(0xFF2C4C7A)
        : Colors.green.shade100;
    final careBoxColor = isDark ? const Color(0xFF1E2A3A) : Colors.blue.shade50;
    final statusColor = isScanFailed ? Colors.orangeAccent : Colors.green;
    final statusIcon = isScanFailed ? Icons.error_outline : Icons.check_circle;
    final statusTitle = isScanFailed ? '스캔 실패' : '스캔 완료!';
    final statusSubtitle = isScanFailed
        ? 'AI가 라벨을 정확히 인식하지 못했어요. 소재와 혼용률을 직접 입력해 주세요.'
        : '의류 무게 기준과 분석 결과를 확인해 주세요.';

    final form = Container(
      color: backgroundColor,
      child: Form(
        key: formKey,
        autovalidateMode: hasTriedSubmit
            ? AutovalidateMode.always
            : AutovalidateMode.disabled,
        child: SingleChildScrollView(
          keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
          // 스캔 화면에는 하단 내비게이션이 없으므로 여백은 최소한만 둡니다.
          padding: const EdgeInsets.fromLTRB(24, 24, 24, 36),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(child: Icon(statusIcon, color: statusColor, size: 60)),
              const SizedBox(height: 16),
              Center(
                child: Text(
                  statusTitle,
                  style: TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                    color: primaryText,
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Center(
                child: Text(
                  statusSubtitle,
                  style: TextStyle(fontSize: 14, color: secondaryText),
                  textAlign: TextAlign.center,
                ),
              ),
              const SizedBox(height: 32),
              Text(
                '기본 정보 수정',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: primaryText,
                ),
              ),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: cardColor,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: borderColor),
                ),
                child: Column(
                  children: [
                    TextFormField(
                      controller: titleController,
                      validator: validateTitle,
                      enabled: !isSaving,
                      onTapOutside: dismissKeyboardOnTapOutside,
                      style: TextStyle(color: primaryText),
                      decoration: InputDecoration(
                        filled: true,
                        fillColor: inputFillColor,
                        labelText: '의류 이름',
                        labelStyle: TextStyle(color: secondaryText),
                        hintText: '예: 코튼 맨투맨',
                        hintStyle: TextStyle(color: secondaryText),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(10),
                        ),
                        prefixIcon: const Icon(Icons.checkroom_outlined),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Semantics(
                      label:
                          '무게 기준, ${selectedClothingType.label}, ${selectedClothingType.weightDisplayText}',
                      button: true,
                      // 입력칸 채움색이 누름 효과를 덮으므로 효과는 칸 위에 겹쳐 그립니다.
                      child: Stack(
                        children: [
                          InputDecorator(
                            decoration: InputDecoration(
                              filled: true,
                              fillColor: inputFillColor,
                              labelText: '무게 기준',
                              labelStyle: TextStyle(color: secondaryText),
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(10),
                              ),
                              prefixIcon: const Icon(Icons.scale_outlined),
                              suffixIcon: Icon(
                                Icons.keyboard_arrow_down,
                                color: secondaryText,
                              ),
                            ),
                            child: ExcludeSemantics(
                              child: Text(
                                '${selectedClothingType.label} · ${selectedClothingType.weightDisplayText}',
                                softWrap: true,
                                style: TextStyle(
                                  color: primaryText,
                                  fontSize: 15,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          ),
                          Positioned.fill(
                            child: Material(
                              type: MaterialType.transparency,
                              child: InkWell(
                                onTap: isSaving ? null : onSelectClothingType,
                                borderRadius: BorderRadius.circular(10),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              ListenableBuilder(
                listenable: materialInputs,
                builder: (context, _) {
                  final calculation = ScanCalculationResolver.resolve(
                    materials: materialInputs.collectEditedMaterials(),
                    clothingType: selectedClothingType,
                    originalMaterials: originalMaterials,
                    serverHealth: serverHealth,
                    serverCarbonFootprint: serverCarbonFootprint,
                    serverWeightGram: serverWeightGram,
                    serverCalculationMethod: serverCalculationMethod,
                  );

                  return Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: previewBoxColor,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: previewBorderColor),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Icon(
                          Icons.analytics_outlined,
                          color: Colors.green,
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            '무게 기준: ${selectedClothingType.label} · ${selectedClothingType.weightDisplayText}\n'
                            '${calculation.usesServerHealth ? '건강도' : '예상 건강도'}: ${calculation.health}%\n'
                            '${calculation.usesServerCarbon ? '최종 탄소발자국' : '임시 예상 탄소발자국'}: ${calculation.carbonFootprint.toStringAsFixed(1)} kg CO2eq',
                            softWrap: true,
                            style: TextStyle(
                              fontSize: 14,
                              color: primaryText,
                              height: 1.5,
                            ),
                          ),
                        ),
                      ],
                    ),
                  );
                },
              ),
              if (isScanFailed) ...[
                const SizedBox(height: 16),
                _buildManualNotice(
                  isScanFailed: isScanFailed,
                  failureMessage: scanFailureMessage,
                  primaryText: primaryText,
                  secondaryText: secondaryText,
                  borderColor: borderColor,
                  cardColor: cardColor,
                ),
                if (rawOcrPreview.trim().isNotEmpty) ...[
                  const SizedBox(height: 12),
                  _buildOcrPreview(
                    primaryText: primaryText,
                    secondaryText: secondaryText,
                    borderColor: borderColor,
                    cardColor: cardColor,
                  ),
                ],
              ],
              const SizedBox(height: 24),
              Text(
                isScanFailed ? '직접 소재 입력' : '소재 및 혼용률',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: primaryText,
                ),
              ),
              const SizedBox(height: 8),
              ListenableBuilder(
                listenable: materialInputs,
                builder: (context, _) {
                  final editedMaterials = materialInputs
                      .collectEditedMaterials();
                  final totalMaterials =
                      ClothingEstimator.calculateMaterialsTotal(
                        editedMaterials,
                      );
                  final isTotalValid =
                      editedMaterials.isNotEmpty &&
                      ClothingEstimator.isMaterialsTotalValid(editedMaterials);

                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Semantics(
                        liveRegion: hasTriedSubmit && !isTotalValid,
                        child: Text(
                          materialInputs.isEmpty
                              ? '소재를 직접 추가해 주세요.'
                              : '현재 소재 합계: ${totalMaterials.toStringAsFixed(1)}%',
                          style: TextStyle(
                            color: materialInputs.isEmpty
                                ? secondaryText
                                : isTotalValid
                                ? Colors.green
                                : Colors.redAccent,
                            fontWeight: FontWeight.w600,
                            fontSize: 13,
                          ),
                        ),
                      ),
                      if (!materialInputs.isEmpty && !isTotalValid) ...[
                        const SizedBox(height: 8),
                        _buildMaterialTotalHint(
                          totalMaterials: totalMaterials,
                          primaryText: primaryText,
                          secondaryText: secondaryText,
                          isDark: isDark,
                        ),
                      ],
                    ],
                  );
                },
              ),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: cardColor,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: borderColor),
                ),
                child: Column(
                  children: [
                    if (materialInputs.isEmpty)
                      _buildEmptyMaterialEditor(secondaryText: secondaryText)
                    else
                      ...List.generate(
                        materialInputs.length,
                        (index) => Padding(
                          padding: EdgeInsets.only(
                            bottom: index == materialInputs.length - 1 ? 0 : 12,
                          ),
                          child: _buildMaterialRow(
                            context,
                            index,
                            primaryText: primaryText,
                            secondaryText: secondaryText,
                            inputFillColor: inputFillColor,
                          ),
                        ),
                      ),
                    const SizedBox(height: 14),
                    // 합계가 허용 범위(100.5%)를 넘으면 소재를 더 넣어도 맞출 수 없어 추가를 막습니다.
                    // 이때는 항상 위의 빨간 안내가 떠 있어 버튼이 꺼진 이유를 보여 줍니다.
                    ListenableBuilder(
                      listenable: materialInputs,
                      builder: (context, _) {
                        final isTotalOver =
                            ClothingEstimator.isMaterialsTotalOver(
                              materialInputs.collectEditedMaterials(),
                            );

                        return SizedBox(
                          width: double.infinity,
                          child: OutlinedButton.icon(
                            onPressed: isSaving || isTotalOver
                                ? null
                                : onAddMaterial,
                            icon: const Icon(Icons.add),
                            label: const Text('소재 추가'),
                          ),
                        );
                      },
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: careBoxColor,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.local_laundry_service, color: Colors.blue),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        '${isScanFailed ? '관리 지침' : 'AI 분석 세탁 지침'}\n$scannedCare',
                        softWrap: true,
                        style: TextStyle(
                          fontSize: 14,
                          color: primaryText,
                          height: 1.5,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 40),
              SizedBox(
                width: double.infinity,
                height: 50,
                child: ElevatedButton(
                  onPressed: isSaving ? null : onSubmit,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppPalette.accent,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                  child: isSaving
                      ? Semantics(
                          label: '의류 저장 중',
                          liveRegion: true,
                          child: const SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(
                              strokeWidth: 2.4,
                              color: Colors.white,
                            ),
                          ),
                        )
                      : const Text(
                          '옷장에 저장하기',
                          style: TextStyle(
                            fontSize: 16,
                            color: Colors.white,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                ),
              ),
              const SizedBox(height: 12),
              Center(
                child: TextButton(
                  onPressed: isSaving ? null : onReset,
                  child: Text('다시 촬영', style: TextStyle(color: secondaryText)),
                ),
              ),
            ],
          ),
        ),
      ),
    );

    // 이 화면은 키보드만큼 줄어든 본문을 채우므로, 맨 아래에 둔 막대가 키보드 바로 위에 놓입니다.
    return Column(
      children: [
        Expanded(child: form),
        _buildNumberKeyboardToolbar(context),
      ],
    );
  }

  // 자동 인식값을 사용할 수 없을 때 수동 입력 사유와 안내를 표시합니다.
  Widget _buildManualNotice({
    required bool isScanFailed,
    required String? failureMessage,
    required Color primaryText,
    required Color secondaryText,
    required Color borderColor,
    required Color cardColor,
  }) {
    final normalizedMessage = failureMessage?.trim();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: borderColor),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.edit_note, color: AppPalette.accent),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  isScanFailed ? '직접 입력 모드' : '직접 입력 안내',
                  style: TextStyle(
                    color: primaryText,
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  normalizedMessage?.isNotEmpty == true
                      ? normalizedMessage!
                      : 'AI가 소재 정보를 정확히 읽지 못했어요. 라벨에 적힌 소재명과 혼용률을 직접 추가해 주세요.',
                  softWrap: true,
                  style: TextStyle(
                    color: secondaryText,
                    fontSize: 13,
                    height: 1.5,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // 소재를 못 읽었어도 AI가 읽어낸 라벨 글자는 남아 있습니다. 사용자가 사진을
  // 다시 열어 보지 않고도 무엇이 읽혔는지 확인하고 직접 입력할 수 있게 보여 줍니다.
  Widget _buildOcrPreview({
    required Color primaryText,
    required Color secondaryText,
    required Color borderColor,
    required Color cardColor,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: borderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.text_snippet_outlined, size: 18, color: secondaryText),
              const SizedBox(width: 8),
              Text(
                '인식된 라벨 원문',
                style: TextStyle(
                  color: primaryText,
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          SelectableText(
            rawOcrPreview.trim(),
            maxLines: 6,
            style: TextStyle(
              color: secondaryText,
              fontSize: 13,
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyMaterialEditor({required Color secondaryText}) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 18, horizontal: 12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: secondaryText.withValues(alpha: 0.25)),
      ),
      child: Text(
        '인식된 소재가 없어요. 아래 버튼으로 소재와 혼용률을 직접 추가해 주세요.',
        textAlign: TextAlign.center,
        style: TextStyle(color: secondaryText, fontSize: 13, height: 1.5),
      ),
    );
  }

  // 소재 함유율 합계와 100%의 차이를 계산해 보정 방향을 안내합니다.
  Widget _buildMaterialTotalHint({
    required double totalMaterials,
    required Color primaryText,
    required Color secondaryText,
    required bool isDark,
  }) {
    final difference = 100 - totalMaterials;
    final isShort = difference > 0;
    final amount = difference.abs();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF2A1E1E) : const Color(0xFFFFF4F2),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.redAccent.withValues(alpha: 0.35)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(
            Icons.info_outline_rounded,
            color: Colors.redAccent,
            size: 18,
          ),
          const SizedBox(width: 8),
          Expanded(
            // 문장마다 줄을 나눠 한 줄씩 읽히게 합니다. 둘째 줄은 좁은 폰에서도 한 줄에 들도록 짧게 둡니다.
            child: Text(
              isShort
                  ? '100%까지 ${_formatMaterialGap(amount)}% 부족해요.\n저장 전 소재 비율을 조정해 주세요.'
                  : '100%보다 ${_formatMaterialGap(amount)}% 많아요.\n줄여야 저장하거나 소재를 더 추가할 수 있어요.',
              style: TextStyle(color: primaryText, fontSize: 12, height: 1.45),
            ),
          ),
        ],
      ),
    );
  }

  String _formatMaterialGap(double value) {
    if (value % 1 == 0) {
      return value.toInt().toString();
    }

    return value.toStringAsFixed(1);
  }

  // 소재 선택창에서 고른 소재를 그 행의 소재명에 넣습니다.
  Future<void> _pickMaterialFromCatalog(
    BuildContext context,
    MaterialEditController item,
  ) async {
    final catalog = materialCatalog;
    if (catalog == null) return;

    // 열기 전에 키보드를 내립니다. 그대로 두면 선택창이 닫힐 때 포커스가
    // 입력란으로 돌아와 키보드가 다시 뜹니다.
    FocusManager.instance.primaryFocus?.unfocus();

    // 다른 줄에 이미 넣은 소재는 목록에서 뺍니다. 이 줄의 소재는 그대로 보입니다.
    final picked = await showMaterialPickerSheet(
      context: context,
      catalog: catalog,
      initialQuery: item.nameController.text,
      excludedNames: _materialNamesOfOtherRows(item),
    );

    // 선택창이 열린 동안 이 행이 지워졌다면 컨트롤러가 이미 해제됐으므로 쓰지 않습니다.
    // 앞 행만 지워져 위치가 바뀐 경우에는 같은 행에 그대로 씁니다.
    if (picked == null || !materialInputs.contains(item)) return;

    // 스캔으로 채워진 행과 같은 한글 표시명으로 넣습니다.
    // 계산·건강도는 MaterialName이 한글명도 표준명으로 바꿔 인식합니다.
    item.nameController.text = picked.nameKo;
  }

  // 이 줄을 뺀 나머지 줄의 소재명입니다. 줄이 지워져 위치가 바뀌어도 맞게, 번호가 아니라
  // 컨트롤러 자체로 이 줄을 가립니다.
  List<String> _materialNamesOfOtherRows(MaterialEditController item) {
    return [
      for (var i = 0; i < materialInputs.length; i++)
        if (!identical(materialInputs[i], item))
          materialInputs[i].nameController.text,
    ];
  }

  // 이 줄보다 앞에 있는 줄들의 소재명입니다. 같은 소재 오류를 뒤 줄에만 보이기 위한 비교 대상이며,
  // 검증 시점의 글자를 읽도록 매번 새로 모읍니다(앞 줄을 고치면 뒤 줄 오류가 바로 사라집니다).
  List<String> _materialNamesBeforeRow(MaterialEditController item) {
    final names = <String>[];
    for (var i = 0; i < materialInputs.length; i++) {
      final row = materialInputs[i];
      if (identical(row, item)) break;
      names.add(row.nameController.text);
    }
    return names;
  }

  // iOS 숫자 키패드에는 확인 키가 없어, 함유율 칸에 포커스가 있는 동안 [다음]·[완료] 버튼을
  // 그립니다. 포커스가 바뀔 때마다 FocusManager가 알려 주므로 이 부분만 다시 그립니다.
  Widget _buildNumberKeyboardToolbar(BuildContext context) {
    if (!NumberKeyboardToolbar.isNeeded(context)) return const SizedBox.shrink();

    return ListenableBuilder(
      listenable: FocusManager.instance,
      builder: (context, _) {
        final index = _indexOfFocusedPercent();
        if (index == null) return const SizedBox.shrink();

        return NumberKeyboardToolbar(
          onNext: _focusNextRowName(index),
          onDone: () => FocusManager.instance.primaryFocus?.unfocus(),
        );
      },
    );
  }

  int? _indexOfFocusedPercent() {
    for (var i = 0; i < materialInputs.length; i++) {
      if (materialInputs[i].percentFocusNode.hasFocus) return i;
    }
    return null;
  }

  // 함유율 다음 차례인 다음 행의 소재명으로 포커스를 옮깁니다. 마지막 행이면 null입니다.
  VoidCallback? _focusNextRowName(int index) {
    if (index >= materialInputs.length - 1) return null;

    final next = materialInputs[index + 1];
    return () {
      // 그사이 그 행이 지워졌다면 포커스 노드가 이미 해제됐으므로 건드리지 않습니다.
      if (materialInputs.contains(next)) next.nameFocusNode.requestFocus();
    };
  }

  // 소재명 입력(선택창 아이콘)과 함유율 입력, 항목 삭제 버튼으로 한 편집 행을 만듭니다.
  Widget _buildMaterialRow(
    BuildContext context,
    int index, {
    required Color primaryText,
    required Color secondaryText,
    required Color inputFillColor,
  }) {
    final item = materialInputs[index];
    final focusNextRowName = _focusNextRowName(index);

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: TextFormField(
            controller: item.nameController,
            focusNode: item.nameFocusNode,
            // 상위 검증(빈 값)을 통과하면 앞 줄과 같은 소재인지 봅니다(면 = 코튼 = cotton).
            validator: (value) =>
                validateMaterialName(value) ??
                ScanFormValidator.validateMaterialNameUnique(
                  value,
                  _materialNamesBeforeRow(item),
                ),
            enabled: !isSaving,
            // 키보드의 '다음'은 같은 행의 함유율로 옮깁니다. 기본 동작(다음 포커스 대상)은
            // 목록 아이콘 같은 버튼으로 갈 수 있어 직접 지정합니다.
            textInputAction: TextInputAction.next,
            onEditingComplete: item.percentFocusNode.requestFocus,
            onTapOutside: dismissKeyboardOnTapOutside,
            style: TextStyle(color: primaryText, fontSize: 14),
            decoration: InputDecoration(
              filled: true,
              fillColor: inputFillColor,
              labelText: '소재명',
              hintText: '예: 면',
              labelStyle: TextStyle(color: secondaryText),
              hintStyle: TextStyle(color: secondaryText),
              isDense: true,
              contentPadding: const EdgeInsets.fromLTRB(12, 12, 12, 10),
              // 좁은 화면에서 오류 문구가 한 줄로 잘리지 않게 합니다.
              errorMaxLines: 2,
              suffixIcon: materialCatalog == null
                  ? null
                  : IconButton(
                      onPressed: isSaving
                          ? null
                          : () => _pickMaterialFromCatalog(context, item),
                      tooltip: '목록에서 소재 고르기',
                      icon: Icon(
                        Icons.format_list_bulleted_rounded,
                        color: secondaryText,
                        size: 20,
                      ),
                    ),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(
          width: 86,
          child: TextFormField(
            controller: item.percentController,
            focusNode: item.percentFocusNode,
            validator: validateMaterialValue,
            enabled: !isSaving,
            // Android 키보드의 동작 키도 iOS 막대와 같은 순서로 옮깁니다.
            // 마지막 행은 '완료'라 기본 동작대로 키보드를 닫습니다.
            textInputAction: focusNextRowName == null
                ? TextInputAction.done
                : TextInputAction.next,
            onEditingComplete: focusNextRowName,
            onTapOutside: dismissKeyboardOnTapOutside,
            style: TextStyle(color: primaryText, fontSize: 14),
            textAlign: TextAlign.right,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            inputFormatters: const [
              LeadingZeroTrimmer(),
              PercentLimitFormatter(),
            ],
            decoration: InputDecoration(
              filled: true,
              fillColor: inputFillColor,
              suffixText: '%',
              suffixStyle: TextStyle(color: secondaryText),
              isDense: true,
              contentPadding: const EdgeInsets.fromLTRB(8, 12, 8, 10),
              errorMaxLines: 2,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
          ),
        ),
        const SizedBox(width: 4),
        SizedBox(
          width: 48,
          // 행 리빌드 없이도 낭독기 안내가 최신 소재명을 따라가도록,
          // 삭제 버튼만 이름 컨트롤러를 직접 구독합니다.
          child: ValueListenableBuilder<TextEditingValue>(
            valueListenable: item.nameController,
            builder: (context, nameValue, _) {
              final trimmedName = nameValue.text.trim();

              return IconButton(
                onPressed: isSaving ? null : () => onRemoveMaterial(index),
                tooltip: '${trimmedName.isEmpty ? '소재' : trimmedName} 삭제',
                icon: Icon(Icons.close, color: secondaryText, size: 20),
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
              );
            },
          ),
        ),
      ],
    );
  }
}
