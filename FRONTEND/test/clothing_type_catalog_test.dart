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

  group('무게 범위 표기 방어', () {
    // weightRangeLabel의 표기가 흔들리면(공백·단위 표기·전각 물결 등)
    // ClothingTypeOption의 정규식이 매치에 실패해 min/max가 대표 무게로
    // 조용히 폴백한다. 이 그룹은 그 폴백이 일어나지 않는지 지킨다.
    final rangeLabelPattern = RegExp(r'^(\d+(?:\.\d+)?)~(\d+(?:\.\d+)?)g$');

    List<ClothingTypeOption> rangeOptions() => ClothingTypeCatalog.options
        .where(
          (option) => !option.isDirectWeightPlaceholder && !option.isDirectWeight,
        )
        .toList();

    test('범위 옵션 8종은 라벨 그대로 파싱되고 대표 무게로 폴백하지 않는다', () {
      final options = rangeOptions();
      expect(options.length, 8);

      for (final option in options) {
        final match = rangeLabelPattern.firstMatch(option.weightRangeLabel);
        expect(
          match,
          isNotNull,
          reason:
              '${option.label}의 weightRangeLabel "${option.weightRangeLabel}"'
              '이(가) "숫자~숫자g" 형식이 아니다',
        );

        final expectedMin = double.parse(match!.group(1)!);
        final expectedMax = double.parse(match.group(2)!);

        expect(
          option.minWeightGram,
          expectedMin,
          reason:
              '${option.label}의 minWeightGram이 라벨 파싱값이 아니라 '
              '대표 무게(${option.estimatedWeightGram})로 폴백했다',
        );
        expect(
          option.maxWeightGram,
          expectedMax,
          reason:
              '${option.label}의 maxWeightGram이 라벨 파싱값이 아니라 '
              '대표 무게(${option.estimatedWeightGram})로 폴백했다',
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
