import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/models/scan_result.dart';
import 'package:k_dpp/services/scan_draft_service.dart';
import 'package:k_dpp/utils/clothing_type_catalog.dart';

void main() {
  group('ScanDraftService', () {
    const service = ScanDraftService();

    test('inferInitialType maps scan result category to clothing type', () {
      final result = ScanResult(
        materials: {'cotton': 100},
        careInstruction: '찬물 세탁',
        category: 'pants',
      );

      final inferredType = service.inferInitialType(result);

      expect(inferredType.estimatedWeightGram, 680);
    });

    test('buildFromResult keeps scanned title when it exists', () {
      final result = ScanResult(
        title: ' 홍길동 코튼 셔츠 ',
        materials: {'cotton': 100},
        careInstruction: '찬물 세탁',
        health: 90,
        carbonFootprint: 4.2,
        weightGram: 180,
        calculationMethod: 'weight_based_v1',
      );

      final draft = service.buildFromResult(
        result: result,
        clothingType: ClothingTypeCatalog.defaultOption,
      );

      expect(draft.title, '홍길동 코튼 셔츠');
      expect(draft.materials, {'cotton': 100});
      expect(draft.careInstruction, '찬물 세탁');
      expect(draft.serverHealth, 90);
      expect(draft.serverCarbonFootprint, 4.2);
      expect(draft.serverWeightGram, 180);
      expect(draft.serverCalculationMethod, 'weight_based_v1');
      expect(draft.isManualMaterialMode, isFalse);
    });

    test('buildFromResult uses default title when scan title is empty', () {
      final result = ScanResult(
        title: ' ',
        materials: {'polyester': 100},
        careInstruction: '단독 세탁',
      );

      final draft = service.buildFromResult(
        result: result,
        clothingType: ClothingTypeCatalog.defaultOption,
      );

      expect(draft.title, ClothingTypeCatalog.defaultOption.defaultTitle);
    });

    test('buildFromResult는 서버 표시명을 소재 구성에 사용한다', () {
      final result = ScanResult(
        materials: const {'cotton': 100},
        materialDetails: const [
          ScanMaterialDetail(
            originalName: 'cotton',
            displayName: '면(cotton)',
            ratio: 100,
            isSupported: true,
          ),
        ],
        careInstruction: '찬물 세탁',
      );

      final draft = service.buildFromResult(
        result: result,
        clothingType: ClothingTypeCatalog.defaultOption,
      );

      expect(draft.materials, {'면(cotton)': 100.0});
    });

    test('buildManual creates empty manual draft', () {
      final draft = service.buildManual(
        clothingType: ClothingTypeCatalog.defaultOption,
      );

      expect(draft.materials, isEmpty);
      expect(draft.title, ClothingTypeCatalog.defaultOption.defaultTitle);
      expect(draft.isManualMaterialMode, isTrue);
    });
  });
}
