// 옷장 서버 백업(GET·POST /me/closet)을 부르고, 응답을 옷장이 다룰 결과로 나누는 파일입니다(DECISIONS 242).
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../config/api_environment.dart';
import 'api_http.dart';

/// 백업 요청이 뜻대로 되지 않은 까닭입니다(`BACKEND/API_CONTRACT.md` '앱 연동 메모(옷장 백업)').
enum ClosetBackupFailure {
  /// 401 — 세션이 무효입니다. 백업만 조용히 멈추고 로그아웃하지 않습니다.
  unauthorized,

  /// 403 `CLOSET_OWNER_MISMATCH` — 로그인이 바뀌는 틈에 옛 계정 id 로 보냈습니다. 이번 시도만 버립니다.
  ownerMismatch,

  /// 그 밖의 4xx(404 빼고) — 다시 보내도 같으니 이번 실행 동안 이 계정 백업을 멈춥니다.
  rejected,

  /// 404·5xx·네트워크·시간 초과·알 수 없는 응답 — 다음 기회에 다시 합니다.
  unavailable,
}

/// `GET /me/closet` 의 결과입니다.
sealed class ClosetBackupFetchResult {
  const ClosetBackupFetchResult();
}

/// 서버 백업을 받았습니다. 백업이 없으면 [version] 0·빈 [items] 입니다.
final class ClosetBackupFetched extends ClosetBackupFetchResult {
  const ClosetBackupFetched({
    required this.userId,
    required this.version,
    required this.items,
  });

  final int userId;
  final int version;

  /// 서버가 돌려준 배열 그대로입니다. 원소가 옷 객체인지는 부르는 쪽이 봅니다.
  final List<Object?> items;
}

final class ClosetBackupFetchFailed extends ClosetBackupFetchResult {
  const ClosetBackupFetchFailed(this.failure);

  final ClosetBackupFailure failure;
}

/// `POST /me/closet` 의 결과입니다.
sealed class ClosetBackupUploadResult {
  const ClosetBackupUploadResult();
}

/// 서버가 받았습니다. 같은 내용이면 [changed] 가 false 이고 [version] 은 그대로입니다.
final class ClosetBackupUploaded extends ClosetBackupUploadResult {
  const ClosetBackupUploaded({required this.version, required this.changed});

  final int version;
  final bool changed;
}

/// 409 `CLOSET_VERSION_CONFLICT` — 다른 기기가 먼저 바꿨습니다. 지금 서버 판은 [currentVersion] 입니다.
final class ClosetBackupConflict extends ClosetBackupUploadResult {
  const ClosetBackupConflict(this.currentVersion);

  final int currentVersion;
}

final class ClosetBackupUploadFailed extends ClosetBackupUploadResult {
  const ClosetBackupUploadFailed(this.failure);

  final ClosetBackupFailure failure;
}

/// 옷장 서버 백업 API 입니다. 시험에서는 가짜로 바꿉니다.
abstract class ClosetBackupApi {
  /// 이 API 가 부르는 서버 주소입니다. 맞춘 상태(`ClosetBackupState.apiBaseUrl`)에 남습니다.
  String get baseUrl;

  Future<ClosetBackupFetchResult> fetch({required String accessToken});

  Future<ClosetBackupUploadResult> upload({
    required String accessToken,
    required int userId,
    required int baseVersion,
    required List<Map<String, dynamic>> items,
  });
}

/// 서버의 `/me/closet` 을 부릅니다. 예외를 던지지 않고 결과로 돌려줍니다.
class ClosetBackupApiService implements ClosetBackupApi {
  ClosetBackupApiService({
    String? baseUrl,
    this.client,
    this.fetchTimeout = const Duration(seconds: 10),
    this.uploadTimeout = const Duration(seconds: 20),
  }) : baseUrl = _trimTrailingSlashes(baseUrl ?? ApiEnvironment.authBaseUrl);

  @override
  final String baseUrl;
  final http.Client? client;
  final Duration fetchTimeout;
  final Duration uploadTimeout;

  Uri get _closetUri => Uri.parse('$baseUrl/me/closet');

  // 맞춘 상태의 `api` 칸과 견주므로, 끝 슬래시만 다른 같은 주소가 다른 서버로 보이지 않게 합니다.
  static String _trimTrailingSlashes(String value) {
    var trimmed = value.trim();
    while (trimmed.endsWith('/')) {
      trimmed = trimmed.substring(0, trimmed.length - 1);
    }
    return trimmed;
  }

