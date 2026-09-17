import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../models/clothing_type_option.dart';
import '../theme/app_palette.dart';

/// 선택을 건너뛸 수 없는 유형 선택 시트에서 '다시 촬영'으로 나갈 때 보여 줄 확인 문구입니다.
///
/// 분석에 성공한 뒤와 실패해 직접 입력하는 경우는 사라지는 내용이 달라 문구를 나눕니다.
class ClothingTypePickerDiscardPrompt {
  const ClothingTypePickerDiscardPrompt({
    required this.title,
    required this.message,
  });

  final String title;
  final String message;

  /// 분석 결과를 확인하는 시트: 나가면 분석한 라벨 결과가 사라집니다.
  static const analysisResult = ClothingTypePickerDiscardPrompt(
    title: '다시 촬영할까요?',
    message: '다시 촬영하면 현재 분석 결과가 사라져요.',
  );

  /// 분석 실패 후 직접 입력하는 시트: 버릴 분석 결과는 없고 지금 사진만 사라집니다.
  static const manualAfterFailure = ClothingTypePickerDiscardPrompt(
    title: '다시 촬영할까요?',
    message: '현재 사진을 지우고 촬영 화면으로 돌아가요.',
  );
}

/// 의류 유형 선택 시트를 열고 고른 유형을 반환합니다.
///
/// [discardPrompt]가 없으면 드래그·바깥 탭·뒤로가기로 닫을 수 있고 그때는 null을 반환합니다.
/// 있으면 선택을 건너뛸 수 없는 시트가 되어 닫는 경로를 모두 막고, 시트 안 '다시 촬영'
/// 버튼이나 시스템 뒤로가기에서 확인을 받은 경우에만 null로 닫힙니다.
///
/// [optionsListenable]을 주면 시트가 열려 있는 동안 목록이 바뀌어도(서버 무게표 도착)
/// 새 목록을 보여 줍니다. 그때는 [options]보다 그 값을 씁니다.
Future<ClothingTypeOption?> showClothingTypePickerSheet({
  required BuildContext context,
  required List<ClothingTypeOption> options,
  required ClothingTypeOption initialSelection,
  ValueListenable<List<ClothingTypeOption>>? optionsListenable,
  ClothingTypePickerDiscardPrompt? discardPrompt,
}) {
  final canDismiss = discardPrompt == null;
  final isDark = Theme.of(context).brightness == Brightness.dark;
  final sheetColor = isDark ? const Color(0xFF121212) : Colors.white;

  return showModalBottomSheet<ClothingTypeOption>(
    context: context,
    isScrollControlled: true,
    isDismissible: canDismiss,
    // Flutter 손잡이는 enableDrag가 false여도 자체 드래그 감지기와 접근성 '닫기'
    // 동작을 가지며, 둘 다 PopScope를 거치지 않고 시트를 닫습니다. 그래서 필수
    // 선택에서는 손잡이를 빼고 시트 안에 모양만 그립니다. enableDrag도 꺼야
    // 하단 안전 영역을 끌어내려 닫는 경로가 막힙니다.
    enableDrag: canDismiss,
    showDragHandle: canDismiss,
    backgroundColor: sheetColor,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
    ),
    clipBehavior: Clip.antiAlias,
    builder: (sheetContext) {
      return ClothingTypePickerSheet(
        options: options,
        optionsListenable: optionsListenable,
        initialSelection: initialSelection,
        discardPrompt: discardPrompt,
        onSelected: (option) {
          Navigator.pop(sheetContext, option);
        },
      );
    },
  );
}

/// 의류 종류별 예상 무게를 선택하거나 실제 무게를 직접 입력하는 바텀 시트입니다.
///
/// 선택 결과는 [onSelected]로 전달합니다. [discardPrompt]가 있으면 시트 안에
/// '다시 촬영' 버튼을 두고 시스템 뒤로가기를 확인 대화상자로 보냅니다.
class ClothingTypePickerSheet extends StatefulWidget {
  const ClothingTypePickerSheet({
    super.key,
    required this.options,
    required this.initialSelection,
    required this.onSelected,
    this.optionsListenable,
    this.discardPrompt,
  });

