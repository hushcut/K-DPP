import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';

/// 기기에서 '동작 줄이기'를 켰는지입니다(DECISIONS 268).
///
/// Android 의 '애니메이션 삭제'는 [MediaQuery.disableAnimationsOf] 로 오지만, iOS 의 '동작 줄이기'는
/// `accessibilityFeatures.reduceMotion` 으로만 와서 MediaQuery 에 실리지 않습니다(Flutter 3.41.5).
/// 그래서 둘 다 봅니다.
///
/// 보통의 애니메이션은 [AppWidgetsBinding] 덕에 Flutter 가 알아서 줄입니다. 이 판정은 그래도 남는 곳
/// (스프링·시간 규칙·스크롤 넘김)에서 씁니다.
///
/// reduceMotion 이 바뀌어도 이 값을 읽은 위젯은 다시 그려지지 않습니다. 애니메이션을 시작하는
/// 순간에 읽어 씁니다.
bool reducesMotion(BuildContext context) =>
    (MediaQuery.maybeDisableAnimationsOf(context) ?? false) ||
    (View.maybeOf(
          context,
        )?.platformDispatcher.accessibilityFeatures.reduceMotion ??
        false);

/// iOS '동작 줄이기'도 Flutter 의 애니메이션 줄이기([SemanticsBinding.disableAnimations])에 싣습니다.
///
/// Flutter 는 이 값이 켜지면 모든 AnimationController 를 5% 길이로 줄여(화면 전환·시트·확인창·
/// Animated 위젯까지) 1~2 프레임에 끝냅니다. 그런데 이 값도 Android '애니메이션 삭제'만 읽어서 iOS 에서는
/// 아무것도 줄지 않았습니다. 애니메이션을 시작할 때마다 읽으므로 설정을 바꾸면 다음 애니메이션부터 먹습니다.
/// 도는 진행 표시(repeat)와 손가락을 따라 움직이는 것은 Flutter 가 줄이지 않습니다.
mixin ReduceMotionSemanticsBinding on SemanticsBinding {
  @override
  bool get disableAnimations =>
      super.disableAnimations || accessibilityFeatures.reduceMotion;
}

/// 앱이 쓰는 바인딩입니다. `main()` 맨 처음에 [WidgetsFlutterBinding.ensureInitialized] 대신 만듭니다.
///
/// 바인딩이 이미 만들어져 있으면 디버그 빌드에서 Flutter 가 잡아 줍니다.
class AppWidgetsBinding extends WidgetsFlutterBinding
    with ReduceMotionSemanticsBinding {}
