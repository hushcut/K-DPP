import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_environment.dart';
import '../models/analysis_history_record.dart';
import 'api_http.dart';

part 'auth_api_models.dart';

/// 회원가입, 로그인, 로그아웃, 세션 검증을 수행하는 HTTP 인증 클라이언트다.
class AuthApiService {
  AuthApiService({
    String? baseUrl,
    this.requestHeaders = kDefaultJsonApiHeaders,
    this.requestTimeout = const Duration(seconds: 15),
    this.client,
  }) : baseUrl = baseUrl ?? ApiEnvironment.authBaseUrl;

  final String baseUrl;
  final Map<String, String> requestHeaders;
  final Duration requestTimeout;
  final http.Client? client;

  /// 닉네임·이메일의 앞뒤 공백을 제거해 회원가입을 요청하고 생성된 사용자 정보를 반환한다.
  Future<AuthResult> signup({
    required String nickname,
    required String email,
    required String password,
  }) {
    return _post('/auth/signup', {
      'nickname': nickname.trim(),
      'email': email.trim(),
      'password': password,
    });
  }

  /// 로그인을 요청하며 응답에 유효한 액세스 토큰과 만료 시간이 반드시 있는지 검사한다.
  Future<AuthResult> login({required String email, required String password}) {
    return _post('/auth/login', {
      'email': email.trim(),
      'password': password,
    }, requiresAccessToken: true);
  }

  /// Bearer 토큰으로 서버 세션 종료를 요청하고 통신 실패를 인증 예외로 변환한다.
  Future<void> logout({required String accessToken}) async {
    try {
      final response = await runJsonApiRequest(
        method: 'POST',
        uri: _buildUri('/auth/logout'),
        headers: requestHeaders,
        timeout: requestTimeout,
        accessToken: accessToken,
        client: client,
      );

      if (!response.isSuccess) {
        throw AuthApiException.fromStatusCode(
          statusCode: response.statusCode,
          responseBody: response.body,
        );
      }
    } on AuthApiException {
      rethrow;
    } on ApiTransportException catch (error) {
      throw _fromTransport(error, timeoutMessage: '로그아웃 요청 시간이 초과되었습니다.');
    } catch (error) {
      throw AuthApiException(
        type: AuthApiErrorType.unknown,
        message: error.toString(),
      );
    }
  }

  /// 세션 스냅샷을 조회해 현재 인증된 사용자만 반환한다.
  Future<AuthUser> validateSession({required String accessToken}) async {
    final snapshot = await fetchSessionSnapshot(accessToken: accessToken);
    return snapshot.user;
  }

  /// `/me/history`에서 사용자와 분석 이력을 함께 가져온다.
  /// 형식이 잘못된 개별 이력은 건너뛰되 사용자·목록 구조 오류는 요청 실패로 처리한다.
  Future<AuthSessionSnapshot> fetchSessionSnapshot({
    required String accessToken,
  }) async {
    try {
      final response = await runJsonApiRequest(
        method: 'GET',
        uri: _buildUri('/me/history'),
        headers: requestHeaders,
        timeout: requestTimeout,
        accessToken: accessToken,
        client: client,
      );

      if (!response.isSuccess) {
        throw AuthApiException.fromStatusCode(
          statusCode: response.statusCode,
          responseBody: response.body,
        );
      }

      final decoded = jsonDecode(response.body);

      if (decoded is! Map<String, dynamic>) {
        throw const FormatException('응답이 JSON 객체 형식이 아닙니다.');
      }

      // 2xx로 내려온 오류 봉투도 로그인·가입 파싱과 동일하게 서버 메시지를 살립니다.
      if (decoded['success'] == false || decoded['status'] == 'error') {
        throw AuthApiException(
          type: AuthApiErrorType.badRequest,
          message: decoded['message']?.toString() ?? '세션 정보를 불러오지 못했습니다.',
        );
      }

      final userJson = decoded['user'];

      if (userJson is! Map) {
        throw const FormatException('사용자 정보가 응답에 없습니다.');
      }

      final rawHistory = decoded['history'];

      if (rawHistory is! List) {
        throw const FormatException('서버 의류 기록이 응답에 없습니다.');
      }

      final history = <AnalysisHistoryRecord>[];

      for (final item in rawHistory.whereType<Map>()) {
        try {
          history.add(
            AnalysisHistoryRecord.fromJson(Map<String, dynamic>.from(item)),
          );
        } on FormatException {
          continue;
        }
      }

      return AuthSessionSnapshot(
        user: AuthUser.fromJson(Map<String, dynamic>.from(userJson)),
        history: history,
      );
    } on AuthApiException {
      rethrow;
    } on ApiTransportException catch (error) {
      throw _fromTransport(error, timeoutMessage: '로그인 확인 시간이 초과되었습니다.');
    } on FormatException catch (error) {
      throw AuthApiException(
        type: AuthApiErrorType.invalidResponse,
        message: error.message,
      );
    } catch (error) {
      throw AuthApiException(
        type: AuthApiErrorType.unknown,
        message: error.toString(),
      );
    }
  }