  // 표시할 선택지와 현재 선택된 초기값입니다.
  final List<ClothingTypeOption> options;
  /// 열려 있는 동안 바뀔 수 있는 선택지입니다. 있으면 [options] 대신 씁니다.
  final ValueListenable<List<ClothingTypeOption>>? optionsListenable;
  final ClothingTypeOption initialSelection;
  /// 일반 선택 또는 검증된 직접 입력 결과를 상위 화면에 전달합니다.
  final ValueChanged<ClothingTypeOption> onSelected;
  /// 선택을 건너뛸 수 없는 시트일 때 '다시 촬영' 확인에 쓸 문구입니다.
  final ClothingTypePickerDiscardPrompt? discardPrompt;

  @override
  State<ClothingTypePickerSheet> createState() =>
      _ClothingTypePickerSheetState();
}

/// 선택 목록과 직접 입력 폼 사이의 전환 및 입력 검증 상태를 관리합니다.
class _ClothingTypePickerSheetState extends State<ClothingTypePickerSheet> {
  final TextEditingController _directNameController = TextEditingController();
  final TextEditingController _directWeightController = TextEditingController();

  bool _isDirectInputMode = false;
  String _directCategory = '상의';
  String? _directErrorText;

  List<ClothingTypeOption> get _options =>
      widget.optionsListenable?.value ?? widget.options;

  // 목록이 바뀌면 다시 그립니다. 선택 표시는 이름으로 맞추므로 고른 종류가 유지됩니다.
  void _handleOptionsChanged() {
    if (!mounted) return;
    setState(() {});
  }

  @override
  void initState() {
    super.initState();
    widget.optionsListenable?.addListener(_handleOptionsChanged);

    _directCategory = widget.initialSelection.category == '하의' ? '하의' : '상의';

    if (widget.initialSelection.isDirectWeight) {
      _directNameController.text = widget.initialSelection.label;
      _directWeightController.text = ClothingTypeOption.formatWeightGram(
        widget.initialSelection.estimatedWeightGram,
      );
    }
  }

  @override
  void didUpdateWidget(covariant ClothingTypePickerSheet oldWidget) {
    super.didUpdateWidget(oldWidget);

    if (oldWidget.optionsListenable != widget.optionsListenable) {
      oldWidget.optionsListenable?.removeListener(_handleOptionsChanged);
      widget.optionsListenable?.addListener(_handleOptionsChanged);
    }
  }

  @override
  void dispose() {
    widget.optionsListenable?.removeListener(_handleOptionsChanged);
    _directNameController.dispose();
    _directWeightController.dispose();
    super.dispose();
  }

  // 의류명이 있고 무게가 양수인지 검증한 후 직접 무게 옵션을 onSelected로 전달합니다.
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

