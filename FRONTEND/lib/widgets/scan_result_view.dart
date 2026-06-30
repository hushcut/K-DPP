import 'package:flutter/material.dart';

import '../models/clothing_type_option.dart';
import '../services/material_catalog_api_service.dart';
import '../utils/clothing_estimator.dart';
import '../utils/scan_calculation_resolver.dart';
import 'material_input_collection.dart';

class ScanResultView extends StatelessWidget {
  const ScanResultView({
    super.key,
    required this.formKey,
    required this.hasTriedSubmit,
    required this.isSaving,
    required this.isScanFailed,
    required this.isManualMaterialMode,
    this.scanFailureMessage,
    required this.titleController,
    required this.selectedClothingType,
    required this.materialInputs,
    this.materialCatalog = const [],
    required this.scannedCare,
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
    required this.onSyncMaterialInputs,
    required this.onSubmit,
    required this.onReset,
  });

  final GlobalKey<FormState> formKey;
  final bool hasTriedSubmit;
  final bool isSaving;
  final bool isScanFailed;
  final bool isManualMaterialMode;
  final String? scanFailureMessage;
  final TextEditingController titleController;
  final ClothingTypeOption selectedClothingType;
  final MaterialInputCollection materialInputs;
  final List<MaterialCatalogItem> materialCatalog;
  final String scannedCare;
  final Map<String, double> originalMaterials;
  final int? serverHealth;
  final double? serverCarbonFootprint;
  final double? serverWeightGram;
  final String? serverCalculationMethod;
  final FormFieldValidator<String> validateTitle;
  final FormFieldValidator<String> validateMaterialName;
  final FormFieldValidator<String> validateMaterialValue;
  final VoidCallback onSelectClothingType;
  final VoidCallback onAddMaterial;
  final ValueChanged<int> onRemoveMaterial;
  final VoidCallback onSyncMaterialInputs;
  final VoidCallback onSubmit;
  final VoidCallback onReset;

