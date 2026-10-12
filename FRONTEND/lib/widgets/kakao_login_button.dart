// 카카오 디자인 가이드(카카오 로그인 버튼)를 따른 '카카오 로그인' 버튼입니다.
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

/// 카카오 로그인 버튼입니다. 처리 중에는 눌리지 않고 진행 표시를 보입니다.
///
/// 카카오 디자인 가이드: 바탕 #FEE500, 말풍선 심볼 #000000, 글자 #000000 85%, 모서리 12.
/// 색·심볼 모양은 바꾸면 안 되므로 다크 모드와 처리 중에도 같은 색을 씁니다. 심볼은 카카오
/// SDK 가 함께 주는 말풍선 그림입니다.
class KakaoLoginButton extends StatelessWidget {
  const KakaoLoginButton({
    super.key,
    required this.isLoading,
    required this.onPressed,
  });

  static const containerColor = Color(0xFFFEE500);
  static const symbolColor = Color(0xFF000000);
  static const labelColor = Color(0xD9000000);
  static const label = '카카오 로그인';

  final bool isLoading;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: 56,
      child: ElevatedButton(
        onPressed: isLoading ? null : onPressed,
        style: ElevatedButton.styleFrom(
          elevation: 0,
          backgroundColor: containerColor,
          disabledBackgroundColor: containerColor,
          foregroundColor: symbolColor,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
        child: isLoading
            ? Semantics(
                label: '카카오 로그인 중',
                liveRegion: true,
                child: const SizedBox(
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(
                    strokeWidth: 2.4,
                    color: symbolColor,
                  ),
                ),
              )
            : Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SvgPicture.asset(
                    'assets/images/icon_talk_login.svg',
                    package: 'kakao_flutter_sdk_user',
                    width: 20,
                    height: 20,
                    colorFilter: const ColorFilter.mode(
                      symbolColor,
                      BlendMode.srcIn,
                    ),
                    excludeFromSemantics: true,
                  ),
                  const SizedBox(width: 8),
                  const Text(
                    label,
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                      color: labelColor,
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}

/// 카카오로 로그인한 계정임을 보여 주는 노란 원 안의 말풍선 표식입니다(설정 프로필 카드).
///
/// [KakaoLoginButton] 과 같은 바탕·심볼 색을 써서 로그인 버튼과 같은 표식으로 읽힙니다.
/// 뜻은 옆 글자('카카오 계정')가 전하므로 낭독에서는 빠집니다.
class KakaoSymbolBadge extends StatelessWidget {
  const KakaoSymbolBadge({super.key, this.size = 20});

  final double size;

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: const BoxDecoration(
          color: KakaoLoginButton.containerColor,
          shape: BoxShape.circle,
        ),
        child: SvgPicture.asset(
          'assets/images/icon_talk_login.svg',
          package: 'kakao_flutter_sdk_user',
          width: size * 0.55,
          height: size * 0.55,
          colorFilter: const ColorFilter.mode(
            KakaoLoginButton.symbolColor,
            BlendMode.srcIn,
          ),
          excludeFromSemantics: true,
        ),
      ),
    );
  }
}
