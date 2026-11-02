import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/models/clothing_type_option.dart';
import 'package:k_dpp/utils/clothing_type_catalog.dart';

void main() {
  test('defaultOption returns the first clothing type option', () {
    expect(ClothingTypeCatalog.defaultOption.label, '반팔 티셔츠');
    expect(ClothingTypeCatalog.defaultOption.category, '상의');
  });

  test('inferFromCategory maps Korean and English outer keywords', () {
    expect(ClothingTypeCatalog.inferFromCategory('아우터').label, '아우터');
    expect(ClothingTypeCatalog.inferFromCategory('winter coat').label, '아우터');
  });

  test('inferFromCategory maps bottom keywords to pants', () {
    expect(ClothingTypeCatalog.inferFromCategory('하의').label, '바지');
    expect(ClothingTypeCatalog.inferFromCategory('pants').label, '바지');
  });

  test('inferFromCategory는 티셔츠·맨투맨을 일반 셔츠보다 먼저 구분한다', () {
    expect(ClothingTypeCatalog.inferFromCategory('티셔츠').label, '반팔 티셔츠');
    expect(ClothingTypeCatalog.inferFromCategory('반팔 티셔츠').label, '반팔 티셔츠');
    expect(ClothingTypeCatalog.inferFromCategory('T-Shirt').label, '반팔 티셔츠');
    expect(ClothingTypeCatalog.inferFromCategory('긴팔 티셔츠').label, '긴팔 / 맨투맨');
    expect(ClothingTypeCatalog.inferFromCategory('Sweatshirt').label, '긴팔 / 맨투맨');
    expect(ClothingTypeCatalog.inferFromCategory('후드 티셔츠').label, '긴팔 / 맨투맨');
    expect(ClothingTypeCatalog.inferFromCategory('셔츠').label, '셔츠 / 블라우스');
    expect(ClothingTypeCatalog.inferFromCategory('blouse').label, '셔츠 / 블라우스');
  });

  test('hasDefaultTitle recognizes current and legacy generated titles', () {
    expect(ClothingTypeCatalog.hasDefaultTitle('니트'), isTrue);
    expect(ClothingTypeCatalog.hasDefaultTitle('홍길동 니트'), isTrue);
    expect(ClothingTypeCatalog.hasDefaultTitle('새 옷'), isFalse);
  });

  group('앱 내장 무게표', () {
    // 2026-09-16부터 무게는 숫자로 들고 있고 화면 문구는 숫자에서 만든다.
    // 서버 표(BACKEND/main.py CLOTHING_TYPE_OPTIONS)와 같은 값인지는
    // 백엔드 계약 테스트(test_clothing_type_contract.py)가 맞대어 본다.
    List<ClothingTypeOption> rangeOptions() => ClothingTypeCatalog.options
        .where(
          (option) => !option.isDirectWeightPlaceholder && !option.isDirectWeight,
        )
        .toList();

    test('범위 옵션 8종은 서버 식별자를 갖고, 문구는 숫자 범위와 같고, 아이콘은 식별자 규칙과 같다', () {
      final options = rangeOptions();
      expect(options.length, 8);
      expect(options.map((option) => option.id).toSet(), hasLength(8));

      for (final option in options) {
        expect(option.id, isNotNull, reason: option.label);
        expect(
          option.weightRangeLabel,
          '${ClothingTypeOption.formatWeightGram(option.minWeightGram)}~'
          '${ClothingTypeOption.formatWeightGram(option.maxWeightGram)}g',
          reason: option.label,
        );
        // 서버 표로 바뀌어도 같은 종류가 같은 아이콘으로 보여야 한다.
        expect(
          option.icon,
          ClothingTypeOption.iconForId(option.id!),
          reason: option.label,
        );
      }
    });

    test('범위 옵션 8종은 min <= 대표 무게 <= max를 만족한다', () {
      for (final option in rangeOptions()) {
        expect(
          option.minWeightGram <= option.estimatedWeightGram,
          isTrue,
          reason: '${option.label}: min(${option.minWeightGram}) > '
              '대표 무게(${option.estimatedWeightGram})',
        );
        expect(
          option.estimatedWeightGram <= option.maxWeightGram,
          isTrue,
          reason: '${option.label}: 대표 무게(${option.estimatedWeightGram}) > '
              'max(${option.maxWeightGram})',
        );
      }
    });

    test('표시 문자열이 옵션별로 고정된 형식을 유지한다', () {
      for (final option in ClothingTypeCatalog.options) {
        if (option.isDirectWeightPlaceholder) {
          expect(option.weightDisplayText, '실제 무게 입력');
        } else {
          expect(option.weightDisplayText, '예상 무게 ${option.weightRangeLabel}');
        }
      }
    });

    test('directWeight 옵션은 실제 무게 문구를 쓰고 min=max=입력값을 반환한다', () {
      final option = ClothingTypeOption.directWeight(
        label: '기타 의류',
        category: '상의',
        weightGram: 612.5,
      );

      expect(option.weightRangeLabel, '612.5g');
      expect(option.weightDisplayText, '실제 무게 612.5g');
      expect(option.minWeightGram, 612.5);
      expect(option.maxWeightGram, 612.5);
    });
  });
}
