import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../models/clothing_type_option.dart';
import '../theme/app_palette.dart';
import 'app_back_button.dart';
import 'app_glass_button.dart';
import 'clothing_category_segmented_control.dart';
import 'number_keyboard_toolbar.dart';

/// 결과 입력 화면에서 의류 종류를 바꾸는 시트를 열고 고른 종류를 반환합니다.
///
/// 드래그·바깥 탭·뒤로가기로 닫을 수 있고 그때는 null을 반환합니다. 스캔 직후 반드시
/// 골라야 하는 경우는 시트가 아니라 [showClothingTypePickerScreen] 으로 엽니다(DECISIONS 226).
///
/// [optionsListenable]을 주면 시트가 열려 있는 동안 목록이 바뀌어도(서버 무게표 도착)
/// 새 목록을 보여 줍니다. 그때는 [options]보다 그 값을 씁니다.
Future<ClothingTypeOption?> showClothingTypePickerSheet({
  required BuildContext context,
  required List<ClothingTypeOption> options,
  required ClothingTypeOption initialSelection,
  ValueListenable<List<ClothingTypeOption>>? optionsListenable,
}) {
  // 배경색은 테마(AppTheme.bottomSheetTheme)에 맡깁니다. 여기서 정하면 여는 순간의 테마로 굳어
  // 시트가 열린 채 시스템 밝기가 바뀔 때 따라오지 않습니다.
  return showModalBottomSheet<ClothingTypeOption>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
    ),
    clipBehavior: Clip.antiAlias,
    builder: (sheetContext) {
      return ClothingTypePickerSheet(
        options: options,
        optionsListenable: optionsListenable,
        initialSelection: initialSelection,
        onSelected: (option) {
          Navigator.pop(sheetContext, option);
        },
      );
    },
  );
}

/// 스캔 직후 의류 종류를 반드시 고르는 화면을 열고 고른 종류를 반환합니다(DECISIONS 226).
///
/// 고르지 않고 나가는 길은 앱바 "<"(다시 촬영)뿐이고 그때는 null을 반환합니다.
/// [confirmRetake]가 true면(분석 성공 뒤) 분석 결과가 사라진다고 먼저 묻고, 확인창을 끼울 수
/// 없는 iOS 왼쪽 끝 밀기는 막습니다. false면(분석 실패 뒤) 잃는 것이 실패한 사진뿐이라 묻지 않고
/// 밀어서도 나갈 수 있습니다.
///
/// [failureMessage]를 주면 화면 맨 위(제목 위)에 빨간 느낌표와 함께 보이고, 화면이 열릴 때
/// 읽기 프로그램이 이 줄을 화면 이름으로 먼저 읽습니다(DECISIONS 96).
Future<ClothingTypeOption?> showClothingTypePickerScreen({
  required BuildContext context,
  required List<ClothingTypeOption> options,
  required ClothingTypeOption initialSelection,
  required bool confirmRetake,
  ValueListenable<List<ClothingTypeOption>>? optionsListenable,
  String? failureMessage,
}) {
  return Navigator.push<ClothingTypeOption>(
    context,
    MaterialPageRoute<ClothingTypeOption>(
      builder: (routeContext) {
        return ClothingTypePickerSheet.screen(
          options: options,
          optionsListenable: optionsListenable,
          initialSelection: initialSelection,
          confirmRetake: confirmRetake,
          failureMessage: failureMessage,
          onSelected: (option) {
            Navigator.pop(routeContext, option);
          },
        );
      },
    ),
  );
}

/// 의류 종류별 예상 무게를 선택하거나 실제 무게를 직접 입력하는 몸통입니다.
///
/// 기본 생성자는 바텀 시트 안에 들어가고, [ClothingTypePickerSheet.screen]은 앱바 "<"를 단
/// 한 화면이 됩니다. 두 곳이 목록·직접 입력을 함께 씁니다(DECISIONS 226 ⑥).
/// 선택 결과는 [onSelected]로 전달합니다.
class ClothingTypePickerSheet extends StatefulWidget {
  const ClothingTypePickerSheet({
    super.key,
    required this.options,
    required this.initialSelection,
    required this.onSelected,
    this.optionsListenable,
  }) : isScreen = false,
       confirmRetake = false,
       failureMessage = null;

  /// 스캔 직후 반드시 고르는 화면입니다. "<"·시스템 뒤로가기는 직접 입력 중이면 목록으로
  /// 돌아가고, 목록에서는 [confirmRetake]에 따라 묻거나 바로 결과 없이 닫습니다.
  const ClothingTypePickerSheet.screen({
    super.key,
    required this.options,
    required this.initialSelection,
    required this.onSelected,
    required this.confirmRetake,
    this.optionsListenable,
    this.failureMessage,
  }) : isScreen = true;

