import 'material_name.dart';

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

  /// 앞 줄에 이미 같은 소재가 있으면 오류 문구를 반환한다.
  ///
  /// 같은지는 글자가 아니라 표준명으로 본다(면 = 코튼 = cotton, [MaterialName.standardize]).
  /// [earlierNames]는 이 줄보다 **앞에 있는** 줄들의 소재명이다 — 오류는 뒤 줄에만 보여
  /// 사용자가 어느 칸을 고칠지 분명하게 한다. 빈 값은 [validateMaterialName]이 맡는다.
  static String? validateMaterialNameUnique(
    String? value,
    Iterable<String> earlierNames,
  ) {
    final text = value?.trim() ?? '';

    if (text.isEmpty) {
      return null;
    }

    final standardName = MaterialName.standardize(text);
    final isDuplicate = earlierNames.any(
      (name) =>
          name.trim().isNotEmpty &&
          MaterialName.standardize(name) == standardName,
    );

    if (isDuplicate) {
      return '이미 입력한 소재예요.';
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

    // "NaN" 입력도 숫자 오류로 처리해 합계가 NaN%로 표시되는 것을 막는다.
    if (parsed == null || parsed.isNaN) {
      return '숫자만';
    }

    if (parsed < 0 || parsed > 100) {
      return '0~100';
    }

    return null;
  }
}
