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

    test('validateMaterialNameUnique flags a material already used in an earlier row', () {
      const message = '이미 입력한 소재예요.';

      // 글자가 아니라 표준명으로 본다: 면 = 코튼 = cotton.
      expect(ScanFormValidator.validateMaterialNameUnique('코튼', ['면']), message);
      expect(
        ScanFormValidator.validateMaterialNameUnique(' COTTON ', ['울', '면']),
        message,
      );
      expect(
        ScanFormValidator.validateMaterialNameUnique('폴리에스터', ['면', '울']),
        isNull,
      );
      // 부분 일치는 중복이 아니다 — '모'는 울의 별칭이지 모달이 아니다.
      expect(ScanFormValidator.validateMaterialNameUnique('모달', ['모']), isNull);
      // 빈 값은 validateMaterialName이 맡고, 빈 앞 줄과는 비교하지 않는다.
      expect(ScanFormValidator.validateMaterialNameUnique('', ['면']), isNull);
      expect(ScanFormValidator.validateMaterialNameUnique('면', ['', '  ']), isNull);
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
