class ScanFormValidator {
  const ScanFormValidator._();

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

  static String? validateMaterialName(String? value) {
    final text = value?.trim() ?? '';

    if (text.isEmpty) {
      return '소재명을 입력해 주세요.';
    }

    return null;
  }

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