  @override
  Future<ClosetBackupFetchResult> fetch({required String accessToken}) async {
    try {
      final response = await runJsonApiRequest(
        method: 'GET',
        uri: _closetUri,
        headers: kDefaultJsonApiHeaders,
        timeout: fetchTimeout,
        accessToken: accessToken,
        client: client,
      );

      if (!response.isSuccess) {
        return ClosetBackupFetchFailed(_classifyFailure(response));
      }

      final body = _decodeObject(response.body);
      final userId = body?['user_id'];
      final version = body?['version'];
      final items = body?['items'];

      if (userId is! int || version is! int || version < 0 || items is! List) {
        return const ClosetBackupFetchFailed(ClosetBackupFailure.unavailable);
      }

      return ClosetBackupFetched(
        userId: userId,
        version: version,
        items: List<Object?>.unmodifiable(items),
      );
    } catch (error) {
      _logFailure('GET', error);
      return const ClosetBackupFetchFailed(ClosetBackupFailure.unavailable);
    }
  }

  @override
  Future<ClosetBackupUploadResult> upload({
    required String accessToken,
    required int userId,
    required int baseVersion,
    required List<Map<String, dynamic>> items,
  }) async {
    try {
      final response = await runJsonApiRequest(
        method: 'POST',
        uri: _closetUri,
        headers: kDefaultJsonApiHeaders,
        timeout: uploadTimeout,
        jsonBody: {
          'user_id': userId,
          'base_version': baseVersion,
          'items': items,
        },
        accessToken: accessToken,
        client: client,
      );

      if (response.isSuccess) {
        final body = _decodeObject(response.body);
        final version = body?['version'];
        final changed = body?['changed'];

        // 받았는지 모르는 응답이면 맞춘 상태를 바꾸지 않고, 다음 변경 때 다시 보냅니다.
        if (version is! int || version < 0 || changed is! bool) {
          return const ClosetBackupUploadFailed(
            ClosetBackupFailure.unavailable,
          );
        }

        return ClosetBackupUploaded(version: version, changed: changed);
      }

      if (response.statusCode == 409 &&
          _errorCode(response.body) == 'CLOSET_VERSION_CONFLICT') {
        final currentVersion = _detail(response.body)?['current_version'];

        if (currentVersion is int && currentVersion >= 0) {
          return ClosetBackupConflict(currentVersion);
        }
      }

      return ClosetBackupUploadFailed(_classifyFailure(response));
    } catch (error) {
      _logFailure('POST', error);
      return const ClosetBackupUploadFailed(ClosetBackupFailure.unavailable);
    }
  }

  static ClosetBackupFailure _classifyFailure(ApiHttpResponse response) {
    final status = response.statusCode;

    if (status == 401) return ClosetBackupFailure.unauthorized;
    if (status == 403 && _errorCode(response.body) == 'CLOSET_OWNER_MISMATCH') {
      return ClosetBackupFailure.ownerMismatch;
    }
    // 404 는 이 API 가 없는 옛 서버이거나 잘못된 주소라, 서버가 바뀌면 다시 닿을 수 있습니다.
    if (status == 404) return ClosetBackupFailure.unavailable;
    if (status >= 400 && status < 500) return ClosetBackupFailure.rejected;
    return ClosetBackupFailure.unavailable;
  }

  static String? _errorCode(String responseBody) {
    final body = _decodeObject(responseBody);
    final code = body?['error_code'] ?? _detail(responseBody)?['error_code'];
    return code is String ? code : null;
  }

  static Map<String, dynamic>? _detail(String responseBody) {
    final detail = _decodeObject(responseBody)?['detail'];
    return detail is Map<String, dynamic> ? detail : null;
  }

  static Map<String, dynamic>? _decodeObject(String responseBody) {
    try {
      final decoded = jsonDecode(responseBody);
      return decoded is Map<String, dynamic> ? decoded : null;
    } on FormatException {
      return null;
    }
  }

  // 옷 이름·소재가 로그에 남지 않게 오류의 종류만 적습니다.
  static void _logFailure(String method, Object error) {
    final kind = error is ApiTransportException
        ? error.type.name
        : error.runtimeType.toString();
    debugPrint('옷장 백업 $method 에 닿지 못했습니다: $kind');
  }
}
