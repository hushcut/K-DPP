import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/models/clothes.dart';
import 'helpers/fake_closet_storage.dart';

void main() {
  group('ClosetProvider', () {
    test('새 의류를 추가하면 items와 selectedClothes가 함께 갱신된다', () async {
      final provider = ClosetProvider(storage: FakeClosetStorage());

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
      expect(provider.latestItem, isNotNull);
      expect(provider.selectedClothes, isNotNull);
      expect(provider.currentReportItem, isNotNull);

      expect(provider.latestItem!.title, '테스트 셔츠');
      expect(provider.selectedClothes!.title, '테스트 셔츠');
      expect(provider.currentReportItem!.title, '테스트 셔츠');
    });

    test('selectClothes를 호출하면 currentReportItem이 해당 의류로 바뀐다', () {
      final provider = ClosetProvider(storage: FakeClosetStorage());

      final target = provider.items.first;
      provider.selectClothes(target);

      expect(provider.selectedClothes, target);
      expect(provider.currentReportItem, target);
    });

    test('setCustomOrder를 호출하면 사용자 정의 순서가 반영된다', () async {
      final provider = ClosetProvider(storage: FakeClosetStorage());

      final reversed = provider.items.toList().reversed.toList();
      await provider.setCustomOrder(reversed);

      expect(provider.items.first.title, reversed.first.title);
      expect(provider.items.last.title, reversed.last.title);
    });

    test('removeClothesBatch를 호출하면 여러 의류가 삭제된다', () async {
      final provider = ClosetProvider(storage: FakeClosetStorage());

      final newClothes1 = Clothes(
        title: '테스트 상의',
        category: '상의',
        health: 80,
        materials: {'cotton': 100},
        careInstruction: '손세탁',
        carbonFootprint: 8.1,
      );

      final newClothes2 = Clothes(
        title: '테스트 하의',
        category: '하의',
        health: 72,
        materials: {'denim': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 12.3,
      );

      await provider.addClothes(newClothes1);
      await provider.addClothes(newClothes2);

      final beforeCount = provider.count;
      await provider.removeClothesBatch([newClothes1, newClothes2]);

      expect(provider.count, beforeCount - 2);
    });
  });
}