  // 표시할 선택지와 현재 선택된 초기값입니다.
  final List<ClothingTypeOption> options;
  /// 열려 있는 동안 바뀔 수 있는 선택지입니다. 있으면 [options] 대신 씁니다.
  final ValueListenable<List<ClothingTypeOption>>? optionsListenable;
  final ClothingTypeOption initialSelection;
  /// 일반 선택 또는 검증된 직접 입력 결과를 상위 화면에 전달합니다.
  final ValueChanged<ClothingTypeOption> onSelected;
  /// 시트 안 몸통이 아니라 앱바를 단 한 화면으로 그리는지입니다.
  final bool isScreen;
  /// 화면에서 "<"(다시 촬영)로 나가기 전에 분석 결과가 사라진다고 물을지입니다.
  final bool confirmRetake;
  /// 분석에 실패했을 때 목록 맨 위에 보일 이유입니다. 없으면 그 줄을 그리지 않습니다.
  final String? failureMessage;

  @override
  State<ClothingTypePickerSheet> createState() =>
      _ClothingTypePickerSheetState();
}

/// 선택 목록과 직접 입력 폼 사이의 전환 및 입력 검증 상태를 관리합니다.
class _ClothingTypePickerSheetState extends State<ClothingTypePickerSheet> {
  final TextEditingController _directNameController = TextEditingController();
  final TextEditingController _directWeightController = TextEditingController();
  final FocusNode _directNameFocusNode = FocusNode();
  final FocusNode _directWeightFocusNode = FocusNode();

  bool _isDirectInputMode = false;
  String _directCategory = '상의';
  String? _directErrorText;

  List<ClothingTypeOption> get _options =>
      widget.optionsListenable?.value ?? widget.options;

  // 시트는 손잡이가 위를 띄워 주고, 화면은 앱바 바로 아래라 조금 띄웁니다.
  EdgeInsets get _contentPadding =>
      EdgeInsets.fromLTRB(20, widget.isScreen ? 8 : 0, 20, 24);

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
    _directNameFocusNode.dispose();
    _directWeightFocusNode.dispose();
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

  // 확인을 받은 경우에만 결과 없이 화면을 닫아, 호출 화면이 촬영 화면으로 돌아가게 합니다.
  Future<void> _confirmRetake() async {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);

    final shouldDiscard = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          backgroundColor: palette.card,
          title: Text(
            '다시 촬영할까요?',
            style: TextStyle(color: palette.textPrimary),
          ),
          content: Text(
            '다시 촬영하면 현재 분석 결과가 사라져요.',
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
    return widget.isScreen ? _buildScreen(context) : _buildSheet(context);
  }

