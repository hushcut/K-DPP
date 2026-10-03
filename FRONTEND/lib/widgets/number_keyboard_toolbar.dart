import 'package:flutter/material.dart';

import '../theme/app_palette.dart';

/// 입력란 바깥을 탭하면 키보드를 내립니다. `TextField.onTapOutside`에 넘겨 씁니다.
void dismissKeyboardOnTapOutside(PointerDownEvent event) {
  FocusManager.instance.primaryFocus?.unfocus();
}

/// 숫자 키패드 바로 위에 띄우는 [다음]·[완료] 버튼입니다.
///
/// iOS 숫자 키패드에는 확인 키가 없어, 버튼이 없으면 키보드를 끌어내려야만 닫을 수
/// 있습니다. Android 숫자 키보드에는 동작 키가 있으므로 [isNeeded]는 iOS에서만 참입니다.
///
/// 배경 띠 없이 둥근 버튼만 오른쪽에 띄웁니다. 겹쳐 띄우지 않고 버튼 높이만큼 자리를
/// 차지해, 키보드 바로 위에 놓인 입력 칸을 가리지 않습니다.
///
/// 버튼은 [TextFieldTapRegion]으로 감싸 입력란의 일부로 취급합니다. 바깥 탭으로 키보드를
/// 내리는 입력란에서 [다음]을 누를 때, 누르는 순간 키보드가 내려갔다가 다음 칸에서 다시
/// 올라오지 않게 하기 위해서입니다.
class NumberKeyboardToolbar extends StatelessWidget {
  const NumberKeyboardToolbar({super.key, required this.onDone, this.onNext});

  /// 키보드를 닫습니다.
  final VoidCallback onDone;

  /// 다음 입력란으로 옮깁니다. 없으면 [다음] 버튼을 그리지 않습니다.
  final VoidCallback? onNext;

  /// 버튼의 최소 높이입니다. 손가락으로 누를 수 있는 크기(44pt)를 지킵니다.
  static const double buttonHeight = 44;

  /// 이 플랫폼의 숫자 키패드에 확인 키가 없어 버튼이 필요한지 알려 줍니다.
  static bool isNeeded(BuildContext context) =>
      Theme.of(context).platform == TargetPlatform.iOS;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    const minimumSize = Size(88, buttonHeight);
    const shape = StadiumBorder();
    final shadowColor = Colors.black.withValues(alpha: palette.isDark ? 0.6 : 0.25);

    return TextFieldTapRegion(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 6, 16, 8),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            if (onNext != null) ...[
              // [다음]은 바탕색 버튼이라 [완료]와 구분되고, 강조색 테두리로 떠 보입니다.
              OutlinedButton(
                onPressed: onNext,
                style: OutlinedButton.styleFrom(
                  backgroundColor: palette.card,
                  foregroundColor: AppPalette.accent,
                  side: const BorderSide(color: AppPalette.accent, width: 1.5),
                  minimumSize: minimumSize,
                  shape: shape,
                  elevation: 2,
                  shadowColor: shadowColor,
                ),
                child: const Text(
                  '다음',
                  style: TextStyle(fontWeight: FontWeight.w600),
                ),
              ),
              const SizedBox(width: 10),
            ],
            FilledButton(
              onPressed: onDone,
              style: FilledButton.styleFrom(
                backgroundColor: AppPalette.accent,
                foregroundColor: Colors.white,
                minimumSize: minimumSize,
                shape: shape,
                elevation: 3,
                shadowColor: shadowColor,
              ),
              child: const Text(
                '완료',
                style: TextStyle(fontWeight: FontWeight.w700),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
