/// 옷장 목록에 적용할 정렬 기준입니다.
///
/// 저장소에는 enum 이름 대신 [storageValue] 문자열을 기록합니다.
/// 열거자 순서나 이름이 바뀌어도 이미 저장된 값이 깨지지 않게 하기 위함입니다.
enum ClosetSortOption {
  eco('eco'),
  health('health'),
  latest('latest'),
  custom('custom');

  const ClosetSortOption(this.storageValue);

  /// 로컬 저장소에 기록하는 값입니다.
  final String storageValue;

  /// 저장된 값이 없거나 알 수 없는 문자열이면 기본값 [ClosetSortOption.eco]를 돌려줍니다.
  static ClosetSortOption fromStorage(String? value) {
    for (final option in ClosetSortOption.values) {
      if (option.storageValue == value) return option;
    }

    return ClosetSortOption.eco;
  }
}
