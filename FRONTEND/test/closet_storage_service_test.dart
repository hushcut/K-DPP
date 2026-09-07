import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/models/closet_sort_option.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/services/closet_storage_service.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';

/// 실제 저장소 구현을 직접 돌린다.
///
/// 다른 테스트는 모두 FakeClosetStorage를 주입하는데, 그 Fake는 객체를 메모리에
/// 그대로 담아 JSON 직렬화·계정 키 파생·손상 복구를 한 번도 실행하지 않는다.
/// 그래서 키 파생 규칙을 바꾸면 기존 사용자의 옷장이 통째로 사라지는데도
/// 나머지 테스트는 전부 통과한다. 여기서 그 경로를 고정한다.
void main() {
  late SharedPreferencesAsync prefs;

  setUp(() {
    SharedPreferencesAsyncPlatform.instance = InMemorySharedPreferencesAsync.empty();
    prefs = SharedPreferencesAsync();
  });

  Clothes buildClothes() {
    return Clothes(
      title: '린넨 셔츠',
      category: '상의',
      health: 88,
      materials: const {'linen': 60.0, 'cotton': 40.0},
      careInstruction: '찬물 세탁',
      carbonFootprint: 2.1,
      carbonFootprintSource: CarbonFootprintSource.server,
      carbonFootprintMin: 1.2,
      carbonFootprintMax: 3.0,
      minWeightGram: 100,
      maxWeightGram: 250,
      savedResultId: 42,
    );
  }

  group('계정별 옷장 저장', () {
    test('저장한 의류가 필드 그대로 복원된다', () async {
      final service = ClosetStorageService();
      final original = buildClothes();

      await service.saveClothesListFor('user@example.com', [original]);
      final restored = await service.loadClothesListFor('user@example.com');

      expect(restored, hasLength(1));
      final item = restored.single;
      expect(item.title, original.title);
      expect(item.category, original.category);
      expect(item.health, original.health);
      expect(item.materials, original.materials);
      expect(item.carbonFootprint, original.carbonFootprint);
      expect(item.carbonFootprintSource, original.carbonFootprintSource);
      expect(item.carbonFootprintMin, original.carbonFootprintMin);
      expect(item.carbonFootprintMax, original.carbonFootprintMax);
      expect(item.minWeightGram, original.minWeightGram);
      expect(item.maxWeightGram, original.maxWeightGram);
      expect(item.savedResultId, original.savedResultId);
    });

    test('대소문자·공백이 다른 같은 이메일은 같은 저장 키를 쓴다', () async {
      final service = ClosetStorageService();

      await service.saveClothesListFor('User@Example.com', [buildClothes()]);

      expect(await service.loadClothesListFor('  user@example.com  '), hasLength(1));
      expect(await service.hasSavedClothesListFor('USER@EXAMPLE.COM'), isTrue);
    });

    test('저장 키는 정규화한 이메일을 base64url로 인코딩하고 padding을 뗀 형태다', () async {
      final service = ClosetStorageService();

      await service.saveClothesListFor('user@example.com', [buildClothes()]);

      // 이 규칙이 바뀌면 기존 사용자의 옷장 키가 전부 어긋난다.
      final expectedKey =
          'closet_items_account_'
          '${base64Url.encode(utf8.encode('user@example.com')).replaceAll('=', '')}';
      expect(await prefs.getString(expectedKey), isNotNull);
    });

    test('다른 계정의 옷장은 서로 섞이지 않는다', () async {
      final service = ClosetStorageService();

      await service.saveClothesListFor('a@example.com', [buildClothes()]);

      expect(await service.loadClothesListFor('b@example.com'), isEmpty);
      expect(await service.hasSavedClothesListFor('b@example.com'), isFalse);
    });

    test('삭제하면 저장된 적 없는 상태로 돌아간다', () async {
      final service = ClosetStorageService();
      await service.saveClothesListFor('user@example.com', [buildClothes()]);

      await service.clearClothesListFor('user@example.com');

      expect(await service.hasSavedClothesListFor('user@example.com'), isFalse);
      expect(await service.loadClothesListOrNullFor('user@example.com'), isNull);
    });
  });

  group('손상된 저장값 처리', () {
    test('저장된 적 없음(null)과 저장값이 깨진 경우를 구분한다', () async {
      final service = ClosetStorageService();
      final key =
          'closet_items_account_'
          '${base64Url.encode(utf8.encode('user@example.com')).replaceAll('=', '')}';

      expect(await service.loadClothesListOrNullFor('user@example.com'), isNull);

      // 저장이 중간에 끊겨 JSON이 잘린 상황을 흉내 낸다.
      await prefs.setString(key, '[{"title":"린넨 셔츠"');

      // 깨진 값은 빈 목록으로 복구된다. null이 아니므로 호출부는 '저장된 적 있음'으로 본다.
      // 즉 사용자에게는 '불러오기 실패'가 아니라 '빈 옷장'으로 보인다 — 현재 의도된 동작이다.
      expect(await service.loadClothesListOrNullFor('user@example.com'), isEmpty);
      expect(await service.loadClothesListFor('user@example.com'), isEmpty);
    });

    test('배열이 아닌 JSON도 빈 목록으로 복구한다', () async {
      final service = ClosetStorageService();
      final key =
          'closet_items_account_'
          '${base64Url.encode(utf8.encode('user@example.com')).replaceAll('=', '')}';

      await prefs.setString(key, '{"title":"린넨 셔츠"}');

      expect(await service.loadClothesListFor('user@example.com'), isEmpty);
    });
  });

  group('정렬 기준 저장', () {
    test('enum 이름이 아니라 storageValue 문자열로 저장한다', () async {
      final service = ClosetStorageService();

      await service.saveClosetSortOption(ClosetSortOption.custom);

      expect(await prefs.getString('closet_sort_option'), 'custom');
      expect(await service.loadClosetSortOption(), ClosetSortOption.custom);
    });

    test('저장된 값이 없으면 친환경 순으로 시작한다', () async {
      final service = ClosetStorageService();

      expect(await service.loadClosetSortOption(), ClosetSortOption.eco);
    });

    test('알 수 없는 값이 저장돼 있어도 기본값으로 되돌린다', () async {
      final service = ClosetStorageService();
      await prefs.setString('closet_sort_option', '예전에_쓰던_값');

      expect(await service.loadClosetSortOption(), ClosetSortOption.eco);
    });
  });
}
