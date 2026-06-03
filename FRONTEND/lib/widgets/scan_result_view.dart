import 'package:flutter/material.dart';

import '../models/clothing_type_option.dart';
import '../utils/clothing_estimator.dart';
import 'material_input_collection.dart';

class ScanResultView extends StatelessWidget {
  const ScanResultView({
    super.key,
    required this.formKey,
    required this.hasTriedSubmit,
    required this.isManualMaterialMode,
    required this.titleController,
    required this.selectedClothingType,
    required this.materialInputs,
    required this.scannedCare,
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
  final bool isManualMaterialMode;
  final TextEditingController titleController;
  final ClothingTypeOption selectedClothingType;
  final MaterialInputCollection materialInputs;
  final String scannedCare;
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
    final previewHealth = ClothingEstimator.estimateInitialHealth(
      editedMaterials,
    );
    final previewCarbon = ClothingEstimator.estimateCarbonFootprint(
      editedMaterials,
      selectedClothingType,
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
    final secondaryText = isDark ? const Color(0xFFD1D1D6) : Colors.grey;
    final inputFillColor = isDark ? const Color(0xFF2A2A2E) : Colors.white;
    final previewBoxColor = isDark
        ? const Color(0xFF1F2A3D)
        : Colors.green.shade50;
    final previewBorderColor = isDark
        ? const Color(0xFF2C4C7A)
        : Colors.green.shade100;
    final careBoxColor = isDark ? const Color(0xFF1E2A3A) : Colors.blue.shade50;

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
              const Center(
                child: Icon(Icons.check_circle, color: Colors.green, size: 60),
              ),
              const SizedBox(height: 16),
              Center(
                child: Text(
                  '스캔 완료!',
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
                  isManualMaterialMode
                      ? '인식하지 못한 정보를 직접 입력해 주세요.'
                      : '의류 무게 기준과 분석 결과를 확인해 주세요.',
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
                      style: TextStyle(color: primaryText),
                      decoration: InputDecoration(
                        filled: true,
                        fillColor: inputFillColor,
                        labelText: '의류 이름',
                        labelStyle: TextStyle(color: secondaryText),
                        hintText: '예: 홍길동 코튼 맨투맨',
                        hintStyle: TextStyle(color: secondaryText),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(10),
                        ),
                        prefixIcon: const Icon(Icons.checkroom_outlined),
                      ),
                    ),
                    const SizedBox(height: 16),
                    InkWell(
                      onTap: onSelectClothingType,
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
                        child: Text(
                          '${selectedClothingType.label} · ${selectedClothingType.weightDisplayText}',
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: primaryText,
                            fontSize: 15,
                            fontWeight: FontWeight.w600,
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
                        '예상 건강도: $previewHealth%\n'
                        '예상 탄소발자국: ${previewCarbon.toStringAsFixed(1)} kg CO2eq',
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
                  secondaryText: secondaryText,
                  borderColor: borderColor,
                  cardColor: cardColor,
                ),
              ],
              const SizedBox(height: 24),
              Text(
                '소재 및 혼용률',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: primaryText,
                ),
              ),
              const SizedBox(height: 8),
              Text(
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
                        onPressed: onAddMaterial,
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
                        'AI 분석 세탁 지침\n$scannedCare',
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
                  onPressed: onSubmit,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF4A4EFE),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                  child: const Text(
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
                  onPressed: onReset,
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
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.edit_note, color: Color(0xFF4A4EFE)),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              'AI가 소재 정보를 정확히 읽지 못했어요. 라벨에 적힌 소재명과 혼용률을 직접 추가해 주세요.',
              softWrap: true,
              style: TextStyle(color: secondaryText, fontSize: 13, height: 1.5),
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
          child: TextFormField(
            controller: item.nameController,
            validator: validateMaterialName,
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
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(
          width: 86,
          child: TextFormField(
            controller: item.percentController,
            validator: validateMaterialValue,
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
          width: 36,
          child: IconButton(
            onPressed: () => onRemoveMaterial(index),
            icon: Icon(Icons.close, color: secondaryText, size: 20),
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 36, minHeight: 48),
          ),
        ),
      ],
    );
  }
}
