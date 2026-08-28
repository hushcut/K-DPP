import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/models/scan_result.dart';

void main() {
  group('ScanResult API contract', () {
    test('parses the canonical scan success payload', () {
      final result = ScanResult.fromJson({
        'materials': {'cotton': 80.0, 'polyester': 20.0},
        'care_instruction': '30도 이하 물에서 중성세제로 세탁하세요.',
        'title': '홍길동 코튼 셔츠',
        'category': '상의',
        'health': 85,
        'carbon_footprint': 4.78,
        'weight_gram': 520,
        'calculation_method': 'weight_based_v1',
        'unit': 'kg CO2eq',
        'saved_result_id': 13,
      });

      expect(result.materials, {'cotton': 80.0, 'polyester': 20.0});
      expect(result.careInstruction, '30도 이하 물에서 중성세제로 세탁하세요.');
      expect(result.title, '홍길동 코튼 셔츠');
      expect(result.category, '상의');
      expect(result.health, 85);
      expect(result.carbonFootprint, 4.78);
      expect(result.weightGram, 520);
      expect(result.calculationMethod, 'weight_based_v1');
      expect(result.unit, 'kg CO2eq');
      expect(result.savedResultId, 13);
    });

    test('accepts integer material ratios and optional result fields', () {
      final result = ScanResult.fromJson({
        'materials': {'cotton': 100},
        'care_instruction': '라벨의 관리 지침을 확인해 주세요.',
      });

      expect(result.materials, {'cotton': 100.0});
      expect(result.title, isNull);
      expect(result.category, isNull);
      expect(result.health, isNull);
      expect(result.carbonFootprint, isNull);
      expect(result.weightGram, isNull);
      expect(result.calculationMethod, isNull);
      expect(result.unit, isNull);
      expect(result.savedResultId, isNull);
    });

    test('parses compatible material list and camelCase fields', () {
      final result = ScanResult.fromJson({
        'composition': [
          {'name': 'cotton', 'percentage': '80%'},
          {'material': 'polyester', 'ratio': 20},
        ],
        'careInstruction': '찬물 세탁',
        'clothingName': '홍길동 혼방 셔츠',
        'type': '상의',
        'carbonFootprint': 3,
        'savedResultId': 7,
      });

      expect(result.materials, {'cotton': 80.0, 'polyester': 20.0});
      expect(result.careInstruction, '찬물 세탁');
      expect(result.title, '홍길동 혼방 셔츠');
      expect(result.category, '상의');
      expect(result.carbonFootprint, 3.0);
      expect(result.savedResultId, 7);
    });

    test('uses the default care instruction when it is missing', () {
      final result = ScanResult.fromJson({
        'materials': {'cotton': 100},
      });

      expect(result.careInstruction, ScanResult.defaultCareInstruction);
    });

    test('rejects a payload with an invalid materials type', () {
      expect(
        () => ScanResult.fromJson({'materials': 'cotton 100%'}),
        throwsFormatException,
      );
    });

    test('material_details를 파싱해 표시명 기준 소재 구성을 제공한다', () {
      final result = ScanResult.fromJson({
        'materials': {'cotton': 60, 'polyester': 40},
        'material_details': [
          {
            'original_name': 'cotton',
            'standard_name': 'cotton',
            'display_name': '면(cotton)',
            'ratio': 60,
            'is_supported': true,
          },
          {
            'original_name': 'polyester',
            'display_name': '폴리에스터(polyester)',
            'ratio': 40,
            'is_supported': true,
          },
        ],
      });

      expect(result.materialDetails, hasLength(2));
      expect(result.displayNameFor('cotton'), '면(cotton)');
      expect(result.displayMaterials, {
        '면(cotton)': 60.0,
        '폴리에스터(polyester)': 40.0,
      });
    });

    test('material_details가 없으면 원래 소재명을 그대로 사용한다', () {
      final result = ScanResult.fromJson({
        'materials': {'cotton': 100},
      });

      expect(result.materialDetails, isEmpty);
      expect(result.displayNameFor('cotton'), 'cotton');
      expect(result.displayMaterials, {'cotton': 100.0});
    });
  });
}
