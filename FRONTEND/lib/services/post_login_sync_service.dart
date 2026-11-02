import 'package:flutter/foundation.dart';

import '../closet_provider.dart';
import 'auth_api_service.dart';

/// 로그인 직후 서버 프로필을 반영하고, 옷장을 서버 백업과 맞춘 뒤, 저장 ID가 일치하는 기존 의류의 분석값을 갱신한다.
class PostLoginSyncService {
  const PostLoginSyncService({required this.authApiService});

  final AuthApiService authApiService;

  /// 인증 거부는 로그아웃 후 상위 호출부로 전달하고, 그 밖의 동기화 실패는 기록만 남긴다.
  Future<void> synchronize({
    required ClosetProvider provider,
    required String accessToken,
  }) async {
    try {
      final snapshot = await authApiService.fetchSessionSnapshot(
        accessToken: accessToken,
      );

      await provider.setUserProfile(
        nickname: snapshot.user.nickname,
        email: snapshot.user.email,
        userId: snapshot.user.id,
        loginMethods: snapshot.user.loginMethods,
      );
      // 백업과 처음 맞추면 서버 옷을 받아 합칩니다. 예외를 던지지 않고, 올리기는 기다리지 않습니다.
      await provider.syncClosetBackup();
      await provider.synchronizeServerHistory(snapshot.history);
    } on AuthApiException catch (error, stackTrace) {
      if (error.type == AuthApiErrorType.unauthorized) {
        await provider.logout();
        rethrow;
      }

      debugPrint('로그인 후 서버 이력을 동기화하지 못했습니다: $error');
      debugPrintStack(stackTrace: stackTrace);
    } catch (error, stackTrace) {
      debugPrint('로그인 후 서버 이력 동기화 중 오류가 발생했습니다: $error');
      debugPrintStack(stackTrace: stackTrace);
    }
  }
}
