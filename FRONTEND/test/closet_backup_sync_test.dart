import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/models/analysis_history_record.dart';
import 'package:k_dpp/models/closet_backup_state.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/services/auth_session_storage_service.dart';
import 'package:k_dpp/services/closet_backup_api_service.dart';
import 'helpers/fake_auth_session_storage.dart';
import 'helpers/fake_closet_backup_api.dart';
import 'helpers/fake_closet_storage.dart';

/// 옷장 서버 백업(DECISIONS 242 — `BACKEND/API_CONTRACT.md` '앱 연동 메모(옷장 백업)')의 앱 몫을 시험한다.
void main() {
  const owner = 'user@example.com';

  Clothes clothes(String title, {DateTime? at, int? savedResultId}) {
    return Clothes(
      title: title,
      category: '상의',
      health: 80,
      materials: const {'cotton': 100.0},
      careInstruction: '찬물 세탁',
      carbonFootprint: 1.5,
      registeredAt: at,
      savedResultId: savedResultId,
    );
  }

  final x = clothes('기기 셔츠', at: DateTime(2026, 10, 1, 9));
  final y = clothes('서버 바지', at: DateTime(2026, 10, 2, 9));
  final z = clothes('다른 폰 코트', at: DateTime(2026, 10, 3, 9));

  Map<String, dynamic> json(Clothes item) => item.toJson();

  ClosetBackupState validState(
    FakeClosetBackupApi api,
    List<Clothes> items, {
    // 가짜 서버의 처음 판(0)과 같게 둡니다 — 다르면 첫 올리기가 409 를 받아 한 번 더 보낸다.
    int version = 0,
    int userId = 1,
  }) {
    return ClosetBackupState(
      userId: userId,
      apiBaseUrl: api.baseUrl,
      version: version,
      fingerprint: closetFingerprint(items),
    );
  }

  Future<ClosetProvider> signIn(
    FakeClosetStorage storage,
    FakeClosetBackupApi api, {
    int userId = 1,
    String token = 'token-1',
    Duration delay = Duration.zero,
    Duration retryInterval = const Duration(seconds: 30),
    DateTime Function()? now,
  }) async {
    final provider = ClosetProvider(
      storage: storage,
      authSessionStorage: FakeAuthSessionStorage(),
      backupApi: api,
      backupUploadDelay: delay,
      firstSyncRetryInterval: retryInterval,
      now: now,
    );
    await provider.setAuthenticatedUser(
      nickname: '테스터',
      email: owner,
      userId: userId,
      accessToken: token,
      expiresInSeconds: 3600,
    );
    return provider;
  }

  Future<void> settle() => pumpEventQueue(times: 50);

  List<String> titles(ClosetProvider provider) =>
      provider.items.map((item) => item.title).toList();

  group('첫 맞춤', () {
    test('맞춘 적 없는 빈 기기는 서버 옷을 모두 되살리고, 서버와 같으니 올리지 않는다', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi()
        ..putServerBackup([json(x), json(y)], version: 3);
      final provider = await signIn(storage, api);
      final restored = <int>[];
      provider.closetRestores.listen(restored.add);

      final count = await provider.syncClosetBackup();
      await settle();

      expect(count, 2);
      expect(restored, [2]);
      expect(titles(provider), [x.title, y.title]);
      expect(
        (await storage.loadClothesListFor(owner)).map((item) => item.title),
        [x.title, y.title],
      );
      final state = storage.backupStateFor(owner)!;
      expect(state.userId, 1);
      expect(state.apiBaseUrl, api.baseUrl);
      expect(state.version, 3);
      expect(state.fingerprint, closetFingerprint([x, y]));
      expect(api.uploads, isEmpty);
    });

    test('기기 옷 + 짝 없는 서버 옷으로 합치고, 올리기 전에 서버 판 상태를 먼저 남긴다', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi()..putServerBackup([json(y)], version: 2);
      final provider = await signIn(storage, api);
      await provider.addClothes(x);
      await settle();
      expect(api.uploads, isEmpty, reason: '맞춘 적 없는 기기는 받기 전에 올리지 않는다');

      final hold = Completer<void>();
      api.holdNextUpload = hold;
      final count = await provider.syncClosetBackup();
      await settle();

      expect(count, 1);
      expect(titles(provider), [x.title, y.title]);
      // 올리는 중에도 상태는 이미 서버 판(v2)이다 — 올리기가 실패해도 다음 실행에서 다시 합치지 않게.
      expect(api.uploads.single.baseVersion, 2);
      expect(api.uploads.single.titles, [x.title, y.title]);
      expect(storage.backupStateFor(owner)!.version, 2);
      expect(
        storage.backupStateFor(owner)!.fingerprint,
        closetFingerprint([y]),
      );

      hold.complete();
      await settle();
      expect(storage.backupStateFor(owner)!.version, 3);
    });

    test('합친 뒤 올리기가 끝나면 상태는 응답 판·보낸 지문이고, 두 번 돌려도 같다', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi()..putServerBackup([json(y)], version: 2);
      final provider = await signIn(storage, api);
      await provider.addClothes(x);

      await provider.syncClosetBackup();
      await settle();

      expect(api.serverVersion, 3);
      expect(storage.backupStateFor(owner)!.version, 3);
      expect(
        storage.backupStateFor(owner)!.fingerprint,
        closetFingerprint([x, y]),
      );

      api.fetchTokens.clear();
      api.uploads.clear();
      expect(await provider.syncClosetBackup(), 0);
      await settle();
      expect(api.fetchTokens, isEmpty);
      expect(api.uploads, isEmpty);
      expect(titles(provider), [x.title, y.title]);
    });

    test('짝 규칙 — 등록 시각과 저장 id 가 같을 때만 같은 옷이고, 한 벌은 한 번만 짝이 된다', () async {
      final at = DateTime(2026, 10, 5, 9);
      final local = [
        clothes('제목 고친 셔츠', at: at, savedResultId: 7),
        clothes('같은 id 다른 시각', at: DateTime(2026, 10, 6), savedResultId: 8),
        clothes('같은 시각 다른 id', at: at, savedResultId: 9),
        clothes('시각 없는 옷'),
        clothes('시각 없는 옷'),
      ];
      final server = [
        clothes('서버 쪽 옛 제목', at: at, savedResultId: 7),
        clothes('같은 id 다른 시각', at: DateTime(2026, 10, 7), savedResultId: 8),
        clothes('같은 시각 다른 id', at: at, savedResultId: 10),
        clothes('시각 없는 옷'),
        clothes('시각 없는 옷'),
        clothes('시각 없는 옷'),
        clothes('시각만 있는 옷', at: DateTime(2026, 10, 8)),
      ];
      final storage = FakeClosetStorage();
      await storage.saveClothesListFor(owner, local);
      final api = FakeClosetBackupApi()
        ..putServerBackup(server.map(json).toList());
      final provider = await signIn(storage, api);

      final count = await provider.syncClosetBackup();

      expect(count, 4);
      expect(titles(provider), [
        '제목 고친 셔츠',
        '같은 id 다른 시각',
        '같은 시각 다른 id',
        '시각 없는 옷',
        '시각 없는 옷',
        '같은 id 다른 시각',
        '같은 시각 다른 id',
        '시각 없는 옷',
        '시각만 있는 옷',
      ]);
    });

    test('서버 응답의 사용자 id 가 지금 계정과 다르면 합치지도 상태를 남기지도 않는다', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi(serverUserId: 2)
        ..putServerBackup([json(y)]);
      final provider = await signIn(storage, api);

      expect(await provider.syncClosetBackup(), 0);
      expect(provider.items, isEmpty);
      expect(storage.backupStateFor(owner), isNull);
    });

    test('서버 옷 하나라도 옷 객체가 아니면 합치지도 올리지도 상태를 남기지도 않는다', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi();
      api.fetchResults.add(
        ClosetBackupFetched(userId: 1, version: 4, items: [json(y), '깨진 값']),
      );
      final provider = await signIn(storage, api);
      await provider.addClothes(x);

      expect(await provider.syncClosetBackup(), 0);
      await settle();

      expect(titles(provider), [x.title]);
      expect(storage.backupStateFor(owner), isNull);
      expect(api.uploads, isEmpty);
    });

    test('받은 옷 저장이 실패하면 되돌리고 상태를 남기지 않는다', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi()..putServerBackup([json(y)]);
      final provider = await signIn(storage, api);
      storage.saveClothesError = StateError('disk full');

      expect(await provider.syncClosetBackup(), 0);

      expect(provider.items, isEmpty);
      expect(storage.backupStateFor(owner), isNull);
    });
  });

  group('첫 맞춤 뒤 올리기 실패', () {
    test('올리기가 못 닿아도 상태는 남아, 같은 실행에서 지운 서버 옷이 다음 실행에 돌아오지 않는다', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi()..putServerBackup([json(y)], version: 2);
      final first = await signIn(storage, api);
      await first.addClothes(x);
      api.uploadResults.add(
        const ClosetBackupUploadFailed(ClosetBackupFailure.unavailable),
      );

      await first.syncClosetBackup();
      await settle();
      expect(storage.backupStateFor(owner)!.version, 2);

      // 같은 실행에서 서버에서 온 옷을 지운다 — 이 올리기도 못 닿았다고 치자.
      api.uploadResults.add(
        const ClosetBackupUploadFailed(ClosetBackupFailure.unavailable),
      );
      await first.removeClothes(first.items.last);
      await settle();

      // 다음 실행: 받지 않고 지문 차이로 올린다.
      api.fetchTokens.clear();
      api.uploads.clear();
      final second = await signIn(storage, api);
      await second.syncClosetBackup();
      await settle();

      expect(api.fetchTokens, isEmpty);
      expect(titles(second), [x.title]);
      expect(api.uploads.single.titles, [x.title]);
      expect(api.serverItems.map((item) => item['title']), [x.title]);
    });

    test('413 이 계속 나도 다음 실행에서 받기·합치기를 되풀이하지 않는다', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi()..putServerBackup([json(y)], version: 2);
      final first = await signIn(storage, api);
      await first.addClothes(x);
      api.uploadResults.add(
        const ClosetBackupUploadFailed(ClosetBackupFailure.rejected),
      );

      await first.syncClosetBackup();
      await settle();

      api.fetchTokens.clear();
      api.uploads.clear();
      api.uploadResults.add(
        const ClosetBackupUploadFailed(ClosetBackupFailure.rejected),
      );
      final second = await signIn(storage, api);
      expect(await second.syncClosetBackup(), 0);
      await settle();

      expect(api.fetchTokens, isEmpty);
      expect(api.uploads, hasLength(1));
      expect(titles(second), [x.title, y.title]);
    });

    test('첫 맞춤 직후 기기 변경 없이 409 면 덮지 않고 한 번 더 받아 다른 폰 옷을 넣는다', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi()..putServerBackup([json(y)], version: 2);
      final provider = await signIn(storage, api);
      await provider.addClothes(x);
      // 첫 올리기는 다른 폰이 먼저 바꾼 뒤라 409 를 받는다.
      api.uploadResults.add(const ClosetBackupConflict(3));
      api.fetchResults.addAll([
        ClosetBackupFetched(userId: 1, version: 2, items: [json(y)]),
        ClosetBackupFetched(userId: 1, version: 3, items: [json(y), json(z)]),
      ]);
      api.putServerBackup([json(y), json(z)], version: 3);

      await provider.syncClosetBackup();
      await settle();

      expect(api.fetchTokens, hasLength(2));
      expect(titles(provider), [x.title, y.title, z.title]);
      expect(api.uploads.last.baseVersion, 3);
      expect(api.uploads.last.titles, [x.title, y.title, z.title]);
      expect(storage.backupStateFor(owner)!.version, 4);
    });

    test('첫 맞춤 뒤 기기를 바꾼 다음 409 면 폰 우선으로 지금 판 위에 다시 보낸다', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi()..putServerBackup([json(y)], version: 2);
      final provider = await signIn(
        storage,
        api,
        delay: const Duration(milliseconds: 20),
      );
      await provider.addClothes(x);

      await provider.syncClosetBackup();
      // 올리기 전에 기기를 바꾼다.
      await provider.addClothes(z);
      api.putServerBackup([json(y), json(clothes('다른 폰'))], version: 3);
      await Future<void>.delayed(const Duration(milliseconds: 80));
      await settle();

      expect(api.fetchTokens, hasLength(1));
      expect(api.uploads.map((upload) => upload.baseVersion), [2, 3]);
      expect(api.serverItems.map((item) => item['title']), [
        x.title,
        y.title,
        z.title,
      ]);
      expect(storage.backupStateFor(owner)!.version, 4);
    });
  });

  group('받기 실패', () {
    test('받기가 못 닿으면 상태도 올리기도 없고 로그아웃하지 않으며, 옷장이 바뀌면 간격을 두고 다시 받는다', () async {
      var clock = DateTime(2026, 10, 18, 12);
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi()..putServerBackup([json(y)]);
      api.fetchResults.add(
        const ClosetBackupFetchFailed(ClosetBackupFailure.unavailable),
      );
      final provider = await signIn(storage, api, now: () => clock);

      expect(await provider.syncClosetBackup(), 0);
      expect(storage.backupStateFor(owner), isNull);
      expect(provider.isAuthenticated, isTrue);

      // 30초가 안 지났으면 바로 다시 묻지 않는다.
      clock = clock.add(const Duration(seconds: 5));
      await provider.addClothes(x);
      await settle();
      expect(api.fetchTokens, hasLength(1));
      expect(api.uploads, isEmpty);

      // 30초가 지나 다시 바뀌면 받아 합치고 올린다.
      clock = clock.add(const Duration(seconds: 30));
      await provider.addClothes(z);
      await settle();
      expect(api.fetchTokens, hasLength(2));
      expect(titles(provider), [x.title, z.title, y.title]);
      expect(api.uploads.single.titles, [x.title, z.title, y.title]);
    });

    test('받기가 401 이면 같은 토큰으로는 이번 실행에 다시 묻지 않는다', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi();
      api.fetchResults.add(
        const ClosetBackupFetchFailed(ClosetBackupFailure.unauthorized),
      );
      final provider = await signIn(storage, api);

      await provider.syncClosetBackup();
      await provider.syncClosetBackup();
      await provider.addClothes(x);
      await settle();

      expect(api.fetchTokens, hasLength(1));
      expect(api.uploads, isEmpty);
      expect(provider.isAuthenticated, isTrue);
    });
  });

  group('맞춘 기기의 올리기', () {
    test('맞춘 상태이고 지문이 같으면 켜기만 해서는 받지도 올리지도 않는다', () async {
      final storage = FakeClosetStorage();
      await storage.saveClothesListFor(owner, [x]);
      final api = FakeClosetBackupApi()..putServerBackup([json(y)], version: 5);
      storage.putBackupState(owner, validState(api, [x], version: 4));
      final provider = await signIn(storage, api);

      expect(await provider.syncClosetBackup(), 0);
      await settle();

      expect(api.fetchTokens, isEmpty);
      expect(api.uploads, isEmpty);
      expect(api.serverItems.single['title'], y.title);
    });

    test('짧은 틈의 변경 셋은 한 번에 올리고, 409 면 지금 판 위에 한 번 더 보낸다', () async {
      final storage = FakeClosetStorage();
      await storage.saveClothesListFor(owner, const []);
      final api = FakeClosetBackupApi()..putServerBackup([], version: 6);
      storage.putBackupState(owner, validState(api, const [], version: 6));
      api.uploadResults.add(const ClosetBackupConflict(7));
      api.serverVersion = 7;
      final provider = await signIn(
        storage,
        api,
        delay: const Duration(milliseconds: 30),
      );

      await provider.addClothes(x);
      await provider.addClothes(y);
      await provider.addClothes(z);
      await Future<void>.delayed(const Duration(milliseconds: 100));
      await settle();

      expect(api.uploads.map((upload) => upload.baseVersion), [6, 7]);
      expect(api.uploads.last.titles, [x.title, y.title, z.title]);
      expect(storage.backupStateFor(owner)!.version, 8);
    });

    test('다시 보낸 것도 409 면 그만두고, 다음 변경 때 다시 보낸다', () async {
      final storage = FakeClosetStorage();
      await storage.saveClothesListFor(owner, const []);
      final api = FakeClosetBackupApi();
      storage.putBackupState(owner, validState(api, const [], version: 1));
      api.uploadResults.addAll(const [
        ClosetBackupConflict(2),
        ClosetBackupConflict(3),
      ]);
      api.serverVersion = 3;
      final provider = await signIn(storage, api);

      await provider.addClothes(x);
      await settle();
      expect(api.uploads, hasLength(2));
      expect(storage.backupStateFor(owner)!.version, 1);

      // 다음 변경은 다시 보낸다 — 이번엔 409(3) 뒤 판 3 위에 다시 보내 받아들여진다.
      await provider.addClothes(y);
      await settle();
      expect(api.uploads.map((upload) => upload.baseVersion), [1, 2, 1, 3]);
      expect(storage.backupStateFor(owner)!.version, 4);
    });

    test('저장 실패로 되돌린 변경은 지문이 같아 올리지 않는다', () async {
      final storage = FakeClosetStorage();
      await storage.saveClothesListFor(owner, [x]);
      final api = FakeClosetBackupApi();
      storage.putBackupState(owner, validState(api, [x]));
      final provider = await signIn(storage, api);
      storage.saveClothesError = StateError('disk full');

      await expectLater(provider.addClothes(y), throwsStateError);
      provider.scheduleClosetBackup();
      await settle();

      expect(api.uploads, isEmpty);
    });

    test('백업 없는 빌드가 바꾼 옷장은 다음 실행에서 지문 차이로 올린다', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi();
      storage.putBackupState(owner, validState(api, [x]));
      // 백업 상태는 [x] 인데 기기 옷장은 그 뒤 다른 빌드가 [x, y] 로 바꿨다.
      await storage.saveClothesListFor(owner, [x, y]);
      final provider = await signIn(storage, api);

      await provider.syncClosetBackup();
      await settle();

      expect(api.fetchTokens, isEmpty);
      expect(api.uploads.single.titles, [x.title, y.title]);
    });

    test('올리기 401 은 로그아웃하지 않고, 403 주인 불일치는 이번만 버리고 다음 변경에 다시 보낸다', () async {
      final storage = FakeClosetStorage();
      await storage.saveClothesListFor(owner, const []);
      final api = FakeClosetBackupApi();
      storage.putBackupState(owner, validState(api, const []));
      api.uploadResults.add(
        const ClosetBackupUploadFailed(ClosetBackupFailure.ownerMismatch),
      );
      final provider = await signIn(storage, api);

      await provider.addClothes(x);
      await settle();
      expect(storage.backupStateFor(owner)!.fingerprint, closetFingerprint([]));

      await provider.addClothes(y);
      await settle();
      expect(api.uploads, hasLength(2));
      expect(
        storage.backupStateFor(owner)!.fingerprint,
        closetFingerprint([x, y]),
      );

      api.uploadResults.add(
        const ClosetBackupUploadFailed(ClosetBackupFailure.unauthorized),
      );
      await provider.addClothes(z);
      await settle();
      expect(provider.isAuthenticated, isTrue);

      // 같은 토큰으로는 더 보내지 않는다(지문은 또 달라졌어도).
      await provider.addClothes(clothes('401 뒤에 넣은 옷'));
      await settle();
      expect(api.uploads, hasLength(3));
    });

    for (final failure in ['413', '422', '모르는 409']) {
      test('거절($failure)을 받으면 이번 실행 동안 이 계정은 더 보내지 않는다', () async {
        final storage = FakeClosetStorage();
        await storage.saveClothesListFor(owner, const []);
        final api = FakeClosetBackupApi();
        storage.putBackupState(owner, validState(api, const []));
        api.uploadResults.add(
          const ClosetBackupUploadFailed(ClosetBackupFailure.rejected),
        );
        final provider = await signIn(storage, api);

        await provider.addClothes(x);
        await settle();
        await provider.addClothes(y);
        await settle();

        expect(api.uploads, hasLength(1));
      });
    }

    test('올리는 중에 바뀐 옷장은 끝난 뒤 한 번 더 올린다', () async {
      final storage = FakeClosetStorage();
      await storage.saveClothesListFor(owner, const []);
      final api = FakeClosetBackupApi();
      storage.putBackupState(owner, validState(api, const []));
      final provider = await signIn(storage, api);
      final hold = Completer<void>();
      api.holdNextUpload = hold;

      await provider.addClothes(x);
      await settle();
      await provider.addClothes(y);
      await settle();
      expect(api.uploads, hasLength(1), reason: '동시에 하나만 보낸다');

      hold.complete();
      await settle();

      expect(api.uploads.map((upload) => upload.titles), [
        [x.title],
        [x.title, y.title],
      ]);
      expect(
        storage.backupStateFor(owner)!.fingerprint,
        closetFingerprint([x, y]),
      );
    });

    test('올리는 중에 로그아웃해도 받은 판은 보낼 때의 주인 상태에 남는다', () async {
      final storage = FakeClosetStorage();
      await storage.saveClothesListFor(owner, const []);
      final api = FakeClosetBackupApi();
      storage.putBackupState(owner, validState(api, const []));
      final provider = await signIn(storage, api);
      final hold = Completer<void>();
      api.holdNextUpload = hold;

      await provider.addClothes(x);
      await settle();
      await provider.logout();
      hold.complete();
      await settle();

      expect(storage.backupStateFor(owner)!.version, 1);
      expect(
        storage.backupStateFor(owner)!.fingerprint,
        closetFingerprint([x]),
      );
    });

    test('스플래시가 기다리는 동안 올리기는 끼어들지 않는다', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi()..putServerBackup([json(y)]);
      final provider = await signIn(storage, api);
      await provider.addClothes(x);
      final hold = Completer<void>();
      api.holdNextUpload = hold;

      // 올리기가 붙잡혀 있어도 syncClosetBackup 은 먼저 끝난다.
      final count = await provider.syncClosetBackup().timeout(
        const Duration(seconds: 1),
      );
      expect(count, 1);
      hold.complete();
      await settle();
    });
  });

  group('맞춘 상태를 믿지 않는 경우', () {
    test('계정 옷장 키가 없어 빈 옷장을 만들면 그 주인 상태를 지운다', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi()..putServerBackup([json(y)]);
      storage.putBackupState(owner, validState(api, const []));

      final provider = await signIn(storage, api);
      expect(storage.backupStateFor(owner), isNull);

      expect(await provider.syncClosetBackup(), 1);
      expect(titles(provider), [y.title]);
    });

    test('망가진 계정 옷장을 불러오면 상태를 지워 다음 동기화가 합치기가 된다', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi()..putServerBackup([json(y)]);
      storage.markClosetCorrupt(owner, items: [x]);
      storage.putBackupState(owner, validState(api, [x]));

      final provider = await signIn(storage, api);
      expect(storage.backupStateFor(owner), isNull);

      expect(await provider.syncClosetBackup(), 1);
      expect(titles(provider), [x.title, y.title]);
    });

    test('다른 주인 옷장에 늦게 넣을 때 그 값이 망가져 있으면 그 주인 상태를 지운다', () async {
      const other = 'other@example.com';
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi();
      storage.markClosetCorrupt(other, items: [x]);
      storage.putBackupState(other, validState(api, [x]));
      final provider = await signIn(storage, api);

      expect(await provider.addClothesForOwner(other, y), isFalse);

      expect(storage.backupStateFor(other), isNull);
      expect(
        (await storage.loadClothesListFor(other)).map((item) => item.title),
        [x.title, y.title],
      );
    });

    test('상태의 사용자 id 나 서버 주소가 다르면 첫 맞춤으로 간다', () async {
      for (final state in [
        ClosetBackupState(
          userId: 9,
          apiBaseUrl: 'https://api.test',
          version: 1,
          fingerprint: closetFingerprint([x]),
        ),
        ClosetBackupState(
          userId: 1,
          apiBaseUrl: 'http://192.168.0.2:8000',
          version: 1,
          fingerprint: closetFingerprint([x]),
        ),
      ]) {
        final storage = FakeClosetStorage();
        await storage.saveClothesListFor(owner, [x]);
        storage.putBackupState(owner, state);
        final api = FakeClosetBackupApi()..putServerBackup([json(y)]);
        final provider = await signIn(storage, api);

        expect(await provider.syncClosetBackup(), 1);
        expect(api.fetchTokens, hasLength(1));
      }
    });
  });

  group('계정 정리', () {
    test('탈퇴 정리는 상태를 지우고 로그아웃은 남긴다', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi()..putServerBackup([json(y)]);
      final provider = await signIn(storage, api);
      await provider.syncClosetBackup();
      await settle();

      await provider.logout();
      expect(storage.backupStateFor(owner), isNotNull);

      final again = await signIn(storage, api);
      await again.purgeAccountData();
      expect(storage.backupStateFor(owner), isNull);
    });

    test('세션은 있는데 옷장 주인이 없으면 저장을 거부하고 공용 옷장에도 쓰지 않는다', () async {
      final storage = FakeClosetStorage();
      final sessionStorage = FakeAuthSessionStorage()
        ..savedSession = AuthSession(
          accessToken: 'token-1',
          expiresAt: DateTime.now().add(const Duration(hours: 1)),
        );
      final provider = ClosetProvider(
        storage: storage,
        authSessionStorage: sessionStorage,
        backupApi: FakeClosetBackupApi(),
      );
      await provider.loadFromStorage();
      expect(provider.isAuthenticated, isTrue);
      expect(provider.closetOwnerKey, isNull);

      await expectLater(provider.addClothes(x), throwsStateError);

      expect(provider.items, isEmpty);
      expect(await storage.loadClothesListOrNull(), isNull);
    });
  });

  // 적대적 검증(10-18)이 실행으로 재현한 경로들이다.
  group('경합', () {
    test('409 뒤 다시 받는 사이 기기에서 지운 옷은 되살리지 않고 폰 우선으로 올린다', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi()
        ..putServerBackup([json(y), json(z)], version: 3);
      api.uploadResults.add(const ClosetBackupConflict(3));
      api.fetchResults.add(
        ClosetBackupFetched(userId: 1, version: 2, items: [json(y)]),
      );
      final provider = await signIn(storage, api);
      await provider.addClothes(x);

      await provider.syncClosetBackup();
      final hold = Completer<void>();
      api.holdNextFetch = hold;
      await settle();
      expect(api.fetchTokens, hasLength(2), reason: '409 뒤 다시 받는 중');

      // 맞춘 기기에서 서버에서 온 y 를 지운다.
      await provider.removeClothes(provider.items.last);
      hold.complete();
      await settle();

      expect(titles(provider), [x.title]);
      expect(api.serverItems.map((item) => item['title']), [x.title]);
      expect(storage.backupStateFor(owner)!.version, api.serverVersion);
    });

    test('탈퇴 정리 도중 끝난 받기는 지운 옷장·상태를 되살리지 않는다', () async {
      final storage = _HookedClosetStorage();
      final api = FakeClosetBackupApi()..putServerBackup([json(y)]);
      final provider = await signIn(storage, api);
      await provider.addClothes(x);
      final hold = Completer<void>();
      api.holdNextFetch = hold;
      final restored = <int>[];
      provider.closetRestores.listen(restored.add);

      final syncing = provider.syncClosetBackup();
      await settle();
      // 옷장 키를 지운 직후, 상태를 지우고 로그아웃하기 전에 받기가 끝난다.
      storage.afterClearClothesFor = () async {
        hold.complete();
        await settle();
      };
      await provider.purgeAccountData();

      expect(await syncing, 0);
      expect(await storage.loadClothesListOrNullFor(owner), isNull);
      expect(storage.backupStateFor(owner), isNull);
      expect(restored, isEmpty);
    });

    test('A 의 첫 맞춤이 걸린 사이 B 로 로그인해도 B 는 서버 백업과 맞춘다', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi()..putServerBackup([json(y)]);
      final provider = await signIn(storage, api);
      final hold = Completer<void>();
      api.holdNextFetch = hold;
      final syncingA = provider.syncClosetBackup();
      await settle();

      await provider.logout();
      await provider.setAuthenticatedUser(
        nickname: 'B',
        email: 'b@example.com',
        userId: 1,
        accessToken: 'token-b',
        expiresInSeconds: 3600,
      );

      expect(await provider.syncClosetBackup(), 1);
      expect(api.fetchTokens, ['token-1', 'token-b']);
      expect(storage.backupStateFor('b@example.com'), isNotNull);

      hold.complete();
      expect(await syncingA, 0);
    });

    test('첫 맞춤 바로 뒤 이력 동기화가 고친 것은 기기 변경으로 세지 않아, 409 면 다시 받아 합친다', () async {
      final local = clothes(
        '기기 셔츠',
        at: DateTime(2026, 10, 1),
        savedResultId: 5,
      );
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi()
        ..putServerBackup([json(y), json(z)], version: 3);
      api.uploadResults.add(const ClosetBackupConflict(3));
      api.fetchResults.add(
        ClosetBackupFetched(userId: 1, version: 2, items: [json(y)]),
      );
      final provider = await signIn(
        storage,
        api,
        delay: const Duration(milliseconds: 20),
      );
      await provider.addClothes(local);

      await provider.syncClosetBackup();
      expect(
        await provider.synchronizeServerHistory(const [
          AnalysisHistoryRecord(
            id: 5,
            materials: {'cotton': 100},
            carbonFootprint: 2.0,
            carbonFootprintMin: 1.0,
            carbonFootprintMax: 3.0,
            minWeightGram: 100,
            maxWeightGram: 250,
          ),
        ]),
        1,
      );
      await Future<void>.delayed(const Duration(milliseconds: 80));
      await settle();

      expect(api.fetchTokens, hasLength(2));
      expect(titles(provider), [local.title, y.title, z.title]);
      expect(api.serverItems.map((item) => item['title']), [
        local.title,
        y.title,
        z.title,
      ]);
    });

    test('탈퇴 대화상자를 열었다 닫아도 걸려 있던 첫 맞춤 다시 시도는 남는다', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi()..putServerBackup([json(y)]);
      api.fetchResults.add(
        const ClosetBackupFetchFailed(ClosetBackupFailure.unavailable),
      );
      final provider = await signIn(storage, api, retryInterval: Duration.zero);
      await provider.syncClosetBackup();

      await provider.addClothes(x);
      provider.cancelScheduledClosetBackup();
      provider.scheduleClosetBackup();
      await settle();

      expect(api.fetchTokens, hasLength(2));
      expect(titles(provider), [x.title, y.title]);
    });

    test('409 뒤 다시 받기가 못 닿아도 다음 변경은 바로 올린다(첫 맞춤 간격을 쓰지 않음)', () async {
      final storage = FakeClosetStorage();
      final api = FakeClosetBackupApi()..putServerBackup([json(y)], version: 2);
      api.uploadResults.add(const ClosetBackupConflict(2));
      api.fetchResults.addAll([
        ClosetBackupFetched(userId: 1, version: 2, items: [json(y)]),
        const ClosetBackupFetchFailed(ClosetBackupFailure.unavailable),
      ]);
      final provider = await signIn(
        storage,
        api,
        retryInterval: const Duration(hours: 1),
      );
      await provider.addClothes(x);
      await provider.syncClosetBackup();
      await settle();
      expect(api.uploads, hasLength(1));

      await provider.addClothes(z);
      await settle();

      expect(api.uploads, hasLength(2));
      expect(api.serverItems.map((item) => item['title']), [
        x.title,
        y.title,
        z.title,
      ]);
    });

    test('탈퇴 전에 예약을 거두면 올리는 중 대기하던 다시 올리기도 거둔다', () async {
      final storage = FakeClosetStorage();
      await storage.saveClothesListFor(owner, const []);
      final api = FakeClosetBackupApi();
      storage.putBackupState(owner, validState(api, const []));
      final provider = await signIn(storage, api);
      final hold = Completer<void>();
      api.holdNextUpload = hold;

      await provider.addClothes(x);
      await settle();
      await provider.addClothes(y);
      await settle();
      provider.cancelScheduledClosetBackup();
      hold.complete();
      await settle();

      expect(api.uploads, hasLength(1));
    });

    test('A 옷장 저장을 기다리는 사이 B 로 바뀌면 되살림 알림을 B 화면에 띄우지 않는다', () async {
      final storage = _HookedClosetStorage();
      final api = FakeClosetBackupApi()..putServerBackup([json(y)]);
      final provider = await signIn(storage, api);
      final restored = <int>[];
      provider.closetRestores.listen(restored.add);
      final gate = Completer<void>();
      storage.gateSaveFor = (owner, gate);

      final syncing = provider.syncClosetBackup();
      await settle();
      await provider.logout();
      await provider.setAuthenticatedUser(
        nickname: 'B',
        email: 'b@example.com',
        userId: 2,
        accessToken: 'token-b',
        expiresInSeconds: 3600,
      );
      gate.complete();
      await syncing;
      await settle();

      expect(restored, isEmpty);
    });
  });
}

/// 계정 옷장 지우기 뒤에 끼어들거나, 한 주인의 옷장 저장을 붙잡을 수 있는 저장소입니다.
class _HookedClosetStorage extends FakeClosetStorage {
  Future<void> Function()? afterClearClothesFor;
  (String, Completer<void>)? gateSaveFor;

  @override
  Future<void> clearClothesListFor(String ownerKey) async {
    await super.clearClothesListFor(ownerKey);
    final hook = afterClearClothesFor;
    afterClearClothesFor = null;
    if (hook != null) await hook();
  }

  @override
  Future<void> saveClothesListFor(String ownerKey, List<Clothes> items) async {
    final gate = gateSaveFor;
    if (gate != null && gate.$1 == ownerKey) {
      gateSaveFor = null;
      await gate.$2.future;
    }
    await super.saveClothesListFor(ownerKey, items);
  }
}
