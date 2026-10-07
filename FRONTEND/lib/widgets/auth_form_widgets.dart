// 로그인·회원가입·비밀번호 찾기 화면이 함께 쓰는 입력란 모양과 제출 버튼입니다.
import 'package:flutter/material.dart';

import '../theme/app_palette.dart';

/// 인증 화면 입력란이 같은 모양과 포커스·오류 스타일을 쓰도록 공통화한 장식입니다.
///
/// [helper] 는 남은 시간처럼 낭독 문장을 따로 줘야 하는 안내에 씁니다. 둘 다 주면
/// [helper] 가 쓰입니다.
InputDecoration authInputDecoration(
  BuildContext context, {
  required String labelText,
  required String hintText,
  String? helperText,
  Widget? helper,
  Widget? suffixIcon,
}) {
  final isDark = Theme.of(context).brightness == Brightness.dark;
  final fillColor = isDark ? const Color(0xFF1C1C1E) : const Color(0xFFF1F1F4);
  final hintColor = isDark ? const Color(0xFF9A9A9A) : const Color(0xFF9E9E9E);
  final enabledBorderColor = isDark
      ? const Color(0xFF2C2C2E)
      : Colors.transparent;

  return InputDecoration(
    labelText: labelText,
    hintText: hintText,
    helper: helper,
    helperText: helper == null ? helperText : null,
    // 서버 문장은 두 문장까지라 한 줄로 자르면 뒤 문장(무엇을 할지)이 잘립니다.
    helperMaxLines: 2,
    errorMaxLines: 3,
    labelStyle: TextStyle(color: hintColor, fontSize: 15),
    hintStyle: TextStyle(color: hintColor, fontSize: 15),
    filled: true,
    fillColor: fillColor,
    contentPadding: const EdgeInsets.symmetric(horizontal: 22, vertical: 22),
    border: OutlineInputBorder(
      borderRadius: BorderRadius.circular(28),
      borderSide: BorderSide.none,
    ),
    enabledBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(28),
      borderSide: BorderSide(color: enabledBorderColor, width: isDark ? 1 : 0),
    ),
    focusedBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(28),
      borderSide: const BorderSide(color: AppPalette.accent, width: 1.5),
    ),
    errorBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(28),
      borderSide: const BorderSide(color: Colors.redAccent, width: 1.2),
    ),
    focusedErrorBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(28),
      borderSide: const BorderSide(color: Colors.redAccent, width: 1.5),
    ),
    suffixIcon: suffixIcon,
  );
}

/// 인증 화면 맨 아래의 강조색 제출 버튼입니다. 처리 중에는 눌리지 않고 진행 표시를 보입니다.
class AuthSubmitButton extends StatelessWidget {
  const AuthSubmitButton({
    super.key,
    required this.label,
    required this.loadingSemanticsLabel,
    required this.isLoading,
    required this.onPressed,
  });

  final String label;

  /// 처리 중 진행 표시를 낭독기가 읽을 문장입니다(예: '회원가입 처리 중').
  final String loadingSemanticsLabel;
  final bool isLoading;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: 60,
      child: ElevatedButton(
        onPressed: isLoading ? null : onPressed,
        style: ElevatedButton.styleFrom(
          elevation: 0,
          backgroundColor: AppPalette.accent,
          disabledBackgroundColor: const Color(0x8C4A4EFE),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(30),
          ),
        ),
        child: isLoading
            ? Semantics(
                label: loadingSemanticsLabel,
                liveRegion: true,
                child: const SizedBox(
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(
                    strokeWidth: 2.4,
                    color: Colors.white,
                  ),
                ),
              )
            : Text(
                label,
                style: const TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.w700,
                  color: Colors.white,
                ),
              ),
      ),
    );
  }
}

/// 인증 화면 아래쪽의 밑줄 친 이동 링크입니다(예: '계정이 없으신가요? 회원가입').
class AuthLinkButton extends StatelessWidget {
  const AuthLinkButton({
    super.key,
    required this.label,
    required this.onPressed,
  });

  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return TextButton(
      onPressed: onPressed,
      style: TextButton.styleFrom(minimumSize: const Size(48, 48)),
      child: Text(
        label,
        style: TextStyle(
          color: isDark ? const Color(0xFFB8B8BE) : const Color(0xFF5F6368),
          fontSize: 14,
          decoration: TextDecoration.underline,
        ),
      ),
    );
  }
}
