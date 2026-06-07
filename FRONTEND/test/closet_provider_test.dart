import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/models/analysis_history_record.dart';
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
}
