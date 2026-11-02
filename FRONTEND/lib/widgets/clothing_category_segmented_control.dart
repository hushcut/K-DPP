import 'package:flutter/material.dart';

import '../theme/app_palette.dart';

/// 상의·하의 같은 의류 분류 하나를 고르는 세그먼트 컨트롤입니다.
///
/// 스캔 '직접 입력'과 리포트 '의류 정보 수정'이 함께 써서 같은 선택을 화면마다
/// 같은 모양으로 보여 줍니다. 선택된 칸은 강조색 바탕에 흰 글자와 체크 표시를 붙여
/// 색만으로 구분하지 않게 하고, 낭독기에는 [SegmentedButton] 이 '선택됨'을 알립니다.
class ClothingCategorySegmentedControl extends StatelessWidget {
  const ClothingCategorySegmentedControl({
    super.key,
    required this.options,
    required this.selected,
    required this.onChanged,
  });

  /// 보여 줄 분류 이름입니다. 칸은 이 순서대로 같은 폭으로 나뉩니다.
  final List<String> options;

  /// 지금 선택된 분류입니다. [options] 중 하나여야 합니다.
  final String selected;

  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    // 다크 모드에서 옅은 강조색 바탕 위 강조색 글자는 대비가 부족해
    // 선택 칸은 두 테마 모두 강조색 바탕 + 흰 글자로 칠합니다.
    final contentColor = WidgetStateProperty<Color?>.fromMap({
      WidgetState.selected: Colors.white,
      WidgetState.any: palette.textPrimary,
    });

    return SegmentedButton<String>(
      segments: [
        for (final option in options)
          ButtonSegment<String>(value: option, label: Text(option)),
      ],
      selected: {selected},
      onSelectionChanged: (selection) => onChanged(selection.single),
      expandedInsets: EdgeInsets.zero,
      style: SegmentedButton.styleFrom(
        selectedBackgroundColor: AppPalette.accent,
        // 테두리는 같은 시트의 입력칸과 맞춥니다. 두 시트 입력칸은 filled 라 M3 가
        // outline 이 아니라 onSurfaceVariant 로 테두리를 그립니다.
        side: BorderSide(color: Theme.of(context).colorScheme.onSurfaceVariant),
        textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ).copyWith(foregroundColor: contentColor, iconColor: contentColor),
    );
  }
}
