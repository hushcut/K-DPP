import 'package:flutter/material.dart';

import '../models/clothing_type_option.dart';

class ClothingTypePickerSheet extends StatefulWidget {
  const ClothingTypePickerSheet({
    super.key,
    required this.options,
    required this.initialSelection,
    required this.onSelected,
  });

  final List<ClothingTypeOption> options;
  final ClothingTypeOption initialSelection;
  final ValueChanged<ClothingTypeOption> onSelected;

  @override
  State<ClothingTypePickerSheet> createState() =>
      _ClothingTypePickerSheetState();
}

class _ClothingTypePickerSheetState extends State<ClothingTypePickerSheet> {
  final TextEditingController _directNameController = TextEditingController();
  final TextEditingController _directWeightController = TextEditingController();

  bool _isDirectInputMode = false;
  String _directCategory = '상의';
  String? _directErrorText;

  @override
  void initState() {
    super.initState();

    _directCategory = widget.initialSelection.category == '하의' ? '하의' : '상의';

    if (widget.initialSelection.isDirectWeight) {
      _directNameController.text = widget.initialSelection.label;
      _directWeightController.text = ClothingTypeOption.formatWeightGram(
        widget.initialSelection.estimatedWeightGram,
      );
    }
  }

  @override
  void dispose() {
    _directNameController.dispose();
    _directWeightController.dispose();
    super.dispose();
  }

  void _submitDirectInput() {
    final name = _directNameController.text.trim();
    final weightText = _directWeightController.text.trim();
    final weight = double.tryParse(weightText);

    if (name.isEmpty) {
      setState(() {
        _directErrorText = '의류 종류를 입력해 주세요.';
      });
      return;
    }

    if (weight == null || weight <= 0) {
      setState(() {
        _directErrorText = '실제 무게를 g 단위로 입력해 주세요.';
      });
      return;
    }

    widget.onSelected(
      ClothingTypeOption.directWeight(
        label: name,
        category: _directCategory,
        weightGram: weight,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final maxSheetHeight = MediaQuery.sizeOf(context).height * 0.78;

    return SafeArea(
      top: false,
      child: AnimatedPadding(
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
        padding: EdgeInsets.only(
          bottom: MediaQuery.viewInsetsOf(context).bottom,
        ),
        child: ConstrainedBox(
          constraints: BoxConstraints(maxHeight: maxSheetHeight),
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 180),
            switchInCurve: Curves.easeOut,
            switchOutCurve: Curves.easeOut,
            child: _isDirectInputMode
                ? _buildDirectInputView(context)
                : _buildOptionListView(context),
          ),
        ),
      ),
    );
  }

