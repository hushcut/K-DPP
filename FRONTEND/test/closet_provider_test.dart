import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/models/analysis_history_record.dart';
import 'package:k_dpp/models/closet_sort_option.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/services/auth_session_storage_service.dart';
import 'helpers/fake_auth_session_storage.dart';
import 'helpers/fake_closet_storage.dart';

void main() {
  group('ClosetProvider', () {
    test('저장된 의류가 없는 새 옷장은 빈 상태로 시작한다', () {
      final provider = ClosetProvider(storage: FakeClosetStorage());

      expect(provider.items, isEmpty);
      expect(provider.count, 0);
      expect(provider.latestItem, isNull);
      expect(provider.selectedClothes, isNull);
      expect(provider.currentReportItem, isNull);
    });

    test('새 의류를 추가하면 items와 selectedClothes가 함께 갱신된다', () async {
      final provider = ClosetProvider(storage: FakeClosetStorage());

      final initialCount = provider.count;

      final newClothes = Clothes(
        title: '테스트 셔츠',
        category: '상의',
        health: 88,
        materials: {'cotton': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 7.5,
      );

      await provider.addClothes(newClothes);

      expect(provider.count, initialCount + 1);
      expect(provider.latestItem, isNotNull);
      expect(provider.selectedClothes, isNotNull);
      expect(provider.currentReportItem, isNotNull);

      expect(provider.latestItem!.title, '테스트 셔츠');
      expect(provider.selectedClothes!.title, '테스트 셔츠');
      expect(provider.currentReportItem!.title, '테스트 셔츠');
    });

    test('selectClothes를 호출하면 currentReportItem이 해당 의류로 바뀐다', () async {
      final provider = ClosetProvider(storage: FakeClosetStorage());
      final target = Clothes(
        title: '선택 테스트 셔츠',
        category: '상의',
        health: 84,
        materials: {'cotton': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 6.5,
      );

      await provider.addClothes(target);
      provider.selectClothes(target);

      expect(provider.selectedClothes, target);
      expect(provider.currentReportItem, target);
    });

    test('setCustomOrder를 호출하면 사용자 정의 순서가 반영된다', () async {
      final provider = ClosetProvider(storage: FakeClosetStorage());
      final first = Clothes(
        title: '첫 번째 셔츠',
        category: '상의',
        health: 80,
        materials: {'cotton': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 6.0,
      );
      final second = Clothes(
        title: '두 번째 바지',
        category: '하의',
        health: 75,
        materials: {'cotton': 98, 'polyurethane': 2},
        careInstruction: '단독 세탁',
        carbonFootprint: 9.0,
      );

      await provider.addClothes(first);
      await provider.addClothes(second);

      final reversed = [second, first];
      await provider.setCustomOrder(reversed);

      expect(provider.items.first.title, reversed.first.title);
      expect(provider.items.last.title, reversed.last.title);
    });

    test('구버전에 저장된 샘플 의류만 제거하고 사용자 의류는 유지한다', () async {
      final storage = FakeClosetStorage();
      final authStorage = FakeAuthSessionStorage()
        ..savedSession = AuthSession(
          accessToken: 'legacy-access-token',
          expiresAt: DateTime.now().add(const Duration(hours: 1)),
        );
      final userClothes = Clothes(
        title: '홍길동 리넨 셔츠',
        category: '상의',
        health: 90,
        materials: {'linen': 100},
        careInstruction: '찬물 손세탁',
        carbonFootprint: 4.8,
      );

      await storage.saveClothesList([
        Clothes(
          title: '오가닉 코튼 맨투맨',
          category: '상의',
          health: 65,
          materials: {'cotton': 100},
          careInstruction: '30도 이하 물에서 세탁하세요.',
          carbonFootprint: 15.5,
        ),
        userClothes,
        Clothes(
          title: '오래된 데님 팬츠',
          category: '하의',
          health: 10,
          materials: {'cotton': 98, 'polyurethane': 2},
          careInstruction: '단독 세탁 권장',
          carbonFootprint: 25.0,
        ),
      ]);
      await storage.saveUserName('홍길동');
      await storage.saveUserEmail('honggildong@example.com');

      final provider = ClosetProvider(
        storage: storage,
        authSessionStorage: authStorage,
      );
      await provider.loadFromStorage();

      expect(provider.items, [userClothes]);

      final restoredProvider = ClosetProvider(
        storage: storage,
        authSessionStorage: authStorage,
      );
      await restoredProvider.loadFromStorage();
      expect(restoredProvider.items, [userClothes]);
    });

    test('서로 다른 로그인 계정의 옷장을 분리해서 저장하고 복원한다', () async {
      final storage = FakeClosetStorage();
      final authStorage = FakeAuthSessionStorage();
      final provider = ClosetProvider(
        storage: storage,
        authSessionStorage: authStorage,
      );
      final firstAccountClothes = Clothes(
        title: '홍길동 코튼 셔츠',
        category: '상의',
        health: 88,
        materials: {'cotton': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 5.2,
      );
      final secondAccountClothes = Clothes(
        title: '김철수 데님 팬츠',
        category: '하의',
        health: 76,
        materials: {'cotton': 98, 'polyurethane': 2},
        careInstruction: '단독 세탁',
        carbonFootprint: 9.4,
      );

      await provider.setAuthenticatedUser(
        nickname: '홍길동',
        email: 'honggildong@example.com',
        accessToken: 'first-token',
        expiresInSeconds: 3600,
      );
      await provider.addClothes(firstAccountClothes);
      await provider.logout();

      expect(provider.items, isEmpty);

      await provider.setAuthenticatedUser(
        nickname: '김철수',
        email: 'kimcheolsu@example.com',
        accessToken: 'second-token',
        expiresInSeconds: 3600,
      );

      expect(provider.items, isEmpty);

      await provider.addClothes(secondAccountClothes);
      await provider.logout();

      await provider.setAuthenticatedUser(
        nickname: '홍길동',
        email: 'HONGGILDONG@example.com',
        accessToken: 'first-token-again',
        expiresInSeconds: 3600,
      );

      expect(provider.items, [firstAccountClothes]);
      expect(provider.items, isNot(contains(secondAccountClothes)));

      await provider.logout();
      await provider.setAuthenticatedUser(
        nickname: '김철수',
        email: 'kimcheolsu@example.com',
        accessToken: 'second-token-again',
        expiresInSeconds: 3600,
      );

      expect(provider.items, [secondAccountClothes]);
      expect(provider.items, isNot(contains(firstAccountClothes)));
    });

    test('다른 이메일 로그인 뒤에도 레거시 공용 옷장은 유실 없이 재시작 시 합쳐진다', () async {
      final storage = FakeClosetStorage();
      final authStorage = FakeAuthSessionStorage();
      final legacyClothes = Clothes(
        title: '홍길동 레거시 니트',
        category: '상의',
        health: 82,
        materials: {'wool': 100},
        careInstruction: '드라이클리닝 권장',
        carbonFootprint: 6.1,
      );

      // 로그아웃 상태(또는 계정 도입 전 버전)에서 공용 공간에 저장된 의류입니다.
      await storage.saveClothesList([legacyClothes]);

      // 저장된 기본 프로필과 다른 이메일로 로그인하면 마이그레이션 없이
      // 계정 옷장이 새로 만들어지지만, 레거시 데이터는 지워지면 안 됩니다.
      final provider = ClosetProvider(
        storage: storage,
        authSessionStorage: authStorage,
      );
      await provider.setAuthenticatedUser(
        nickname: '홍길동',
        email: 'honggildong@example.com',
        accessToken: 'legacy-keep-token',
        expiresInSeconds: 3600,
      );

      expect(await storage.hasSavedClothesList(), isTrue);

      // 앱 재시작: 세션 복원 시 레거시 옷장이 계정 옷장에 합쳐진 뒤에야 비워집니다.
      final restoredProvider = ClosetProvider(
        storage: storage,
        authSessionStorage: authStorage,
      );
      await restoredProvider.loadFromStorage();

      expect(restoredProvider.items, [legacyClothes]);
      expect(await storage.hasSavedClothesList(), isFalse);
    });

    test('세션 저장이 실패하면 로그인 상태를 메모리에 남기지 않는다', () async {
      final storage = FakeClosetStorage();
      final authStorage = FakeAuthSessionStorage()
        ..saveError = StateError('secure storage write failed');
      final provider = ClosetProvider(
        storage: storage,
        authSessionStorage: authStorage,
      );

      await expectLater(
        provider.setAuthenticatedUser(
          nickname: '홍길동',
          email: 'honggildong@example.com',
          accessToken: 'rollback-token',
          expiresInSeconds: 3600,
        ),
        throwsStateError,
      );

      expect(provider.isAuthenticated, isFalse);
      expect(provider.accessToken, isNull);
    });

    test('기기에서 직접 바꾼 닉네임은 서버 프로필 동기화가 덮어쓰지 않는다', () async {
      final storage = FakeClosetStorage();
      final authStorage = FakeAuthSessionStorage();
      final provider = ClosetProvider(
        storage: storage,
        authSessionStorage: authStorage,
      );

      await provider.setAuthenticatedUser(
        nickname: '홍길동',
        email: 'honggildong@example.com',
        accessToken: 'nickname-token',
        expiresInSeconds: 3600,
      );

      await provider.setUserName('길동이');

      // 스플래시의 세션 검증처럼 서버 닉네임으로 프로필을 다시 동기화합니다.
      await provider.setUserProfile(
        nickname: '홍길동',
        email: 'honggildong@example.com',
      );

      expect(provider.userName, '길동이');

      // 앱을 다시 시작해도 직접 수정 여부가 복원되어 유지됩니다.
      final restoredProvider = ClosetProvider(
        storage: storage,
        authSessionStorage: authStorage,
      );
      await restoredProvider.loadFromStorage();
      await restoredProvider.setUserProfile(
        nickname: '홍길동',
        email: 'honggildong@example.com',
      );

      expect(restoredProvider.userName, '길동이');
    });

    test('옷장 저장이 실패하면 추가한 의류를 목록에서 되돌린다', () async {
      final storage = FakeClosetStorage()
        ..saveClothesError = StateError('disk full');
      final provider = ClosetProvider(storage: storage);
      final clothes = Clothes(
        title: '홍길동 실패 테스트 셔츠',
        category: '상의',
        health: 90,
        materials: {'cotton': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 3.2,
      );

      await expectLater(provider.addClothes(clothes), throwsStateError);

      expect(provider.items, isEmpty);
      expect(provider.selectedClothes, isNull);
    });

    test('의류 수정 저장이 실패하면 이전 값으로 되돌린다', () async {
      final storage = FakeClosetStorage();
      final provider = ClosetProvider(storage: storage);
      final original = Clothes(
        title: '홍길동 원본 셔츠',
        category: '상의',
        health: 90,
        materials: {'cotton': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 4.0,
      );
      await provider.addClothes(original);

      storage.saveClothesError = StateError('disk full');
      final updated = original.copyWith(title: '홍길동 수정 셔츠');

      await expectLater(
        provider.updateClothes(original, updated),
        throwsStateError,
      );

      expect(provider.items.single.title, '홍길동 원본 셔츠');
    });

    test('latestItem은 목록 순서보다 등록 시각이 최신인 의류를 우선한다', () async {
      final provider = ClosetProvider(storage: FakeClosetStorage());
      final newer = Clothes(
        title: '홍길동 새 자켓',
        category: '상의',
        health: 95,
        materials: {'nylon': 100},
        careInstruction: '손세탁',
        carbonFootprint: 7.7,
        registeredAt: DateTime(2026, 8, 24, 12),
      );
      final older = Clothes(
        title: '홍길동 옛 자켓',
        category: '상의',
        health: 60,
        materials: {'wool': 100},
        careInstruction: '드라이클리닝',
        carbonFootprint: 6.6,
        registeredAt: DateTime(2026, 8, 20, 9),
      );

      // 목록에는 옛 의류가 뒤에 오지만, 등록 시각은 새 의류가 최신입니다.
      await provider.addClothes(newer);
      await provider.addClothes(older);
      provider.selectClothes(older);

      expect(provider.items.last, older);
      expect(provider.latestItem, newer);
    });

    test('서버 이력의 null 범위값도 그대로 반영해 동기화가 반복되지 않는다', () async {
      final provider = ClosetProvider(storage: FakeClosetStorage());
      final clothes = Clothes(
        title: '홍길동 동기화 셔츠',
        category: '상의',
        health: 85,
        materials: {'cotton': 100.0},
        careInstruction: '찬물 세탁',
        carbonFootprint: 12.0,
        carbonFootprintSource: CarbonFootprintSource.server,
        carbonFootprintMin: 11.0,
        carbonFootprintMax: 13.0,
        savedResultId: 42,
      );
      await provider.addClothes(clothes);

      // 서버 이력에는 범위값이 없는(단일값) 계산 결과가 내려온 상황입니다.
      const record = AnalysisHistoryRecord(
        id: 42,
        materials: {'cotton': 100.0},
        carbonFootprint: 9.9,
      );

      final firstSync = await provider.synchronizeServerHistory([record]);

      expect(firstSync, 1);
      expect(provider.items.single.carbonFootprint, 9.9);
      expect(provider.items.single.carbonFootprintMin, isNull);
      expect(provider.items.single.carbonFootprintMax, isNull);

      // 같은 이력을 다시 받아도 이미 일치하므로 갱신이 반복되지 않습니다.
      final secondSync = await provider.synchronizeServerHistory([record]);

      expect(secondSync, 0);
    });

    test('removeClothes는 같은 인스턴스가 없어도 저장 ID로 삭제하고 결과를 알려준다', () async {
      final provider = ClosetProvider(storage: FakeClosetStorage());
      final saved = Clothes(
        title: '홍길동 저장 셔츠',
        category: '상의',
        health: 90,
        materials: {'cotton': 100.0},
        careInstruction: '찬물 세탁',
        carbonFootprint: 5.0,
        savedResultId: 7,
      );
      await provider.addClothes(saved);

      // 서버 동기화 등으로 인스턴스가 바뀐 뒤의 오래된 참조를 흉내 냅니다.
      final staleReference = saved.copyWith(title: '홍길동 저장 셔츠(구 참조)');

      expect(await provider.removeClothes(staleReference), isTrue);
      expect(provider.items, isEmpty);

      // 이미 삭제된 대상은 false를 돌려주어 헛된 성공 안내를 막습니다.
      expect(await provider.removeClothes(staleReference), isFalse);
    });

    test('removeClothesBatch를 호출하면 여러 의류가 삭제된다', () async {
      final provider = ClosetProvider(storage: FakeClosetStorage());

      final newClothes1 = Clothes(
        title: '테스트 상의',
        category: '상의',
        health: 80,
        materials: {'cotton': 100},
        careInstruction: '손세탁',
        carbonFootprint: 8.1,
      );

      final newClothes2 = Clothes(
        title: '테스트 하의',
        category: '하의',
        health: 72,
        materials: {'denim': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 12.3,
      );

      await provider.addClothes(newClothes1);
      await provider.addClothes(newClothes2);

      final beforeCount = provider.count;
      await provider.removeClothesBatch([newClothes1, newClothes2]);

      expect(provider.count, beforeCount - 2);
    });

    test('updateClothes를 호출하면 기존 의류와 선택 상태를 함께 갱신한다', () async {
      final storage = FakeClosetStorage();
      final provider = ClosetProvider(storage: storage);
      final original = Clothes(
        title: '수정 전 셔츠',
        category: '상의',
        health: 80,
        materials: {'cotton': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 4.2,
      );

      await provider.addClothes(original);

      final updated = original.copyWith(
        title: '수정 후 셔츠',
        careInstruction: '찬물 손세탁',
      );

      final success = await provider.updateClothes(original, updated);

      expect(success, isTrue);
      expect(provider.items.single.title, '수정 후 셔츠');
      expect(provider.currentReportItem, updated);

      final savedItems = await storage.loadClothesList();

      expect(savedItems.single.title, '수정 후 셔츠');
      expect(savedItems.single.careInstruction, '찬물 손세탁');
    });

    test('로그인 사용자 프로필을 저장하고 다시 불러온다', () async {
      final storage = FakeClosetStorage();
      final authStorage = FakeAuthSessionStorage();
      final provider = ClosetProvider(
        storage: storage,
        authSessionStorage: authStorage,
      );

      await provider.setAuthenticatedUser(
        nickname: '홍길동',
        email: 'honggildong@example.com',
        accessToken: 'access-token',
        expiresInSeconds: 3600,
      );

      final restoredProvider = ClosetProvider(
        storage: storage,
        authSessionStorage: authStorage,
      );
      await restoredProvider.loadFromStorage();

      expect(restoredProvider.userName, '홍길동');
      expect(restoredProvider.userEmail, 'honggildong@example.com');
      expect(restoredProvider.accessToken, 'access-token');
      expect(restoredProvider.isAuthenticated, isTrue);
    });

    test('로그아웃하면 사용자 프로필을 기본값으로 되돌린다', () async {
      final authStorage = FakeAuthSessionStorage();
      final provider = ClosetProvider(
        storage: FakeClosetStorage(),
        authSessionStorage: authStorage,
      );

      await provider.setAuthenticatedUser(
        nickname: '홍길동',
        email: 'honggildong@example.com',
        accessToken: 'access-token',
        expiresInSeconds: 3600,
      );
      await provider.logout();

      expect(provider.userName, '홍길동');
      expect(provider.userEmail, 'honggildong@kdpp.com');
      expect(provider.accessToken, isNull);
      expect(provider.isAuthenticated, isFalse);
      expect(provider.items, isEmpty);
      expect(provider.selectedClothes, isNull);
      expect(authStorage.savedSession, isNull);
    });

    test('만료된 로그인 세션은 복원하지 않는다', () async {
      final authStorage = FakeAuthSessionStorage()
        ..savedSession = AuthSession(
          accessToken: 'expired-token',
          expiresAt: DateTime.now().subtract(const Duration(minutes: 1)),
        );
      final provider = ClosetProvider(
        storage: FakeClosetStorage(),
        authSessionStorage: authStorage,
      );

      await provider.loadFromStorage();

      expect(provider.accessToken, isNull);
      expect(provider.isAuthenticated, isFalse);
      expect(authStorage.savedSession, isNull);
    });

    test('인증 저장소를 읽지 못해도 나머지 로컬 데이터 로딩을 완료한다', () async {
      final storage = FakeClosetStorage();
      await storage.saveUserName('홍길동');
      await storage.saveUserEmail('honggildong@example.com');

      final originalDebugPrint = debugPrint;
      debugPrint = (String? message, {int? wrapWidth}) {};
      addTearDown(() {
        debugPrint = originalDebugPrint;
      });

      final authStorage = FakeAuthSessionStorage()
        ..loadError = StateError('secure storage unavailable');
      final provider = ClosetProvider(
        storage: storage,
        authSessionStorage: authStorage,
      );

      await provider.loadFromStorage();

      expect(provider.isLoaded, isTrue);
      expect(provider.userName, '홍길동');
      expect(provider.userEmail, 'honggildong@example.com');
      expect(provider.isAuthenticated, isFalse);
      expect(provider.accessToken, isNull);
    });

    test('서버 ID가 같은 의류의 계산 데이터만 동기화한다', () async {
      final storage = FakeClosetStorage();
      final authStorage = FakeAuthSessionStorage();
      final provider = ClosetProvider(
        storage: storage,
        authSessionStorage: authStorage,
      );
      final localClothes = Clothes(
        title: '홍길동 코튼 티셔츠',
        category: '상의',
        health: 88,
        materials: {'cotton': 80, 'polyester': 20},
        careInstruction: '찬물 세탁',
        carbonFootprint: 4.2,
        savedResultId: 13,
      );

      await provider.setAuthenticatedUser(
        nickname: '홍길동',
        email: 'honggildong@example.com',
        accessToken: 'access-token',
        expiresInSeconds: 3600,
      );
      await provider.clearAllClothes();
      await provider.addClothes(localClothes);

      final updatedCount = await provider.synchronizeServerHistory(const [
        AnalysisHistoryRecord(
          id: 13,
          materials: {'cotton': 100},
          carbonFootprint: 1.46,
          carbonFootprintMin: 0.83,
          carbonFootprintMax: 2.08,
          minWeightGram: 100,
          maxWeightGram: 250,
        ),
        AnalysisHistoryRecord(
          id: 99,
          materials: {'wool': 100},
          carbonFootprint: 8.0,
        ),
      ]);

      expect(updatedCount, 1);
      expect(provider.count, 1);

      final synchronized = provider.items.single;
      expect(synchronized.title, '홍길동 코튼 티셔츠');
      expect(synchronized.category, '상의');
      expect(synchronized.health, 88);
      expect(synchronized.careInstruction, '찬물 세탁');
      expect(synchronized.materials, {'cotton': 100});
      expect(synchronized.carbonFootprint, 1.46);
      expect(synchronized.carbonFootprintSource, CarbonFootprintSource.server);
      expect(synchronized.carbonFootprintMin, 0.83);
      expect(synchronized.carbonFootprintMax, 2.08);
      expect(synchronized.minWeightGram, 100);
      expect(synchronized.maxWeightGram, 250);
      expect(provider.selectedClothes, same(synchronized));

      final restoredProvider = ClosetProvider(
        storage: storage,
        authSessionStorage: authStorage,
      );
      await restoredProvider.loadFromStorage();
      expect(restoredProvider.items.single.carbonFootprint, 1.46);
      expect(restoredProvider.items.single.title, '홍길동 코튼 티셔츠');
    });
  });

  group('purgeAccountData', () {
    test('계정 전용 옷장과 세션을 함께 지운다', () async {
      final storage = FakeClosetStorage();
      final provider = ClosetProvider(
        storage: storage,
        authSessionStorage: FakeAuthSessionStorage(),
      );
      await provider.setAuthenticatedUser(
        nickname: '홍길동',
        email: 'honggildong@example.com',
        accessToken: 'access-token',
        expiresInSeconds: 3600,
      );
      await storage.saveClothesListFor('honggildong@example.com', const []);

      await provider.purgeAccountData();

      expect(provider.isAuthenticated, isFalse);
      expect(
        await storage.hasSavedClothesListFor('honggildong@example.com'),
        isFalse,
      );
    });

    test('옷장 삭제가 실패해도 세션은 반드시 정리하고 오류를 전달한다', () async {
      final storage = FakeClosetStorage();
      final provider = ClosetProvider(
        storage: storage,
        authSessionStorage: FakeAuthSessionStorage(),
      );
      await provider.setAuthenticatedUser(
        nickname: '홍길동',
        email: 'honggildong@example.com',
        accessToken: 'access-token',
        expiresInSeconds: 3600,
      );
      storage.clearClothesForError = Exception('저장소 오류');

      // 삭제된 계정의 토큰이 기기에 남으면 다음 실행에서 없는 계정으로 복원을 시도한다.
      await expectLater(provider.purgeAccountData(), throwsA(isA<Exception>()));

      expect(provider.isAuthenticated, isFalse);
      expect(provider.accessToken, isNull);
    });
  });

  group('정렬 기준 저장', () {
    test('기본값은 친환경 순이고 선택하면 저장소에 기록한다', () async {
      final storage = FakeClosetStorage();
      final provider = ClosetProvider(storage: storage);

      expect(provider.closetSortOption, ClosetSortOption.eco);

      await provider.setClosetSortOption(ClosetSortOption.custom);

      expect(provider.closetSortOption, ClosetSortOption.custom);
      expect(await storage.loadClosetSortOption(), ClosetSortOption.custom);
    });

    test('저장된 정렬 기준을 다음 실행에서 복원한다', () async {
      final storage = FakeClosetStorage();
      await storage.saveClosetSortOption(ClosetSortOption.latest);

      final provider = ClosetProvider(storage: storage);
      await provider.loadFromStorage();

      expect(provider.closetSortOption, ClosetSortOption.latest);
    });

    test('저장에 실패하면 이전 기준으로 되돌린다', () async {
      final storage = FakeClosetStorage();
      final provider = ClosetProvider(storage: storage);
      await provider.setClosetSortOption(ClosetSortOption.health);

      storage.saveSortOptionError = Exception('저장소 오류');

      // 되돌리지 않으면 화면과 다음 실행이 어긋난다.
      await expectLater(
        provider.setClosetSortOption(ClosetSortOption.custom),
        throwsA(isA<Exception>()),
      );
      expect(provider.closetSortOption, ClosetSortOption.health);
    });

    test('같은 기준을 다시 고르면 저장하지 않는다', () async {
      final storage = FakeClosetStorage();
      final provider = ClosetProvider(storage: storage);
      storage.saveSortOptionError = Exception('저장되면 안 된다');

      await provider.setClosetSortOption(ClosetSortOption.eco);

      expect(provider.closetSortOption, ClosetSortOption.eco);
    });
  });
}
