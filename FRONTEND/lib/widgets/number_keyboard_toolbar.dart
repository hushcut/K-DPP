import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import '../theme/app_palette.dart';

/// 입력란 바깥을 탭하면 키보드를 내립니다. `TextField.onTapOutside`에 넘겨 씁니다.
void dismissKeyboardOnTapOutside(PointerDownEvent event) {
  FocusManager.instance.primaryFocus?.unfocus();
}

/// 숫자 키패드 바로 위에 띄우는 양 끝이 둥근 막대입니다. 왼쪽에 ∧(이전 칸)·∨(다음 칸), 오른쪽에 [완료].
///
/// iOS 숫자 키패드에는 확인 키가 없어, 막대가 없으면 키보드를 끌어내려야만 닫을 수
/// 있었습니다. 모양은 iOS 키보드 액세서리를 따르고, 두 플랫폼에서 같은 막대를 씁니다
/// (DECISIONS 177 — 30 의 떠 있는 둥근 버튼을 바꿈).
///
/// 갈 곳이 없는 화살표는 흐리게 남겨, 막대 안 버튼 자리가 칸마다 바뀌지 않게 합니다.
/// 좌우·위아래에 여백을 둔 캡슐이라 위 모서리가 둥근 키보드 위에 따로 떠 보입니다(DECISIONS 178).
/// 겹쳐 띄우지 않고 막대 높이만큼 자리를 차지해, 키보드 바로 위에 놓인 입력 칸을 가리지 않습니다.
///
/// 막대는 [TextFieldTapRegion]으로 감싸 입력란의 일부로 취급합니다. 바깥 탭으로 키보드를
/// 내리는 입력란에서 화살표를 누를 때, 누르는 순간 키보드가 내려갔다가 다음 칸에서 다시
/// 올라오지 않게 하기 위해서입니다.
class NumberKeyboardToolbar extends StatelessWidget {
  const NumberKeyboardToolbar({
    super.key,
    required this.onDone,
    this.onPrevious,
    this.onNext,
  });

  /// 키보드를 닫습니다.
  final VoidCallback onDone;

  /// 앞 입력란으로 옮깁니다. 없으면 ∧ 를 흐리게 그립니다.
  final VoidCallback? onPrevious;

  /// 다음 입력란으로 옮깁니다. 없으면 ∨ 를 흐리게 그립니다.
  final VoidCallback? onNext;

  /// 막대 높이이자 버튼을 누를 수 있는 최소 크기(44pt)입니다.
  static const double buttonHeight = 44;

  /// 캡슐 바깥 여백입니다. 화면 가장자리와 키보드에 붙지 않게 띄웁니다.
  static const EdgeInsets margin = EdgeInsets.fromLTRB(8, 4, 8, 4);

  // 키보드와 같은 계열의 회색 띠입니다. 화살표·[완료] 색은 막대 위에서 글자 대비 4.5:1 을 넘깁니다
  // (라이트 4.6·다크 4.9). 사진처럼 다크 #666666 에 파랑을 두면 2:1 이 안 돼 띠를 더 어둡게 했습니다.
  static const Color _lightBar = Color(0xFFE9EAEE);
  static const Color _darkBar = Color(0xFF3A3A3C);
  static const Color _lightSeparator = Color(0xFFC6C6C8);
  static const Color _darkSeparator = Color(0xFF48484A);
  static const Color _darkAccent = Color(0xFF9EA1FF);
  static const Color _lightDisabled = Color(0xFFA1A1A8);
  static const Color _darkDisabled = Color(0xFF6E6E73);

  /// 숫자 키패드 위에 막대를 붙이는 플랫폼인지 알려 줍니다. iOS·Android 둘 다입니다(DECISIONS 177).
  static bool isNeeded(BuildContext context) {
    final platform = Theme.of(context).platform;
    return platform == TargetPlatform.iOS || platform == TargetPlatform.android;
  }

  @override
  Widget build(BuildContext context) {
    final isDark = AppPalette.of(context).isDark;
    final accent = isDark ? _darkAccent : AppPalette.accent;
    final disabled = isDark ? _darkDisabled : _lightDisabled;

    Widget arrow({
      required IconData icon,
      required String label,
      required VoidCallback? onPressed,
    }) {
      return IconButton(
        onPressed: onPressed,
        constraints: const BoxConstraints.tightFor(
          width: buttonHeight,
          height: buttonHeight,
        ),
        padding: EdgeInsets.zero,
        color: accent,
        disabledColor: disabled,
        // 툴팁은 낭독 트리에 이름(label)이 아니라 tooltip 으로만 들어가 아이콘 이름으로 둡니다.
        icon: Icon(icon, size: 24, semanticLabel: label),
      );
    }

    return TextFieldTapRegion(
      child: Padding(
        padding: margin,
        // 눌림 물결이 둥근 끝 밖으로 번지지 않게 캡슐 모양으로 자릅니다.
        child: Material(
          color: isDark ? _darkBar : _lightBar,
          shape: StadiumBorder(
            side: BorderSide(
              color: isDark ? _darkSeparator : _lightSeparator,
              width: 0.5,
            ),
          ),
          clipBehavior: Clip.antiAlias,
          child: SizedBox(
            height: buttonHeight,
            child: Row(
              children: [
                const SizedBox(width: 8),
                arrow(
                  icon: CupertinoIcons.chevron_up,
                  label: '이전 칸',
                  onPressed: onPrevious,
                ),
                const SizedBox(width: 4),
                arrow(
                  icon: CupertinoIcons.chevron_down,
                  label: '다음 칸',
                  onPressed: onNext,
                ),
                const Spacer(),
                TextButton(
                  onPressed: onDone,
                  style: TextButton.styleFrom(
                    foregroundColor: accent,
                    minimumSize: const Size(64, buttonHeight),
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    shape: const StadiumBorder(),
                    textStyle: const TextStyle(
                      fontSize: 17,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  child: const Text('완료'),
                ),
                const SizedBox(width: 4),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