  Widget _buildOptionListView(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardColor = isDark ? const Color(0xFF1C1C1E) : Colors.white;
    final borderColor = isDark ? const Color(0xFF2C2C2E) : Colors.grey.shade200;
    final primaryText = isDark ? Colors.white : const Color(0xFF111111);
    final secondaryText = isDark
        ? const Color(0xFFD1D1D6)
        : const Color(0xFF777777);

    return ListView(
      key: const ValueKey('option-list'),
      shrinkWrap: true,
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      children: [
        Text(
          '의류 종류 선택',
          style: TextStyle(
            color: primaryText,
            fontSize: 22,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          '탄소발자국 계산에 사용할 의류 무게 범위를 선택해 주세요.',
          style: TextStyle(color: secondaryText, fontSize: 13, height: 1.5),
        ),
        const SizedBox(height: 18),
        ...widget.options.map((option) {
          final isSelected = option.isDirectWeightPlaceholder
              ? widget.initialSelection.isDirectWeight ||
                    widget.initialSelection.isDirectWeightPlaceholder
              : option.label == widget.initialSelection.label;

          return Semantics(
            button: true,
            selected: isSelected,
            label: option.isDirectWeightPlaceholder
                ? '직접 무게 입력'
                : '${option.label}, ${option.category}, 예상 무게 ${option.weightRangeLabel}',
            child: Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: InkWell(
                onTap: () {
                  if (option.isDirectWeightPlaceholder) {
                    setState(() {
                      _isDirectInputMode = true;
                      _directErrorText = null;
                    });
                    return;
                  }

                  widget.onSelected(option);
                },
                borderRadius: BorderRadius.circular(14),
                child: ExcludeSemantics(
                  child: Container(
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: isSelected
                          ? const Color(
                              0xFF4A4EFE,
                            ).withValues(alpha: isDark ? 0.20 : 0.10)
                          : cardColor,
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(
                        color: isSelected
                            ? const Color(0xFF4A4EFE)
                            : borderColor,
                        width: isSelected ? 1.5 : 1,
                      ),
                    ),
                    child: Row(
                      children: [
                        Container(
                          width: 42,
                          height: 42,
                          decoration: BoxDecoration(
                            color: isSelected
                                ? const Color(0xFF4A4EFE)
                                : (isDark
                                      ? const Color(0xFF2A2A2E)
                                      : const Color(0xFFF2F3F8)),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Icon(
                            option.icon,
                            color: isSelected
                                ? Colors.white
                                : const Color(0xFF4A4EFE),
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                option.label,
                                style: TextStyle(
                                  color: primaryText,
                                  fontSize: 15,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                option.isDirectWeightPlaceholder
                                    ? '실제 무게를 알고 있어요'
                                    : '${option.category} · 예상 무게 ${option.weightRangeLabel}',
                                style: TextStyle(
                                  color: secondaryText,
                                  fontSize: 12,
                                  height: 1.4,
                                ),
                              ),
                            ],
                          ),
                        ),
                        if (isSelected)
                          const Icon(
                            Icons.check_circle,
                            color: Color(0xFF4A4EFE),
                          )
                        else
                          Icon(
                            option.isDirectWeightPlaceholder
                                ? Icons.scale_outlined
                                : Icons.chevron_right,
                            color: secondaryText,
                          ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          );
        }),
      ],
    );
  }

  Widget _buildDirectInputView(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardColor = isDark ? const Color(0xFF1C1C1E) : Colors.white;
    final borderColor = isDark ? const Color(0xFF2C2C2E) : Colors.grey.shade300;
    final primaryText = isDark ? Colors.white : const Color(0xFF111111);
    final secondaryText = isDark
        ? const Color(0xFFD1D1D6)
        : const Color(0xFF777777);
    final inputFillColor = isDark ? const Color(0xFF2A2A2E) : Colors.white;

    return ListView(
      key: const ValueKey('direct-input'),
      shrinkWrap: true,
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      children: [
        Row(
          children: [
            IconButton(
              onPressed: () {
                setState(() {
                  _isDirectInputMode = false;
                  _directErrorText = null;
                });
              },
              tooltip: '의류 종류 목록으로 돌아가기',
              icon: Icon(
                Icons.arrow_back_ios_new_rounded,
                color: primaryText,
                size: 20,
              ),
            ),
            Expanded(
              child: Text(
                '직접 무게 입력',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: primaryText,
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
            const SizedBox(width: 48),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          '실제 무게를 알고 있다면 더 정확하게 탄소발자국을 계산할 수 있어요.',
          style: TextStyle(color: secondaryText, fontSize: 13, height: 1.5),
        ),
        const SizedBox(height: 18),
        TextField(
          controller: _directNameController,
          autofocus: true,
          style: TextStyle(color: primaryText),
          textInputAction: TextInputAction.next,
          decoration: InputDecoration(
            filled: true,
            fillColor: inputFillColor,
            labelText: '의류 종류',
            hintText: '예: 가디건, 조끼, 트레이닝복',
            labelStyle: TextStyle(color: secondaryText),
            hintStyle: TextStyle(color: secondaryText),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
            prefixIcon: const Icon(Icons.edit_outlined),
          ),
          onChanged: (_) {
            if (_directErrorText == null) return;
            setState(() {
              _directErrorText = null;
            });
          },
        ),
        const SizedBox(height: 14),
        TextField(
          controller: _directWeightController,
          style: TextStyle(color: primaryText),
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          textInputAction: TextInputAction.done,
          decoration: InputDecoration(
            filled: true,
            fillColor: inputFillColor,
            labelText: '실제 무게',
            hintText: '예: 620',
            suffixText: 'g',
            labelStyle: TextStyle(color: secondaryText),
            hintStyle: TextStyle(color: secondaryText),
            suffixStyle: TextStyle(color: secondaryText),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
            prefixIcon: const Icon(Icons.scale_outlined),
          ),
          onChanged: (_) {
            if (_directErrorText == null) return;
            setState(() {
              _directErrorText = null;
            });
          },
          onSubmitted: (_) => _submitDirectInput(),
        ),
        const SizedBox(height: 16),
        Text(
          '분류',
          style: TextStyle(
            color: primaryText,
            fontSize: 14,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              child: _CategoryChoiceChip(
                label: '상의',
                selected: _directCategory == '상의',
                onTap: () {
                  setState(() {
                    _directCategory = '상의';
                  });
                },
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _CategoryChoiceChip(
                label: '하의',
                selected: _directCategory == '하의',
                onTap: () {
                  setState(() {
                    _directCategory = '하의';
                  });
                },
              ),
            ),
          ],
        ),
        if (_directErrorText != null) ...[
          const SizedBox(height: 12),
          Semantics(
            liveRegion: true,
            child: Text(
              _directErrorText!,
              style: const TextStyle(
                color: Colors.redAccent,
                fontSize: 13,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
        const SizedBox(height: 20),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: cardColor,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: borderColor),
          ),
          child: Text(
            '무게는 의류 한 벌 기준으로 g 단위로 입력해 주세요.',
            style: TextStyle(color: secondaryText, fontSize: 13, height: 1.5),
          ),
        ),
        const SizedBox(height: 20),
        SizedBox(
          width: double.infinity,
          height: 50,
          child: ElevatedButton(
            onPressed: _submitDirectInput,
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF4A4EFE),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
            child: const Text(
              '적용하기',
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _CategoryChoiceChip extends StatelessWidget {
  const _CategoryChoiceChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final borderColor = selected
        ? const Color(0xFF4A4EFE)
        : const Color(0xFF8C8C8C);
    final backgroundColor = selected
        ? const Color(0xFF4A4EFE).withValues(alpha: isDark ? 0.22 : 0.10)
        : Colors.transparent;
    final textColor = selected
        ? const Color(0xFF4A4EFE)
        : (isDark ? Colors.white : Colors.black87);

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        height: 48,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: backgroundColor,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: borderColor),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: textColor,
            fontSize: 14,
            fontWeight: selected ? FontWeight.w800 : FontWeight.w600,
          ),
        ),
      ),
    );
  }
}
