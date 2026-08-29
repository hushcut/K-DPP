import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/services/scan_save_service.dart';
import 'package:k_dpp/utils/clothing_type_catalog.dart';

void main() {
  group('ScanSaveService', () {
    const service = ScanSaveService();

    test('buildClothes creates Clothes with estimated health and carbon', () {
      final result = service.buildClothes(
        title: ' 홍길동 코튼 셔츠 ',
        category: '상의',
        materials: {'cotton': 100},
        careInstruction: '찬물 세탁',
        clothingType: ClothingTypeCatalog.defaultOption,
      );

      expect(result, isA<ScanSaveSuccess>());

      final success = result as ScanSaveSuccess;
      expect(success.clothes.title, '홍길동 코튼 셔츠');
      expect(success.clothes.category, '상의');
      expect(success.clothes.health, 93);
      expect(success.clothes.carbonFootprint, 1.4);
      expect(success.clothes.minWeightGram, 100);
      expect(success.clothes.maxWeightGram, 250);
    });

    test('buildClothes rejects empty materials', () {
      final result = service.buildClothes(
        title: '홍길동 기타 의류',
        category: '상의',
        materials: {},
        careInstruction: '',
        clothingType: ClothingTypeCatalog.defaultOption,
      );

      expect(result, isA<ScanSaveFailure>());

      final failure = result as ScanSaveFailure;
      expect(failure.message, contains('소재를 1개 이상'));
    });

    test('buildClothes prefers valid server calculations', () {
      final result = service.buildClothes(
        title: '홍길동 코튼 셔츠',
        category: '상의',
        materials: {'cotton': 100},
        careInstruction: '찬물 세탁',
        clothingType: ClothingTypeCatalog.defaultOption,
        originalMaterials: const {'cotton': 100},
        serverHealth: 88,
        serverCarbonFootprint: 2.75,
        serverWeightGram: ClothingTypeCatalog.defaultOption.estimatedWeightGram,
        serverCalculationMethod: 'weight_based_v1',
      );

      final success = result as ScanSaveSuccess;
      expect(success.clothes.health, 88);
      expect(success.clothes.carbonFootprint, 2.75);
      expect(
        success.clothes.carbonFootprintSource,
        CarbonFootprintSource.server,
      );
    });

    test('buildClothes rejects material total that is not 100 percent', () {
      final result = service.buildClothes(
        title: '홍길동 기타 의류',
        category: '상의',
        materials: {'cotton': 80},
        careInstruction: '',
        clothingType: ClothingTypeCatalog.defaultOption,
      );

      expect(result, isA<ScanSaveFailure>());

      final failure = result as ScanSaveFailure;
      expect(failure.message, contains('현재 80.0%'));
    });
  });
}
