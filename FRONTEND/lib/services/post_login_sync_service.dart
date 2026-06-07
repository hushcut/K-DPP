import 'package:flutter/foundation.dart';

import '../closet_provider.dart';
import 'auth_api_service.dart';

class PostLoginSyncService {
  const PostLoginSyncService({required this.authApiService});

  final AuthApiService authApiService;

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
      );
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