  Future<AuthResult> _post(
    String path,
    Map<String, String> body, {
    bool requiresAccessToken = false,
  }) async {
    try {
      final response = await runJsonApiRequest(
        method: 'POST',
        uri: _buildUri(path),
        headers: requestHeaders,
        timeout: requestTimeout,
        jsonBody: body,
        client: client,
      );

      if (!response.isSuccess) {
        throw AuthApiException.fromStatusCode(
          statusCode: response.statusCode,
          responseBody: response.body,
        );
      }

      return _parseResult(
        response.body,
        requiresAccessToken: requiresAccessToken,
      );
    } on AuthApiException {
      rethrow;
    } on ApiTransportException catch (error) {
      throw _fromTransport(error, timeoutMessage: '인증 요청 시간이 초과되었습니다.');
    } on FormatException catch (error) {
      throw AuthApiException(
        type: AuthApiErrorType.invalidResponse,
        message: error.message,
      );
    } catch (error) {
      throw AuthApiException(
        type: AuthApiErrorType.unknown,
        message: error.toString(),
      );
    }
  }

  /// 공통 전송 오류를 인증 오류 유형으로 변환한다.
  AuthApiException _fromTransport(
    ApiTransportException error, {
    required String timeoutMessage,
  }) {
    return switch (error.type) {
      ApiTransportErrorType.network => AuthApiException(
        type: AuthApiErrorType.network,
        message: error.message,
      ),
      ApiTransportErrorType.timeout => AuthApiException(
        type: AuthApiErrorType.timeout,
        message: timeoutMessage,
      ),
    };
  }

  Uri _buildUri(String path) {
    final normalizedBaseUrl = baseUrl.endsWith('/')
        ? baseUrl.substring(0, baseUrl.length - 1)
        : baseUrl;

    return Uri.parse('$normalizedBaseUrl$path');
  }

  AuthResult _parseResult(
    String responseBody, {
    required bool requiresAccessToken,
  }) {
    final decoded = jsonDecode(responseBody);

    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('응답이 JSON 객체 형식이 아닙니다.');
    }

    if (decoded['success'] == false || decoded['status'] == 'error') {
      throw AuthApiException(
        type: AuthApiErrorType.badRequest,
        message: decoded['message']?.toString() ?? '인증 요청에 실패했습니다.',
      );
    }

    final payload = decoded['data'] is Map<String, dynamic>
        ? decoded['data'] as Map<String, dynamic>
        : decoded;
    final userJson = payload['user'];

    if (userJson is! Map) {
      throw const FormatException('사용자 정보가 응답에 없습니다.');
    }

    final accessToken = payload['access_token']?.toString().trim();
    final expiresInSeconds = _parseInt(payload['expires_in']);

    if (requiresAccessToken &&
        (accessToken == null ||
            accessToken.isEmpty ||
            expiresInSeconds == null ||
            expiresInSeconds <= 0)) {
      throw const FormatException('로그인 세션 정보가 응답에 없습니다.');
    }

    return AuthResult(
      user: AuthUser.fromJson(Map<String, dynamic>.from(userJson)),
      accessToken: accessToken,
      tokenType: payload['token_type']?.toString(),
      expiresInSeconds: expiresInSeconds,
    );
  }

  int? _parseInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '');
  }
}
