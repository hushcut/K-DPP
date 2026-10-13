// 앱바·옷장 위 줄처럼 혼자 떠 있는 버튼의 유리 원·캡슐 모양과 누름 반응입니다(DECISIONS 224·225).
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/physics.dart';
import 'package:flutter/scheduler.dart';

/// 유리 버튼이 함께 쓰는 크기와 색입니다.
///
/// 흐림(BackdropFilter)은 걸지 않습니다. 버튼 뒤가 대부분 단색이라 흐려도 보이는 차이가 없고,
/// Android 에서 매 프레임 뒤 화면을 다시 읽는 비용만 늘기 때문입니다. 반투명 색만 칠합니다.
abstract final class AppGlassStyle {
  /// 보이는 원의 지름입니다(iOS 최소 터치 크기 44pt).
  static const double diameter = 44;

  /// 누를 수 있는 영역입니다. 보이는 원보다 넓게 잡아 Android 기준(48dp)을 맞춥니다.
  static const double tapTarget = 48;

  /// 앱바 왼쪽 "<" 칸 폭입니다. 왼쪽 여백 [leadingInset] + 누를 수 있는 영역 [tapTarget].
  static const double leadingWidth = leadingInset + tapTarget;
  static const double leadingInset = 8;

  /// 캡슐(글자 버튼)의 높이입니다.
  static const double capsuleHeight = diameter - 8;

  /// iOS 에서 누르는 동안 원이 부푸는 배율입니다. 원 44 는 약 55 까지 커집니다.
  static const double pressedScale = 1.25;

  /// Android 에서 누르는 동안 모서리 반지름이 줄어드는 비율입니다. 원 44 는 반지름 22 → 14 로
  /// 둥근 네모 쪽으로 눌립니다(Material 3 Expressive 의 모양 바뀜).
  static const double androidPressedCorner = 0.64;

  static bool _isDark(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark;

  /// 평소 바탕색입니다. 배경(#121212·#F8F9FC)과 조금만 다르게 옅게 칠합니다.
  static Color fill(BuildContext context) =>
      _isDark(context) ? const Color(0xE62C2C2E) : const Color(0xE6FFFFFF);

  /// 누르는 동안 바탕색입니다. 다크는 밝게, 라이트는 흰 원이 더 밝아질 수 없어 살짝 어둡게 합니다.
  static Color pressedFill(BuildContext context) =>
      _isDark(context) ? const Color(0xF2404044) : const Color(0xF2E9EAF0);

  /// 원 둘레의 옅은 테두리입니다.
  static Color border(BuildContext context) =>
      _isDark(context) ? const Color(0x1FFFFFFF) : const Color(0xFFE8E8EE);

  /// 유리 버튼의 바탕·테두리·누름 색을 담은 스타일입니다.
  ///
  /// [pressed] 는 [GlassPressBuilder] 가 정한 눌림입니다. iOS 에선 손가락이 버튼 밖으로 나가 버튼의
  /// 눌림이 풀려도 놓을 때까지 눌린 색을 유지하려고 따로 받습니다.
  ///
  /// Material 물결은 끕니다. 누름은 부풂(iOS)이나 모양 바뀜(Android)으로 보입니다.
  static ButtonStyle buttonStyle(
    BuildContext context, {
    required OutlinedBorder shape,
    required bool pressed,
    Size? fixedSize,
    Size? minimumSize,
    EdgeInsetsGeometry? padding,
  }) {
    final normalColor = fill(context);
    final pressedColor = pressedFill(context);
    final side = BorderSide(color: border(context));

    return ButtonStyle(
      backgroundColor: WidgetStateProperty.resolveWith(
        (states) => pressed || states.contains(WidgetState.pressed)
            ? pressedColor
            : normalColor,
      ),
      overlayColor: const WidgetStatePropertyAll(Colors.transparent),
      splashFactory: NoSplash.splashFactory,
      shape: WidgetStatePropertyAll(shape),
      side: WidgetStatePropertyAll(side),
      fixedSize: fixedSize == null ? null : WidgetStatePropertyAll(fixedSize),
      minimumSize: minimumSize == null
          ? null
          : WidgetStatePropertyAll(minimumSize),
      padding: padding == null ? null : WidgetStatePropertyAll(padding),
      tapTargetSize: MaterialTapTargetSize.padded,
      elevation: const WidgetStatePropertyAll(0),
      shadowColor: const WidgetStatePropertyAll(Colors.transparent),
      surfaceTintColor: const WidgetStatePropertyAll(Colors.transparent),
    );
  }
}

/// 혼자 떠 있는 아이콘 버튼입니다. 반투명 원 위에 아이콘을 둡니다.
///
/// 보이는 원은 [AppGlassStyle.diameter], 누를 수 있는 영역은 [AppGlassStyle.tapTarget] 입니다.
/// 누름 반응은 [GlassPressBuilder] 를 봅니다. [onPressed] 가 null 이면 흐리게 그리고 반응하지 않습니다.
class AppGlassIconButton extends StatelessWidget {
  const AppGlassIconButton({
    super.key,
    required this.icon,
    required this.onPressed,
    this.tooltip,
    this.color,
    this.disabledColor,
  });

