import 'package:flutter/services.dart';

/// 소재 함유율 칸에 100을 넘는 값을 입력하지 못하게 합니다.
///
/// 100을 넘기면서 값이 커지는 입력은 받지 않고 직전 값을 그대로 둡니다. 붙여넣기도 같습니다.
/// 스캔 결과나 임시저장으로 이미 100을 넘게 채워진 칸은 값을 줄이는 입력만 받아,
/// 끝자리를 지우는 도중에 100을 넘는 값이 거쳐 가도 고칠 수 있게 합니다.
/// 숫자로 읽을 수 없는 입력은 그대로 통과시켜 저장 전 검증이 오류로 안내하게 합니다.
class PercentLimitFormatter extends TextInputFormatter {
  const PercentLimitFormatter();

  static const double max = 100;

  @override
  TextEditingValue formatEditUpdate(
    TextEditingValue oldValue,
    TextEditingValue newValue,
  ) {
    final next = _parse(newValue.text);
    if (next == null || next <= max) return newValue;

    final previous = _parse(oldValue.text);
    if (previous != null && next < previous) return newValue;

    return oldValue;
  }

  static double? _parse(String text) {
    final parsed = double.tryParse(text.trim().replaceAll('%', ''));
    return parsed == null || parsed.isNaN ? null : parsed;
  }
}
