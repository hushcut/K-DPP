/// 스캔 결과 편집 폼의 의류명과 소재 입력값을 검증한다.
class ScanFormValidator {
  const ScanFormValidator._();

  /// 의류명이 비어 있거나 두 글자보다 짧으면 화면에 표시할 오류 문구를 반환한다.
  static String? validateTitle(String? value) {
    final text = value?.trim() ?? '';

    if (text.isEmpty) {
      return '의류 이름을 입력해 주세요.';
    }

    if (text.length < 2) {
      return '의류 이름은 2자 이상 입력해 주세요.';
    }

    return null;
  }

  /// 앞뒤 공백을 제거한 소재명이 비어 있지 않은지 확인한다.
  static String? validateMaterialName(String? value) {
    final text = value?.trim() ?? '';

    if (text.isEmpty) {
      return '소재명을 입력해 주세요.';
    }

    return null;
  }

  /// 소재 비율을 숫자로 해석해 0~100 범위인지 확인한다.
  static String? validateMaterialValue(String? value) {
    final text = value?.trim() ?? '';

    if (text.isEmpty) {
      return '필수';
    }

    final parsed = double.tryParse(text.replaceAll('%', ''));

    if (parsed == null) {
      return '숫자만';
    }

    if (parsed < 0 || parsed > 100) {
      return '0~100';
    }

    return null;
  }
}