  @override
  Widget build(BuildContext context) {
    final editedMaterials = materialInputs.collectEditedMaterials();
    final calculation = ScanCalculationResolver.resolve(
      materials: editedMaterials,
      clothingType: selectedClothingType,
      originalMaterials: originalMaterials,
      serverHealth: serverHealth,
      serverCarbonFootprint: serverCarbonFootprint,
      serverWeightGram: serverWeightGram,
      serverCalculationMethod: serverCalculationMethod,
    );
    final totalMaterials = ClothingEstimator.calculateMaterialsTotal(
      editedMaterials,
    );
    final isTotalValid =
        editedMaterials.isNotEmpty &&
        ClothingEstimator.isMaterialsTotalValid(editedMaterials);

    final isDark = Theme.of(context).brightness == Brightness.dark;
    final backgroundColor = isDark
        ? const Color(0xFF121212)
        : const Color(0xFFF8F9FC);
    final cardColor = isDark ? const Color(0xFF1C1C1E) : Colors.white;
    final borderColor = isDark ? const Color(0xFF2C2C2E) : Colors.grey.shade300;
    final primaryText = isDark ? Colors.white : const Color(0xFF111111);
    final secondaryText = isDark
        ? const Color(0xFFD1D1D6)
        : const Color(0xFF5F6368);
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
        : isManualMaterialMode
        ? '인식하지 못한 정보를 직접 입력해 주세요.'
        : '의류 무게 기준과 분석 결과를 확인해 주세요.';

    return Container(
      color: backgroundColor,
      child: Form(
        key: formKey,
        autovalidateMode: hasTriedSubmit
            ? AutovalidateMode.always
            : AutovalidateMode.disabled,
        child: SingleChildScrollView(
          keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
          padding: const EdgeInsets.fromLTRB(24, 24, 24, 140),
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
                      child: InkWell(
                        onTap: isSaving ? null : onSelectClothingType,
                        borderRadius: BorderRadius.circular(10),
                        child: InputDecorator(
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
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: previewBoxColor,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: previewBorderColor),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.analytics_outlined, color: Colors.green),
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
              ),
              if (isManualMaterialMode) ...[
                const SizedBox(height: 16),
                _buildManualNotice(
                  isScanFailed: isScanFailed,
                  failureMessage: scanFailureMessage,
                  primaryText: primaryText,
                  secondaryText: secondaryText,
                  borderColor: borderColor,
                  cardColor: cardColor,
                ),
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
                            index,
                            primaryText: primaryText,
                            secondaryText: secondaryText,
                            inputFillColor: inputFillColor,
                          ),
                        ),
                      ),
                    const SizedBox(height: 14),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        onPressed: isSaving ? null : onAddMaterial,
                        icon: const Icon(Icons.add),
                        label: const Text('소재 추가'),
                      ),
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
                    backgroundColor: const Color(0xFF4A4EFE),
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
  }

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
          const Icon(Icons.edit_note, color: Color(0xFF4A4EFE)),
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
            child: Text(
              isShort
                  ? '100%까지 ${_formatMaterialGap(amount)}% 부족해요. 저장 전 소재 비율을 조정해 주세요.'
                  : '100%보다 ${_formatMaterialGap(amount)}% 많아요. 저장 전 소재 비율을 조정해 주세요.',
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

  Widget _buildMaterialRow(
    int index, {
    required Color primaryText,
    required Color secondaryText,
    required Color inputFillColor,
  }) {
    final item = materialInputs[index];

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: RawAutocomplete<MaterialCatalogItem>(
            textEditingController: item.nameController,
            focusNode: item.nameFocusNode,
            displayStringForOption: (option) => option.nameEn,
            optionsBuilder: (textEditingValue) {
              if (materialCatalog.isEmpty) {
                return const Iterable<MaterialCatalogItem>.empty();
              }

              return materialCatalog
                  .where((option) => option.matches(textEditingValue.text))
                  .take(8);
            },
            onSelected: (option) {
              item.nameController.text = option.nameEn;
              onSyncMaterialInputs();
            },
            fieldViewBuilder:
                (context, controller, focusNode, onFieldSubmitted) {
                  return TextFormField(
                    controller: controller,
                    focusNode: focusNode,
                    validator: validateMaterialName,
                    enabled: !isSaving,
                    style: TextStyle(color: primaryText, fontSize: 14),
                    decoration: InputDecoration(
                      filled: true,
                      fillColor: inputFillColor,
                      labelText: '소재명',
                      hintText: '예: cotton',
                      labelStyle: TextStyle(color: secondaryText),
                      hintStyle: TextStyle(color: secondaryText),
                      isDense: true,
                      contentPadding: const EdgeInsets.fromLTRB(12, 12, 12, 10),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10),
                      ),
                    ),
                    onChanged: (_) => onSyncMaterialInputs(),
                    onFieldSubmitted: (_) => onFieldSubmitted(),
                  );
                },
            optionsViewBuilder: (context, onSelected, options) {
              final optionList = options.toList(growable: false);

              return Align(
                alignment: Alignment.topLeft,
                child: Material(
                  elevation: 8,
                  color: inputFillColor,
                  borderRadius: BorderRadius.circular(10),
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(
                      minWidth: 190,
                      maxWidth: 260,
                      maxHeight: 260,
                    ),
                    child: ListView.separated(
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      shrinkWrap: true,
                      itemCount: optionList.length,
                      separatorBuilder: (context, index) => Divider(
                        height: 1,
                        color: secondaryText.withValues(alpha: 0.16),
                      ),
                      itemBuilder: (context, optionIndex) {
                        final option = optionList[optionIndex];

                        return InkWell(
                          onTap: () => onSelected(option),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 10,
                            ),
                            child: Text(
                              option.label,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                color: primaryText,
                                fontSize: 14,
                              ),
                            ),
                          ),
                        );
                      },
                    ),
                  ),
                ),
              );
            },
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(
          width: 86,
          child: TextFormField(
            controller: item.percentController,
            validator: validateMaterialValue,
            enabled: !isSaving,
            style: TextStyle(color: primaryText, fontSize: 14),
            textAlign: TextAlign.right,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: InputDecoration(
              filled: true,
              fillColor: inputFillColor,
              suffixText: '%',
              suffixStyle: TextStyle(color: secondaryText),
              isDense: true,
              contentPadding: const EdgeInsets.fromLTRB(8, 12, 8, 10),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
            onChanged: (_) => onSyncMaterialInputs(),
          ),
        ),
        const SizedBox(width: 4),
        SizedBox(
          width: 48,
          child: IconButton(
            onPressed: isSaving ? null : () => onRemoveMaterial(index),
            tooltip:
                '${item.nameController.text.trim().isEmpty ? '소재' : item.nameController.text.trim()} 삭제',
            icon: Icon(Icons.close, color: secondaryText, size: 20),
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
          ),
        ),
      ],
    );
  }
}
