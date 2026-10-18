import 'dart:async';
import 'dart:convert';

import 'package:k_dpp/services/closet_backup_api_service.dart';

/// 보낸 업로드 한 번의 기록입니다.
class FakeClosetUpload {
  const FakeClosetUpload({
    required this.accessToken,
    required this.userId,
    required this.baseVersion,
    required this.items,
  });

  final String accessToken;
  final int userId;
  final int baseVersion;
  final List<Map<String, dynamic>> items;

  List<String?> get titles =>
      items.map((item) => item['title'] as String?).toList();
}

/// 서버의 `/me/closet` 을 흉내 냅니다. [fetchResults]·[uploadResults] 에 넣은 결과가 있으면
/// 그것부터 돌려주고, 없으면 계약대로(같은 내용 → changed false · 판이 다르면 409) 답합니다.
class FakeClosetBackupApi implements ClosetBackupApi {
  FakeClosetBackupApi({
    this.baseUrl = 'https://api.test',
    this.serverUserId = 1,
  });

  @override
  final String baseUrl;

  int serverUserId;
  int serverVersion = 0;
  List<Map<String, dynamic>> serverItems = [];

  final List<ClosetBackupFetchResult> fetchResults = [];
  final List<ClosetBackupUploadResult> uploadResults = [];

  final List<String> fetchTokens = [];
  final List<FakeClosetUpload> uploads = [];

  /// 있으면 다음 업로드를 끝내라고 할 때까지 붙잡습니다(한 번 쓰고 비웁니다).
  Completer<void>? holdNextUpload;

  /// 있으면 다음 받기를 끝내라고 할 때까지 붙잡습니다(한 번 쓰고 비웁니다).
  Completer<void>? holdNextFetch;

  /// 서버 백업을 [items] 로 바꿉니다(다른 폰이 올린 것 흉내).
  void putServerBackup(List<Map<String, dynamic>> items, {int? version}) {
    serverItems = _copy(items);
    serverVersion = version ?? serverVersion + 1;
  }

  @override
  Future<ClosetBackupFetchResult> fetch({required String accessToken}) async {
    fetchTokens.add(accessToken);

    final hold = holdNextFetch;
    if (hold != null) {
      holdNextFetch = null;
      await hold.future;
    }

    if (fetchResults.isNotEmpty) return fetchResults.removeAt(0);

    return ClosetBackupFetched(
      userId: serverUserId,
      version: serverVersion,
      items: _copy(serverItems),
    );
  }

  @override
  Future<ClosetBackupUploadResult> upload({
    required String accessToken,
    required int userId,
    required int baseVersion,
    required List<Map<String, dynamic>> items,
  }) async {
    uploads.add(
      FakeClosetUpload(
        accessToken: accessToken,
        userId: userId,
        baseVersion: baseVersion,
        items: _copy(items),
      ),
    );

    final hold = holdNextUpload;
    if (hold != null) {
      holdNextUpload = null;
      await hold.future;
    }

    if (uploadResults.isNotEmpty) return uploadResults.removeAt(0);

    if (userId != serverUserId) {
      return const ClosetBackupUploadFailed(ClosetBackupFailure.ownerMismatch);
    }
    if (jsonEncode(items) == jsonEncode(serverItems)) {
      return ClosetBackupUploaded(version: serverVersion, changed: false);
    }
    if (baseVersion != serverVersion) {
      return ClosetBackupConflict(serverVersion);
    }

    serverItems = _copy(items);
    serverVersion++;
    return ClosetBackupUploaded(version: serverVersion, changed: true);
  }

  static List<Map<String, dynamic>> _copy(List<Map<String, dynamic>> items) {
    return (jsonDecode(jsonEncode(items)) as List)
        .cast<Map<String, dynamic>>()
        .toList();
  }
}
