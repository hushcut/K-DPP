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

    test('buildManual은 서버가 보낸 부분 인식 결과를 초기값으로 쓴다', () {
      final draft = service.buildManual(
        clothingType: ClothingTypeCatalog.defaultOption,
        partialMaterials: const {'cotton': 60, 'wool': 15},
        careInstruction: '손세탁; 표백 금지',
        rawOcrPreview: '  COTTON 60% WOOL 15%  ',
      );

      expect(draft.materials, {'cotton': 60.0, 'wool': 15.0});
      expect(draft.careInstruction, '손세탁; 표백 금지');
      expect(draft.rawOcrPreview, 'COTTON 60% WOOL 15%');
      expect(draft.isManualMaterialMode, isTrue);
    });

    test('buildManual은 서버 값이 비어 있으면 기존 기본값을 유지한다', () {
      final draft = service.buildManual(
        clothingType: ClothingTypeCatalog.defaultOption,
        careInstruction: '   ',
        rawOcrPreview: '   ',
      );

      expect(draft.materials, isEmpty);
      expect(draft.careInstruction, ScanResult.defaultCareInstruction);
      expect(draft.rawOcrPreview, isEmpty);
    });

    test('buildManual은 폼에서 고칠 수 없는 소재 항목을 걸러낸다', () {
      final draft = service.buildManual(
        clothingType: ClothingTypeCatalog.defaultOption,
        partialMaterials: {
          ' cotton ': 60,
          '': 30,
          'linen': -5,
          'silk': double.nan,
        },
      );

      expect(draft.materials, {'cotton': 60.0});
    });

    test('buildManual은 지나치게 긴 라벨 원문을 잘라 낸다', () {
      final draft = service.buildManual(
        clothingType: ClothingTypeCatalog.defaultOption,
        rawOcrPreview: 'A' * 400,
      );

      expect(draft.rawOcrPreview.length, 303);
      expect(draft.rawOcrPreview.endsWith('...'), isTrue);
    });
  });
}
