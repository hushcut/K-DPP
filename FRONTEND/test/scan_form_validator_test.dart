import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/utils/scan_form_validator.dart';

void main() {
  group('ScanFormValidator', () {
    test('validateTitle requires a non-empty title with at least 2 chars', () {
      expect(ScanFormValidator.validateTitle(''), '의류 이름을 입력해 주세요.');
      expect(ScanFormValidator.validateTitle('A'), '의류 이름은 2자 이상 입력해 주세요.');
      expect(ScanFormValidator.validateTitle('홍길동 셔츠'), isNull);
    });

    test('validateMaterialName requires a material name', () {
      expect(ScanFormValidator.validateMaterialName(' '), '소재명을 입력해 주세요.');
      expect(ScanFormValidator.validateMaterialName('cotton'), isNull);
    });

    test('validateMaterialValue accepts percentages from 0 to 100', () {
      expect(ScanFormValidator.validateMaterialValue(''), '필수');
      expect(ScanFormValidator.validateMaterialValue('abc'), '숫자만');
      expect(ScanFormValidator.validateMaterialValue('-1'), '0~100');
      expect(ScanFormValidator.validateMaterialValue('101'), '0~100');
      expect(ScanFormValidator.validateMaterialValue('50%'), isNull);
      expect(ScanFormValidator.validateMaterialValue('33.3'), isNull);
    });
  });
}
