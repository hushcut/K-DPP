import 'package:flutter/services.dart';

/// 숫자 입력의 맨 앞 0을 지워 '0'에서 시작한 칸에 100을 치면 '0100'이 되지 않게 합니다.
///
/// 뒤에 숫자가 오는 0만 지우므로 '0'과 '0.5'처럼 소수점 앞의 0은 그대로 둡니다.
/// 붙여넣기나 커서를 옮긴 입력에도 같게 적용됩니다(2026-09-19 폰 확인).
class LeadingZeroTrimmer extends TextInputFormatter {
  const LeadingZeroTrimmer();

  static final RegExp _leadingZeros = RegExp(r'^0+(?=\d)');

  @override
  TextEditingValue formatEditUpdate(
    TextEditingValue oldValue,
    TextEditingValue newValue,
  ) {
    final text = newValue.text;
    final trimmed = text.replaceFirst(_leadingZeros, '');
    if (trimmed == text) return newValue;

    final removed = text.length - trimmed.length;
    final offset = (newValue.selection.baseOffset - removed).clamp(
      0,
      trimmed.length,
    );
    return TextEditingValue(
      text: trimmed,
      selection: TextSelection.collapsed(offset: offset),
    );
  }
}
