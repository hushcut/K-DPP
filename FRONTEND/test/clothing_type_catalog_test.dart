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

  test('hasDefaultTitle recognizes current and legacy generated titles', () {
    expect(ClothingTypeCatalog.hasDefaultTitle('니트'), isTrue);
    expect(ClothingTypeCatalog.hasDefaultTitle('홍길동 니트'), isTrue);
    expect(ClothingTypeCatalog.hasDefaultTitle('새 옷'), isFalse);
  });
}
