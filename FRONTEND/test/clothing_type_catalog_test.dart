import 'package:flutter_test/flutter_test.dart';
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
}
