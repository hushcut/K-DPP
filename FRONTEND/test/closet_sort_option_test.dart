import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/models/closet_sort_option.dart';

void main() {
  group('ClosetSortOption 저장 값', () {
    test('모든 값이 storageValue로 왕복한다', () {
      for (final option in ClosetSortOption.values) {
        expect(ClosetSortOption.fromStorage(option.storageValue), option);
      }
    });

    test('저장 값은 열거자 이름과 별개로 고정돼 있다', () {
      // 이름을 바꿔도 기기에 남은 값이 깨지지 않도록 문자열을 못 박아 둔다.
      expect(ClosetSortOption.eco.storageValue, 'eco');
      expect(ClosetSortOption.health.storageValue, 'health');
      expect(ClosetSortOption.latest.storageValue, 'latest');
      expect(ClosetSortOption.custom.storageValue, 'custom');
    });

    test('저장된 값이 없거나 알 수 없으면 친환경 순으로 돌아간다', () {
      expect(ClosetSortOption.fromStorage(null), ClosetSortOption.eco);
      expect(ClosetSortOption.fromStorage(''), ClosetSortOption.eco);
      expect(ClosetSortOption.fromStorage('예전에_쓰던_값'), ClosetSortOption.eco);
    });
  });
}
