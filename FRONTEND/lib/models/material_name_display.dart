/// 소재 이름을 화면에 어떤 언어로 보여줄지 정하는 기기 단위 설정입니다.
///
/// 옷장에 저장된 소재 키는 바꾸지 않고, 화면에 표시할 때만 적용합니다.
/// 저장소에는 enum 이름 대신 [storageValue] 문자열을 기록합니다.
/// 열거자 순서나 이름이 바뀌어도 이미 저장된 값이 깨지지 않게 하기 위함입니다.
enum MaterialNameDisplay {
  korean('ko', '한글'),
  english('en', '영문'),
  koreanAndEnglish('ko_en', '한글+영문');

  const MaterialNameDisplay(this.storageValue, this.label);

  /// 로컬 저장소에 기록하는 값입니다.
  final String storageValue;

  /// 설정 화면에 보여줄 이름입니다.
  final String label;

  /// 저장된 값이 없거나 알 수 없는 문자열이면 기본값 [MaterialNameDisplay.korean]을 돌려줍니다.
  static MaterialNameDisplay fromStorage(String? value) {
    for (final option in MaterialNameDisplay.values) {
      if (option.storageValue == value) return option;
    }

    return MaterialNameDisplay.korean;
  }
}
