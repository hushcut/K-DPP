import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/models/analysis_history_record.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/services/auth_api_service.dart';
import 'package:k_dpp/services/post_login_sync_service.dart';

import 'helpers/fake_auth_session_storage.dart';
import 'helpers/fake_closet_storage.dart';

void main() {
  test('로그인 직후 서버 프로필과 기존 의류 계산값을 동기화한다', () async {
    final provider = ClosetProvider(
      storage: FakeClosetStorage(),
      authSessionStorage: FakeAuthSessionStorage(),
    );
    final localClothes = Clothes(
      title: '홍길동 코튼 셔츠',
      category: '상의',
      health: 85,
      materials: {'cotton': 80, 'polyester': 20},
      careInstruction: '찬물 세탁',
      carbonFootprint: 4.8,
      savedResultId: 13,
    );

    await provider.setAuthenticatedUser(
      nickname: '이전 닉네임',
      email: 'honggildong@example.com',
      accessToken: 'valid-token',
      expiresInSeconds: 3600,
    );
    await provider.addClothes(localClothes);

    final service = PostLoginSyncService(
      authApiService: _FakeAuthApiService(
        snapshot: const AuthSessionSnapshot(
          user: AuthUser(
            id: 7,
            email: 'honggildong@example.com',
            nickname: '홍길동',
          ),
          history: [
            AnalysisHistoryRecord(
              id: 13,
              materials: {'cotton': 100},
              carbonFootprint: 1.46,
              carbonFootprintMin: 0.83,
              carbonFootprintMax: 2.08,
              minWeightGram: 100,
              maxWeightGram: 250,
            ),
          ],
        ),
      ),
    );

    await service.synchronize(provider: provider, accessToken: 'valid-token');

    expect(provider.userName, '홍길동');
    expect(provider.items.single.carbonFootprint, 1.46);
    expect(
      provider.items.single.carbonFootprintSource,
      CarbonFootprintSource.server,
    );
  });

  test('서버 연결 실패 시 로그인 세션과 로컬 옷장을 유지한다', () async {
    final provider = ClosetProvider(
      storage: FakeClosetStorage(),
      authSessionStorage: FakeAuthSessionStorage(),
    );
    final localClothes = Clothes(
      title: '홍길동 리넨 셔츠',
      category: '상의',
      health: 90,
      materials: {'linen': 100},
      careInstruction: '찬물 손세탁',
      carbonFootprint: 4.2,
    );

    await provider.setAuthenticatedUser(
      nickname: '홍길동',
      email: 'honggildong@example.com',
      accessToken: 'offline-token',
      expiresInSeconds: 3600,
    );
    await provider.addClothes(localClothes);

    final service = PostLoginSyncService(
      authApiService: _FakeAuthApiService(
        error: const AuthApiException(
          type: AuthApiErrorType.network,
          message: 'connection failed',
        ),
      ),
    );

    await service.synchronize(provider: provider, accessToken: 'offline-token');

    expect(provider.isAuthenticated, isTrue);
    expect(provider.items, [localClothes]);
  });

  test('서버가 새 토큰을 거부하면 로컬 세션과 화면 데이터를 정리한다', () async {
    final authStorage = FakeAuthSessionStorage();
    final provider = ClosetProvider(
      storage: FakeClosetStorage(),
      authSessionStorage: authStorage,
    );

    await provider.setAuthenticatedUser(
      nickname: '홍길동',
      email: 'honggildong@example.com',
      accessToken: 'rejected-token',
      expiresInSeconds: 3600,
    );
    await provider.addClothes(
      Clothes(
        title: '홍길동 코튼 셔츠',
        category: '상의',
        health: 80,
        materials: {'cotton': 100},
        careInstruction: '찬물 세탁',
        carbonFootprint: 5.0,
      ),
    );

    final service = PostLoginSyncService(
      authApiService: _FakeAuthApiService(
        error: const AuthApiException(
          type: AuthApiErrorType.unauthorized,
          message: '로그인이 필요합니다.',
          statusCode: 401,
        ),
      ),
    );

    await expectLater(
      service.synchronize(provider: provider, accessToken: 'rejected-token'),
      throwsA(isA<AuthApiException>()),
    );

    expect(provider.isAuthenticated, isFalse);
    expect(provider.items, isEmpty);
    expect(authStorage.savedSession, isNull);
  });
}

class _FakeAuthApiService extends AuthApiService {
  _FakeAuthApiService({this.snapshot, this.error});

  final AuthSessionSnapshot? snapshot;
  final AuthApiException? error;

  @override
  Future<AuthSessionSnapshot> fetchSessionSnapshot({
    required String accessToken,
  }) async {
    if (error != null) throw error!;
    return snapshot!;
  }
}