    // NaN·Infinity는 저장 시 오류를 일으키므로 유한한 양수만 허용합니다.
    if (weight == null || !weight.isFinite || weight <= 0) {
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

  // 직접 입력 화면에서 의류 종류 목록으로 돌아갑니다.
  void _leaveDirectInputMode() {
    setState(() {
      _isDirectInputMode = false;
      _directErrorText = null;
    });
  }

  // 확인을 받은 경우에만 결과 없이 시트를 닫아, 호출 화면이 촬영 화면으로 돌아가게 합니다.
  Future<void> _confirmDiscard() async {
    final prompt = widget.discardPrompt;
    if (prompt == null) return;

    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);

    final shouldDiscard = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          backgroundColor: palette.card,
          title: Text(
            prompt.title,
            style: TextStyle(color: palette.textPrimary),
          ),
          content: Text(
            prompt.message,
            style: TextStyle(
              height: 1.5,
              color: isDark ? const Color(0xFFD1D1D6) : const Color(0xFF444444),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('선택 계속하기'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.redAccent,
              ),
              child: const Text(
                '다시 촬영',
                style: TextStyle(color: Colors.white),
              ),
            ),
          ],
        );
      },
    );

    if (shouldDiscard != true || !mounted) return;

    Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final maxSheetHeight = MediaQuery.sizeOf(context).height * 0.78;
    final isSelectionRequired = widget.discardPrompt != null;

    final sheet = SafeArea(
      top: false,
      child: AnimatedPadding(
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
        padding: EdgeInsets.only(
          bottom: MediaQuery.viewInsetsOf(context).bottom,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (isSelectionRequired) const _DecorativeDragHandle(),
            ConstrainedBox(
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
          ],
        ),
      ),
    );

    if (!isSelectionRequired) return sheet;

    return PopScope<Object?>(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        // 유형을 고르거나 확인 후 닫힐 때도 불리므로, 막힌 뒤로가기만 처리합니다.
        if (didPop) return;

        if (_isDirectInputMode) {
          _leaveDirectInputMode();
          return;
        }

        _confirmDiscard();
      },
      child: sheet,
    );
  }

  // 미리 정의된 의류 옵션과 직접 입력 진입 항목을 목록으로 표시합니다.
  Widget _buildOptionListView(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);
    final cardColor = palette.card;
    final borderColor = isDark ? const Color(0xFF2C2C2E) : Colors.grey.shade200;
    final primaryText = palette.textPrimary;
    final secondaryText = isDark
        ? const Color(0xFFD1D1D6)
        : const Color(0xFF777777);

    return ListView(
      key: const ValueKey('option-list'),
      shrinkWrap: true,
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                '의류 종류 선택',
                style: TextStyle(
                  color: primaryText,
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
            if (widget.discardPrompt != null)
              TextButton(
                onPressed: _confirmDiscard,
                style: TextButton.styleFrom(foregroundColor: secondaryText),
                child: const Text(
                  '다시 촬영',
                  style: TextStyle(fontWeight: FontWeight.w700),
                ),
              ),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          '탄소발자국 계산에 사용할 의류 무게 범위를 선택해 주세요.',
          style: TextStyle(color: secondaryText, fontSize: 13, height: 1.5),
        ),
        const SizedBox(height: 18),
        ..._options.map((option) {
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
                          ? AppPalette.accent.withValues(
                              alpha: isDark ? 0.20 : 0.10,
                            )
                          : cardColor,
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(
                        color: isSelected
                            ? AppPalette.accent
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
                                ? AppPalette.accent
                                : (isDark
                                      ? const Color(0xFF2A2A2E)
                                      : const Color(0xFFF2F3F8)),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Icon(
                            option.icon,
                            color: isSelected
                                ? Colors.white
                                : AppPalette.accent,
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
                            color: AppPalette.accent,
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

  // 의류명, g 단위 실제 무게, 상·하의 분류를 입력받는 화면을 만듭니다.
  Widget _buildDirectInputView(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);
    final cardColor = palette.card;
    final borderColor = isDark ? const Color(0xFF2C2C2E) : Colors.grey.shade300;
    final primaryText = palette.textPrimary;
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
              onPressed: _leaveDirectInputMode,
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
              backgroundColor: AppPalette.accent,
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

/// 필수 선택 시트에서 Flutter 손잡이 대신 그리는, 모양만 있는 손잡이입니다.
///
/// 드래그와 접근성 '닫기' 동작이 없어야 하므로 제스처 없이 그리고 의미 정보에서도 뺍니다.
/// 크기와 색은 Flutter 기본 손잡이(48px 영역, 32x4 막대)에 맞춥니다.
class _DecorativeDragHandle extends StatelessWidget {
  const _DecorativeDragHandle();

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: SizedBox(
        height: kMinInteractiveDimension,
        child: Center(
          child: Container(
            width: 32,
            height: 4,
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
        ),
      ),
    );
  }
}

/// 직접 입력 의류의 분류 하나를 선택하는 내부 선택형 칩입니다.
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
        ? AppPalette.accent
        : const Color(0xFF8C8C8C);
    final backgroundColor = selected
        ? AppPalette.accent.withValues(alpha: isDark ? 0.22 : 0.10)
        : Colors.transparent;
    final textColor = selected
        ? AppPalette.accent
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
