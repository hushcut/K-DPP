// 뒤 화면을 흐리게 비추는 반투명 둥근 바탕을 그리는 위젯입니다.
import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';

/// 불투명도가 100% 미만이면 뒤 내용을 흐린 채 비추고, 100%면 흐림 없이 그대로 칠하는 둥근 바탕입니다.
///
/// 흐림(BackdropFilter)은 매 프레임 뒤 화면을 다시 읽어 비용이 크므로, 비칠 것이 없는 100%에서는
/// 걸지 않아 지금까지의 불투명한 바와 똑같이 그립니다.
///
/// [child] 는 투명 [Material] 위에 두어, 안의 [InkWell] 누름 효과가 바탕색 아래에 가려지지 않고 위에 보이게 합니다.
class FrostedSurface extends StatelessWidget {
  const FrostedSurface({
    super.key,
    required this.opacity,
    required this.color,
    required this.borderRadius,
    this.border,
    this.boxShadow,
    this.blurSigma = 14,
    this.child,
  });

  /// 배경색의 불투명도(0~1)입니다. 1이면 흐림 없이 불투명하게 칠합니다.
  final double opacity;

  /// 불투명도를 적용하기 전의 배경색입니다.
  final Color color;
  final BorderRadius borderRadius;
  final BoxBorder? border;

  /// 그림자는 흐림·클립 바깥에 그려 둥근 모서리 밖으로 번지게 합니다.
  final List<BoxShadow>? boxShadow;
  final double blurSigma;
  final Widget? child;

  @override
  Widget build(BuildContext context) {
    Widget surface = DecoratedBox(
      decoration: BoxDecoration(
        color: color.withValues(alpha: color.a * opacity),
        borderRadius: borderRadius,
        border: border,
      ),
      child: child == null
          ? null
          : Material(type: MaterialType.transparency, child: child),
    );

    if (opacity < 1) {
      surface = ClipRRect(
        borderRadius: borderRadius,
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: blurSigma, sigmaY: blurSigma),
          child: surface,
        ),
      );
    }

    final shadow = boxShadow;
    if (shadow == null) return surface;

    return DecoratedBox(
      decoration: BoxDecoration(borderRadius: borderRadius, boxShadow: shadow),
      child: surface,
    );
  }
}