  final Widget icon;
  final VoidCallback? onPressed;

  /// 낭독 이름입니다. 말풍선은 앱 테마에서 꺼져 있습니다(2026-09-24).
  final String? tooltip;
  final Color? color;
  final Color? disabledColor;

  @override
  Widget build(BuildContext context) {
    // 앱바 칸이 높이 56 을 꽉 채워 주더라도 원이 늘어나지 않게 가운데에 둡니다.
    return Center(
      child: GlassPressBuilder(
        builder: (context, states, pressed, corner) => IconButton(
          onPressed: onPressed,
          tooltip: tooltip,
          statesController: states,
          color: color,
          disabledColor: disabledColor,
          style: AppGlassStyle.buttonStyle(
            context,
            pressed: pressed,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(
                AppGlassStyle.diameter / 2 * corner,
              ),
            ),
            fixedSize: const Size.square(AppGlassStyle.diameter),
            minimumSize: const Size.square(AppGlassStyle.diameter),
            padding: EdgeInsets.zero,
          ),
          icon: icon,
        ),
      ),
    );
  }
}

/// 혼자 떠 있는 글자 버튼입니다. 유리 원과 같은 재질의 캡슐로 그립니다.
class AppGlassTextButton extends StatelessWidget {
  const AppGlassTextButton({
    super.key,
    required this.label,
    required this.onPressed,
  });

  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: GlassPressBuilder(
        // 캡슐은 원보다 넓어 같은 배율이면 더 크게 부풀어 보이므로 덜 키웁니다.
        pressedScale: 1.12,
        builder: (context, states, pressed, corner) => TextButton(
          onPressed: onPressed,
          statesController: states,
          style: AppGlassStyle.buttonStyle(
            context,
            pressed: pressed,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(
                AppGlassStyle.capsuleHeight / 2 * corner,
              ),
            ),
            minimumSize: const Size(56, AppGlassStyle.capsuleHeight),
            padding: const EdgeInsets.symmetric(horizontal: 14),
          ),
          child: Text(label),
        ),
      ),
    );
  }
}

/// [GlassPressBuilder.builder] 의 모양입니다.
///
/// `states` 는 버튼의 `statesController` 에 넘기고, `pressed` 로 바탕색을, `corner`(평소 1, Android
/// 에서 누르는 동안 [AppGlassStyle.androidPressedCorner] 까지)로 모서리 반지름을 정합니다.
typedef GlassPressWidgetBuilder =
    Widget Function(
      BuildContext context,
      WidgetStatesController states,
      bool pressed,
      double corner,
    );

/// 버튼의 누름 상태를 만들어 [builder] 에 넘기고, 플랫폼에 맞는 누름 반응을 그립니다(DECISIONS 225).
///
/// - iOS: 손가락이 닿으면 스프링으로 [pressedScale] 까지 부풀고, 누른 채 당기면 그 방향으로 끌려가며
///   길쭉해집니다(많이 당길수록 덜 늘어나는 고무줄 저항). 놓으면 스프링으로 한 번 넘쳤다가 돌아옵니다.
///   버튼 밖으로 끌고 나가면 누름은 취소되지만, 부푼 모양과 색은 놓을 때까지 남습니다. 스크롤이
///   시작되면 그 자리에서 놓은 것처럼 돌아옵니다.
/// - Android: 크기는 그대로 두고, 누르는 동안 모서리가 줄어 둥근 네모 쪽으로 눌립니다.
///
/// 모양 변화는 그림으로만(Transform) 하므로 옆 위젯 배치는 그대로입니다. '동작 줄이기'(iOS 동작
/// 줄이기·Android 애니메이션 삭제)가 켜져 있으면 색 변화만 남고, 누를 수 없는 버튼은 반응하지 않습니다.
class GlassPressBuilder extends StatefulWidget {
  const GlassPressBuilder({
    super.key,
    required this.builder,
    this.pressedScale = AppGlassStyle.pressedScale,
  });

