import 'package:flutter/material.dart';

import '../theme/app_palette.dart';

/// 입력란 바깥을 탭하면 키보드를 내립니다. `TextField.onTapOutside`에 넘겨 씁니다.
void dismissKeyboardOnTapOutside(PointerDownEvent event) {
  FocusManager.instance.primaryFocus?.unfocus();
}

/// 숫자 키패드 바로 위에 붙이는 [다음]·[완료] 막대입니다.
///
/// iOS 숫자 키패드에는 확인 키가 없어, 막대가 없으면 키보드를 끌어내려야만 닫을 수
/// 있습니다. Android 숫자 키보드에는 동작 키가 있으므로 [isNeeded]는 iOS에서만 참입니다.
///
/// 막대는 [TextFieldTapRegion]으로 감싸 입력란의 일부로 취급합니다. 바깥 탭으로 키보드를
/// 내리는 입력란에서 [다음]을 누를 때, 누르는 순간 키보드가 내려갔다가 다음 칸에서 다시
/// 올라오지 않게 하기 위해서입니다.
class NumberKeyboardToolbar extends StatelessWidget {
  const NumberKeyboardToolbar({super.key, required this.onDone, this.onNext});

  /// 키보드를 닫습니다.
  final VoidCallback onDone;

  /// 다음 입력란으로 옮깁니다. 없으면 [다음] 버튼을 그리지 않습니다.
  final VoidCallback? onNext;

  /// 이 플랫폼의 숫자 키패드에 확인 키가 없어 막대가 필요한지 알려 줍니다.
  static bool isNeeded(BuildContext context) =>
      Theme.of(context).platform == TargetPlatform.iOS;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final borderColor = isDark ? const Color(0xFF2C2C2E) : Colors.grey.shade300;
    final buttonStyle = TextButton.styleFrom(
      foregroundColor: AppPalette.accent,
    );

    return TextFieldTapRegion(
      child: Material(
        color: AppPalette.of(context).card,
        child: Container(
          constraints: const BoxConstraints(minHeight: 44),
          padding: const EdgeInsets.symmetric(horizontal: 8),
          decoration: BoxDecoration(
            border: Border(top: BorderSide(color: borderColor)),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              if (onNext != null)
                TextButton(
                  onPressed: onNext,
                  style: buttonStyle,
                  child: const Text('다음'),
                ),
              TextButton(
                onPressed: onDone,
                style: buttonStyle,
                child: const Text(
                  '완료',
                  style: TextStyle(fontWeight: FontWeight.w700),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
