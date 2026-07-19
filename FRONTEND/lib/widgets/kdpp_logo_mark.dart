import 'package:flutter/material.dart';

/// 지정한 정사각형 크기로 K-DPP 로고 자산을 표시하는 공용 위젯입니다.
///
/// 자산을 불러오지 못하면 동일한 영역에 브랜드 색상의 친환경 아이콘을 표시합니다.
class KdppLogoMark extends StatelessWidget {
  const KdppLogoMark({super.key, this.size = 34, this.borderRadius});

  /// 앱 번들에 포함된 로고 이미지 경로입니다.
  static const String assetPath = 'assets/images/kdpp_logo.png';

  // 로고의 가로·세로 크기와 선택적 모서리 반경입니다.
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
