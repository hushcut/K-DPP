import 'package:flutter/material.dart';

import '../theme/app_palette.dart';

/// 배경 없이 택과 잎을 표시합니다. 인접한 제목이 있으면 semanticLabel을 null로 둡니다.
class KdppLogoMark extends StatelessWidget {
  const KdppLogoMark({super.key, this.size = 34, this.semanticLabel = 'K-DPP'});

  static const String assetPath = 'assets/images/kdpp_logo.png';

  final double size;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final image = Image.asset(
      assetPath,
      width: size,
      height: size,
      fit: BoxFit.contain,
      filterQuality: FilterQuality.high,
      excludeFromSemantics: true,
      errorBuilder: (context, error, stackTrace) => CustomPaint(
        size: Size.square(size),
        painter: const _KdppLogoPainter(),
      ),
    );

    if (semanticLabel == null) return ExcludeSemantics(child: image);
    return Semantics(
      label: semanticLabel,
      image: true,
      child: ExcludeSemantics(child: image),
    );
  }
}

/// assets/images/kdpp_logo_mark.svg와 같은 100×100 좌표계의 폴백입니다.
/// 자산 로드 실패 중에도 투명 배경과 택/잎 색상을 유지합니다.
class _KdppLogoPainter extends CustomPainter {
  const _KdppLogoPainter();

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.scale(size.width / 100, size.height / 100);
    final tag = Path()
      ..fillType = PathFillType.evenOdd
      ..moveTo(41, 11)
      ..lineTo(59, 11)
      ..lineTo(77, 29)
      ..lineTo(77, 82)
      ..quadraticBezierTo(77, 89, 70, 89)
      ..lineTo(30, 89)
      ..quadraticBezierTo(23, 89, 23, 82)
      ..lineTo(23, 29)
      ..close()
      ..addOval(Rect.fromCircle(center: const Offset(50, 28), radius: 5.5));
    canvas.drawPath(tag, Paint()..color = AppPalette.accent);
    final leaf = Path()
      ..moveTo(37, 72)
      ..cubicTo(33, 54, 43, 45, 63, 44)
      ..cubicTo(66, 62, 54, 76, 37, 72)
      ..close();
    canvas.drawPath(leaf, Paint()..color = const Color(0xFF63D68B));
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _KdppLogoPainter oldDelegate) => false;
}