  final GlassPressWidgetBuilder builder;

  /// iOS 에서 누르는 동안 부푸는 배율입니다.
  final double pressedScale;

  /// 부풀고 돌아오는 스프링입니다. 감쇠비 1 미만이라 떼는 순간 한 번 넘쳤다가 자리 잡습니다.
  static final SpringDescription spring = SpringDescription.withDampingRatio(
    mass: 1,
    stiffness: 520,
    ratio: 0.55,
  );

  /// 당길 때 끌려가는 최대 거리와 최대로 늘어나는 비율입니다.
  static const double maxPullOffset = 10;
  static const double maxStretch = 0.15;

  /// 이만큼 당기면 최대치의 절반까지 갑니다. 고무줄 저항의 세기입니다.
  static const double pullHalfDistance = 40;

  /// 모양을 바꾸는 Transform 의 키입니다(테스트용).
  static const transformKey = ValueKey('glass-press-transform');

  @override
  State<GlassPressBuilder> createState() => _GlassPressBuilderState();
}

class _GlassPressBuilderState extends State<GlassPressBuilder>
    with TickerProviderStateMixin {
  final _states = WidgetStatesController();

  /// iOS 부풂 배율(평소 1)입니다.
  late final AnimationController _scale = AnimationController.unbounded(
    vsync: this,
    value: 1,
  );

  /// Android 모서리 비율(평소 1)입니다.
  late final AnimationController _corner = AnimationController.unbounded(
    vsync: this,
    value: 1,
  );

  /// iOS 당김의 남은 몫입니다. 당기는 동안 1, 놓으면 스프링으로 0 이 됩니다(넘치면 잠깐 음수).
  late final AnimationController _pullFactor = AnimationController.unbounded(
    vsync: this,
    value: 0,
  );

  /// 손가락이 처음 닿은 곳에서 움직인 거리입니다(iOS).
  final _pull = ValueNotifier<Offset>(Offset.zero);

  /// 지금 화면에 보이는 눌림입니다. iOS 는 손가락 기준, Android 는 버튼의 눌림 기준입니다.
  bool _pressed = false;

  int? _pointer;
  Offset _pointerOrigin = Offset.zero;
  ValueListenable<bool>? _scrolling;

  bool get _isIOS => switch (Theme.of(context).platform) {
    TargetPlatform.iOS || TargetPlatform.macOS => true,
    _ => false,
  };

  bool get _reduceMotion =>
      MediaQuery.maybeDisableAnimationsOf(context) ?? false;

  bool get _enabled => !_states.value.contains(WidgetState.disabled);

  @override
  void initState() {
    super.initState();
    _states.addListener(_handleStates);
  }

  @override
  void dispose() {
    _stopWatchingScroll();
    _states.removeListener(_handleStates);
    _states.dispose();
    _scale.dispose();
    _corner.dispose();
    _pullFactor.dispose();
    _pull.dispose();
    super.dispose();
  }

  // 버튼은 그리는 도중에도(누를 수 없게 바뀔 때 등) 상태를 바꿔 알립니다. 그때 바로 다시 그리면
  // Flutter 가 막으므로, 그리는 중이면 그 프레임 뒤로 미룹니다.
  void _afterBuild(VoidCallback action) {
    if (SchedulerBinding.instance.schedulerPhase ==
        SchedulerPhase.persistentCallbacks) {
      SchedulerBinding.instance.addPostFrameCallback((_) {
        if (mounted) action();
      });
    } else {
      action();
    }
  }

  void _handleStates() {
    if (_isIOS) {
      // iOS 의 눌림은 손가락 기준이지만, 누르는 중에 누를 수 없게 바뀌면 바로 놓아 줍니다.
      if (_pointer != null && !_enabled) _afterBuild(_release);
      return;
    }
    final pressed = _states.value.contains(WidgetState.pressed);
    if (pressed == _pressed) return;
    _afterBuild(() => _setPressed(pressed));
  }

  void _setPressed(bool pressed) {
    if (pressed == _pressed) return;
    setState(() => _pressed = pressed);

    if (_isIOS) {
      _springTo(_scale, pressed ? widget.pressedScale : 1);
    } else {
      _springTo(_corner, pressed ? AppGlassStyle.androidPressedCorner : 1);
    }
  }

  void _springTo(AnimationController controller, double target) {
    // '동작 줄이기'면 움직이지 않고 늘 쉬는 값(부풂·모서리 1, 당김 0)에 둡니다.
    if (_reduceMotion) {
      final rest = identical(controller, _pullFactor) ? 0.0 : 1.0;
      if (controller.value != rest) controller.value = rest;
      return;
    }
    // 지금 속도를 이어받아, 짧게 탭해도 부풀던 힘으로 한 번 솟았다가 돌아옵니다.
    controller.animateWith(
      SpringSimulation(
        GlassPressBuilder.spring,
        controller.value,
        target,
        controller.velocity,
      ),
    );
  }

  void _handlePointerDown(PointerDownEvent event) {
    if (!_isIOS || _pointer != null || !_enabled) return;
    _pointer = event.pointer;
    _pointerOrigin = event.position;
    _pull.value = Offset.zero;
    _pullFactor.stop();
    _pullFactor.value = _reduceMotion ? 0 : 1;
    _watchScroll();
    _setPressed(true);
  }

  void _handlePointerMove(PointerMoveEvent event) {
    if (event.pointer != _pointer || _reduceMotion) return;
    _pull.value = event.position - _pointerOrigin;
  }

  void _handlePointerEnd(PointerEvent event) {
    if (event.pointer != _pointer) return;
    _release();
  }

  void _release() {
    if (_pointer == null) return;
    _pointer = null;
    _stopWatchingScroll();
    _springTo(_pullFactor, 0);
    _setPressed(false);
  }

  void _watchScroll() {
    _scrolling = Scrollable.maybeOf(context)?.position.isScrollingNotifier;
    _scrolling?.addListener(_handleScrolling);
  }

  void _stopWatchingScroll() {
    _scrolling?.removeListener(_handleScrolling);
    _scrolling = null;
  }

  void _handleScrolling() {
    if (_scrolling?.value ?? false) _release();
  }

  /// 부풂·당김을 담은 변환입니다. 당긴 방향 u 로 s 배 늘리고, 그 수직으로는 조금 줄입니다.
  Matrix4 _transform() {
    final scale = _scale.value;
    final raw = _pull.value;
    final distance = raw.distance;
    if (distance == 0 || _pullFactor.value == 0) {
      return Matrix4.diagonal3Values(scale, scale, 1);
    }

    // 많이 당길수록 덜 따라가는 고무줄 저항입니다(0 → 1 로 다가감).
    final resistance =
        distance / (distance + GlassPressBuilder.pullHalfDistance);
    final amount = resistance * _pullFactor.value;
    final ux = raw.dx / distance;
    final uy = raw.dy / distance;

    final stretch = 1 + GlassPressBuilder.maxStretch * amount.abs();
    final squash = 1 - (stretch - 1) * 0.5;
    final a = (stretch * ux * ux + squash * uy * uy) * scale;
    final b = (stretch - squash) * ux * uy * scale;
    final d = (stretch * uy * uy + squash * ux * ux) * scale;
    final shift = GlassPressBuilder.maxPullOffset * amount;

    return Matrix4.identity()
      ..setEntry(0, 0, a)
      ..setEntry(0, 1, b)
      ..setEntry(1, 0, b)
      ..setEntry(1, 1, d)
      ..setEntry(0, 3, ux * shift)
      ..setEntry(1, 3, uy * shift);
  }

  @override
  Widget build(BuildContext context) {
    return Listener(
      onPointerDown: _handlePointerDown,
      onPointerMove: _handlePointerMove,
      onPointerUp: _handlePointerEnd,
      onPointerCancel: _handlePointerEnd,
      child: AnimatedBuilder(
        animation: Listenable.merge([_scale, _pullFactor, _pull]),
        builder: (context, child) => Transform(
          key: GlassPressBuilder.transformKey,
          alignment: Alignment.center,
          transform: _transform(),
          child: child,
        ),
        child: AnimatedBuilder(
          animation: _corner,
          builder: (context, _) => widget.builder(
            context,
            _states,
            _pressed,
            math.max(0, _corner.value),
          ),
        ),
      ),
    );
  }
}
