import 'package:flutter/material.dart';

class KdppLogoMark extends StatelessWidget {
  const KdppLogoMark({super.key, this.size = 34, this.borderRadius});

  static const String assetPath = 'assets/images/kdpp_logo.png';

  final double size;
  final double? borderRadius;

  @override
  Widget build(BuildContext context) {
    final radius = borderRadius ?? size * 0.28;

    return Semantics(
      label: 'K-DPP',
      image: true,
      child: ExcludeSemantics(
        child: ClipRRect(
          borderRadius: BorderRadius.circular(radius),
          child: Image.asset(
            assetPath,
            width: size,
            height: size,
            fit: BoxFit.cover,
            filterQuality: FilterQuality.high,
            errorBuilder: (context, error, stackTrace) {
              return Container(
                width: size,
                height: size,
                decoration: BoxDecoration(
                  color: const Color(0xFF4A4EFE),
                  borderRadius: BorderRadius.circular(radius),
                ),
                child: Icon(
                  Icons.eco_outlined,
                  color: Colors.white,
                  size: size * 0.58,
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}
