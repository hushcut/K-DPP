import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/models/clothes.dart';

void main() {
  group('ClosetProvider', () {
    test('새 의류를 추가하면 items와 selectedClothes가 함께 갱신된다', () async {
      final provider = ClosetProvider();

      final initialCount = provider.count;

      final newClothes = Clothes(
        title: '테스트 셔츠',
        category: '상의',
        health: 88,
        materials: {'cotton': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 7.5,
      );

      await provider.addClothes(newClothes);

      expect(provider.count, initialCount + 1);
      expect(provider.latestItem?.title, '테스트 셔츠');
      expect(provider.selectedClothes?.title, '테스트 셔츠');
      expect(provider.currentReportItem?.title, '테스트 셔츠');
    });

    test('selectClothes를 호출하면 currentReportItem이 해당 의류로 바뀐다', () {
      final provider = ClosetProvider();

      final target = provider.items.first;
      provider.selectClothes(target);

      expect(provider.selectedClothes, target);
      expect(provider.currentReportItem, target);
    });

    test('totalCarbonFootprint와 averageHealth가 정상 계산된다', () {
      final provider = ClosetProvider();

      expect(provider.totalCarbonFootprint, greaterThan(0));
      expect(provider.averageHealth, greaterThan(0));
    });
  });
}