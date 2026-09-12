import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/utils/material_name.dart';

/// 같은 소재가 등록 경로에 따라 다른 문자열로 저장된다 —
/// 스캔은 서버 표시명(한글 '면'), 자동완성은 `option.nameEn`(영문 'cotton').
/// 소재를 문자열로 판별하는 코드가 한쪽만 알아보면 스캔한 옷에서만 기능이 죽는다.
void main() {
  group('standardize', () {
    test('서버 시드의 한글명·별칭을 영문 표준명으로 되돌린다', () {
      const pairs = <String, String>{
        '면': 'cotton',
        '코튼': 'cotton',
        '폴리에스터': 'polyester',
        'poly': 'polyester',
        '레이온': 'rayon',
        '나일론': 'nylon',
        'polyamide': 'nylon',
        '울': 'wool',
        '모': 'wool',
        '아크릴': 'acrylic',
        '스판덱스': 'spandex',
        'lycra': 'spandex',
        '린넨': 'linen',
        '마': 'linen',
        '실크': 'silk',
        '견': 'silk',
        '비스코스': 'viscose',
        '모달': 'modal',
        '캐시미어': 'cashmere',
        '폴리우레탄': 'polyurethane',
        'pu': 'polyurethane',
        '가죽': 'leather',
        '라미': 'ramie',
        '텐셀': 'lyocell',
        '다운': 'down',
        '깃털': 'feather',
        '야크': 'yak',
        '모헤어': 'mohair',
        '대나무': 'bamboo',
        '큐프로': 'cupro',
      };

      pairs.forEach((alias, standardName) {
        expect(
          MaterialName.standardize(alias),
          standardName,
          reason: '$alias 가 $standardName 으로 표준화되지 않았습니다.',
        );
      });
    });

    test('영문 표준명은 그대로 두고 앞뒤 공백·대소문자만 정리한다', () {
      expect(MaterialName.standardize('cotton'), 'cotton');
      expect(MaterialName.standardize('  COTTON  '), 'cotton');
      expect(MaterialName.standardize(' 면 '), 'cotton');
      expect(MaterialName.standardize('PU'), 'polyurethane');
    });

    test('표에 없는 이름은 지어내지 않고 소문자로만 정리해 돌려준다', () {
      expect(MaterialName.standardize('Organic Cotton'), 'organic cotton');
      expect(MaterialName.standardize('알 수 없는 소재'), '알 수 없는 소재');
      expect(MaterialName.standardize(''), '');
    });
  });

  group('matchesAny', () {
    test('한글 소재명이 영문 키워드에 걸린다', () {
      expect(MaterialName.matchesAny(['면'], ['cotton', 'linen']), isTrue);
      expect(MaterialName.matchesAny(['울'], ['wool', 'silk']), isTrue);
      expect(MaterialName.matchesAny(['스판덱스'], ['spandex']), isTrue);
      expect(MaterialName.matchesAny(['폴리에스터'], ['polyester']), isTrue);
    });

    // 한글과 영문을 서로 비교만 하면 matchesAny가 늘 참(또는 늘 거짓)을 돌려줘도
    // 양변이 같아 통과한다. 기대값을 함께 못박아 참·거짓이 모두 나오게 한다.
    test('한글과 영문이 같은 판정을 내고, 그 판정이 실제로 갈린다', () {
      const cases = <List<Object>>[
        // [한글, 영문, 키워드, 기대값]
        ['면', 'cotton', ['cotton', 'linen'], true],
        ['면', 'cotton', ['wool', 'silk'], false],
        ['울', 'wool', ['wool', 'silk'], true],
        ['울', 'wool', ['polyester', 'nylon'], false],
        ['스판덱스', 'spandex', ['polyurethane', 'spandex'], true],
        ['스판덱스', 'spandex', ['cotton', 'linen'], false],
        ['폴리에스터', 'polyester', ['polyester', 'nylon'], true],
        ['폴리에스터', 'polyester', ['wool', 'silk'], false],
      ];

      for (final row in cases) {
        final korean = row[0] as String;
        final english = row[1] as String;
        final keywords = row[2] as List<String>;
        final expected = row[3] as bool;

        expect(
          MaterialName.matchesAny([korean], keywords),
          expected,
          reason: '$korean · $keywords 판정이 $expected 가 아닙니다.',
        );
        expect(
          MaterialName.matchesAny([english], keywords),
          expected,
          reason: '$english · $keywords 판정이 $expected 가 아닙니다.',
        );
      }
    });

    // 서버 별칭 '모'(wool)는 '모달'·'모헤어'의 부분 문자열이다.
    // 표준화 없이 부분 일치만 쓰면 모달 니트가 울 안내를 받는다.
    test("'모'로 시작하는 다른 소재를 울로 오인하지 않는다", () {
      expect(MaterialName.matchesAny(['모달'], ['wool']), isFalse);
      expect(MaterialName.matchesAny(['모헤어'], ['wool']), isFalse);
      expect(MaterialName.matchesAny(['모'], ['wool']), isTrue);
    });

    test('표에 없는 영문 자유 입력은 계열 판정에 걸린다', () {
      expect(
        MaterialName.matchesAny(['organic cotton'], ['cotton']),
        isTrue,
      );
      expect(
        MaterialName.matchesAny(['recycled polyester'], ['polyester']),
        isTrue,
      );
      expect(MaterialName.matchesAny(['알 수 없는 소재'], ['cotton']), isFalse);
    });

    // 알려진 한계 — 이 파리티는 영문 자유 입력에만 성립한다.
    // 키워드가 영문이고 표준화는 완전 일치라, 표에 없는 **한글** 조합은
    // 표준명으로 바뀌지도 않고 영문 키워드에 걸리지도 않는다.
    // 해소하려면 한글 부분 일치가 필요한데, 그러면 서버 별칭 '모'(wool)가
    // '모달'을 잡는 문제가 되살아난다. 지금은 동작을 고정만 해 둔다.
    test('표에 없는 한글 자유 입력은 계열 판정에서 빠진다 (알려진 한계)', () {
      expect(MaterialName.matchesAny(['오가닉 면'], ['cotton']), isFalse);
      expect(MaterialName.matchesAny(['재생 폴리에스터'], ['polyester']), isFalse);
      // 서버 표에 있는 정확한 이름이면 정상 동작한다.
      expect(MaterialName.matchesAny(['면'], ['cotton']), isTrue);
    });

    test('혼방이면 소재 중 하나만 걸려도 참이다', () {
      expect(
        MaterialName.matchesAny(['폴리에스터', '면'], ['cotton']),
        isTrue,
      );
      expect(MaterialName.matchesAny([], ['cotton']), isFalse);
    });
  });
}
