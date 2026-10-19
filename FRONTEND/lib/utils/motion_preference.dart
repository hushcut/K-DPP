import 'package:flutter/widgets.dart';

/// 기기에서 '동작 줄이기'를 켰는지입니다(DECISIONS 268).
///
/// Android 의 '애니메이션 삭제'는 [MediaQuery.disableAnimationsOf] 로 오지만, iOS 의 '동작 줄이기'는
/// `accessibilityFeatures.reduceMotion` 으로만 와서 MediaQuery 에 실리지 않습니다(Flutter 3.41.5).
/// 그래서 둘 다 봅니다.
///
/// reduceMotion 이 바뀌어도 이 값을 읽은 위젯은 다시 그려지지 않습니다. 애니메이션을 시작하는
/// 순간에 읽어 씁니다.
bool reducesMotion(BuildContext context) =>
    (MediaQuery.maybeDisableAnimationsOf(context) ?? false) ||
    (View.maybeOf(
          context,
        )?.platformDispatcher.accessibilityFeatures.reduceMotion ??
        false);