  Widget _buildSheet(BuildContext context) {
    final maxSheetHeight = MediaQuery.sizeOf(context).height * 0.78;

    return SafeArea(
      top: false,
      child: AnimatedPadding(
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
        padding: EdgeInsets.only(
          bottom: MediaQuery.viewInsetsOf(context).bottom,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // 키보드 여백과 아래 막대를 뺀 남은 높이 안에서만 커지게 Flexible로 감쌉니다.
            // Flexible 없이 Column에 두면 높이 제한 없이 화면 높이의 78%까지 커져
            // 키보드 여백과 합쳐 넘칩니다(2026-09-18 폰 확인).
            Flexible(
              child: ConstrainedBox(
                constraints: BoxConstraints(maxHeight: maxSheetHeight),
                child: _buildContent(context),
              ),
            ),
            _buildWeightKeyboardToolbar(context),
          ],
        ),
      ),
    );
  }

  // 키보드가 올라오면 Scaffold 가 본문을 줄이므로, 시트와 달리 키보드 여백을 따로 두지 않습니다.
  Widget _buildScreen(BuildContext context) {
    final palette = AppPalette.of(context);

    return PopScope<Object?>(
      // 직접 입력 중에는 목록으로, 분석 성공 뒤에는 확인창으로 가야 해서 막습니다. 막으면 iOS 왼쪽
      // 끝 밀기도 꺼집니다(Flutter PageRoute.popGestureEnabled) — 밀기에는 확인창을 끼울 수 없습니다.
      canPop: !_isDirectInputMode && !widget.confirmRetake,
      onPopInvokedWithResult: (didPop, _) {
        // 종류를 골라 닫힐 때도 불리므로, 막힌 뒤로가기만 처리합니다.
        if (didPop) return;

        if (_isDirectInputMode) {
          _leaveDirectInputMode();
          return;
        }

        _confirmRetake();
      },
      child: Scaffold(
        backgroundColor: palette.background,
        appBar: AppBar(
          backgroundColor: palette.background,
          elevation: 0,
          scrolledUnderElevation: 0,
          automaticallyImplyLeading: false,
          leadingWidth: AppGlassStyle.leadingWidth,
          // 누르면 부푸는 유리 버튼이 앱바 아래 경계에서 잘리지 않게 합니다(앱바 기본은 잘라 냄).
          clipBehavior: Clip.none,
          leading: Padding(
            padding: const EdgeInsets.only(left: 8),
            child: AppBackButton(
              // pop 이 아니라 maybePop 이라야 위 PopScope 를 거칩니다.
              onPressed: () => Navigator.maybePop(context),
              // 직접 입력 중에는 촬영 화면이 아니라 목록으로 돌아갑니다.
              tooltip: _isDirectInputMode ? '의류 종류 목록으로 돌아가기' : '다시 촬영',
            ),
          ),
        ),
        body: SafeArea(
          top: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(child: _buildContent(context)),
              _buildWeightKeyboardToolbar(context),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildContent(BuildContext context) {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 180),
      switchInCurve: Curves.easeOut,
      switchOutCurve: Curves.easeOut,
      child: _isDirectInputMode
          ? _buildDirectInputView(context)
          : _buildOptionListView(context),
    );
  }

  // 무게 칸에 포커스가 있는 동안 시트 맨 아래(키보드 바로 위)에 ∧·∨·[완료] 막대를 붙입니다
  // (DECISIONS 177). ∧ 는 앞 칸인 의류 종류로 가고, 무게 뒤로 이어지는 입력란이 없어 ∨ 는 흐립니다.
  Widget _buildWeightKeyboardToolbar(BuildContext context) {
    if (!_isDirectInputMode || !NumberKeyboardToolbar.isNeeded(context)) {
      return const SizedBox.shrink();
    }

    return ListenableBuilder(
      listenable: _directWeightFocusNode,
      builder: (context, _) => _directWeightFocusNode.hasFocus
          ? NumberKeyboardToolbar(
              onPrevious: _directNameFocusNode.requestFocus,
              onDone: () => _directWeightFocusNode.unfocus(),
            )
          : const SizedBox.shrink(),
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
    final failureMessage = widget.failureMessage;

    return ListView(
      key: const ValueKey('option-list'),
      shrinkWrap: !widget.isScreen,
      padding: _contentPadding,
      children: [
        // 제목은 분석 성공과 같아 이 줄이 없으면 실패한 줄 모른다. 제목보다 위에 두고 모양은
        // 실패 배너와 맞춘다. 화면 이름(namesRoute)으로 삼아, 화면이 열릴 때 읽기 프로그램이 첫 칸
        // ("<")으로 가기 전에 이 줄부터 말하게 한다 — 보이는 순서는 그대로 둔다(DECISIONS 103).
        if (failureMessage != null) ...[
          Semantics(
            container: true,
            namesRoute: true,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(
                  Icons.error_outline,
                  color: Colors.redAccent,
                  size: 22,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.only(top: 1),
                    child: Text(
                      failureMessage,
                      style: TextStyle(
                        color: primaryText,
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        height: 1.4,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],
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
              // 칸 색을 Container 로 칠하면 누름 효과가 그 아래에 가려지므로 Ink 로 칠합니다.
              child: Material(
                color: Colors.transparent,
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
                    child: Ink(
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

    final title = Text(
      '직접 무게 입력',
      textAlign: widget.isScreen ? TextAlign.start : TextAlign.center,
      style: TextStyle(
        color: primaryText,
        fontSize: 22,
        fontWeight: FontWeight.w800,
      ),
    );

    return ListView(
      key: const ValueKey('direct-input'),
      shrinkWrap: !widget.isScreen,
      padding: _contentPadding,
      children: [
        // 화면에서는 앱바 "<" 가 목록으로 돌아가므로 몸통 안에 뒤로 버튼을 또 두지 않습니다.
        if (widget.isScreen)
          title
        else
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
              Expanded(child: title),
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
          focusNode: _directNameFocusNode,
          autofocus: true,
          style: TextStyle(color: primaryText),
          textInputAction: TextInputAction.next,
          onTapOutside: dismissKeyboardOnTapOutside,
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
          focusNode: _directWeightFocusNode,
          style: TextStyle(color: primaryText),
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          textInputAction: TextInputAction.done,
          onTapOutside: dismissKeyboardOnTapOutside,
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
        ClothingCategorySegmentedControl(
          options: const ['상의', '하의'],
          selected: _directCategory,
          onChanged: (value) {
            setState(() {
              _directCategory = value;
            });
          },
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
