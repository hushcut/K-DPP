import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/models/clothes.dart';

void main() {
  test('registeredAt은 JSON 저장과 복원을 거쳐도 유지된다', () {
    final registeredAt = DateTime(2026, 8, 24, 15, 30);
    final clothes = Clothes(
      title: '홍길동 저장 시각 셔츠',
      category: '상의',
      health: 90,
      materials: {'cotton': 100},
      careInstruction: '찬물 세탁',
      carbonFootprint: 3.4,
      registeredAt: registeredAt,
    );

    final restored = Clothes.fromJson(clothes.toJson());

    expect(restored.registeredAt, registeredAt);
  });

  test('registeredAt이 없는 옛 JSON은 null로 복원된다', () {
    final restored = Clothes.fromJson({
      'title': '홍길동 옛 셔츠',
      'category': '상의',
      'health': 70,
      'materials': {'cotton': 100.0},
      'careInstruction': '손세탁',
      'carbonFootprint': 2.2,
    });

    expect(restored.registeredAt, isNull);
  });

  test('compareByRecency는 등록 시각이 있는 항목을 최신으로 취급한다', () {
    final timed = Clothes(
      title: '홍길동 새 항목',
      category: '상의',
      health: 90,
      materials: {'cotton': 100},
      careInstruction: '찬물 세탁',
      carbonFootprint: 1.0,
      registeredAt: DateTime(2026, 8, 24),
    );
    final legacy = Clothes(
      title: '홍길동 옛 항목',
      category: '상의',
      health: 80,
      materials: {'cotton': 100},
      careInstruction: '찬물 세탁',
      carbonFootprint: 1.0,
    );

    expect(Clothes.compareByRecency(timed, legacy), lessThan(0));
    expect(Clothes.compareByRecency(legacy, timed), greaterThan(0));
    expect(Clothes.compareByRecency(legacy, legacy), 0);
  });
}
