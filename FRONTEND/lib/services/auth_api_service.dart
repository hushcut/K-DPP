import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../config/api_environment.dart';
import '../models/analysis_history_record.dart';

part 'auth_api_models.dart';

/// 회원가입, 로그인, 로그아웃, 세션 검증을 수행하는 HTTP 인증 클라이언트다.
class AuthApiService {
  AuthApiService({
    String? baseUrl,
    this.requestHeaders = const {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'ngrok-skip-browser-warning': 'true',
    },
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
    final activeClient = client ?? http.Client();
    final shouldCloseClient = client == null;

    try {
      final response = await activeClient
          .post(
            _buildUri('/auth/logout'),
            headers: {
              ...requestHeaders,
              'Authorization': 'Bearer $accessToken',
            },
          )
          .timeout(requestTimeout);
      final responseBody = utf8.decode(response.bodyBytes);

      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw AuthApiException.fromStatusCode(
          statusCode: response.statusCode,
          responseBody: responseBody,
        );
      }
    } on AuthApiException {
      rethrow;
    } on SocketException catch (error) {
      throw AuthApiException(
        type: AuthApiErrorType.network,
        message: error.message,
      );
    } on http.ClientException catch (error) {
      throw AuthApiException(
        type: AuthApiErrorType.network,
        message: error.message,
      );
    } on TimeoutException {
      throw const AuthApiException(
        type: AuthApiErrorType.timeout,
        message: '로그아웃 요청 시간이 초과되었습니다.',
      );
    } catch (error) {
      throw AuthApiException(
        type: AuthApiErrorType.unknown,
        message: error.toString(),
      );
    } finally {
      if (shouldCloseClient) {
        activeClient.close();
      }
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
    final activeClient = client ?? http.Client();
    final shouldCloseClient = client == null;

    try {
      final response = await activeClient
          .get(
            _buildUri('/me/history'),
            headers: {
              ...requestHeaders,
              'Authorization': 'Bearer $accessToken',
            },
          )
          .timeout(requestTimeout);
      final responseBody = utf8.decode(response.bodyBytes);

      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw AuthApiException.fromStatusCode(
          statusCode: response.statusCode,
          responseBody: responseBody,
        );
      }

      final decoded = jsonDecode(responseBody);

      if (decoded is! Map<String, dynamic>) {
        throw const FormatException('응답이 JSON 객체 형식이 아닙니다.');
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
    } on SocketException catch (error) {
      throw AuthApiException(
        type: AuthApiErrorType.network,
        message: error.message,
      );
    } on http.ClientException catch (error) {
      throw AuthApiException(
        type: AuthApiErrorType.network,
        message: error.message,
      );
    } on TimeoutException {
      throw const AuthApiException(
        type: AuthApiErrorType.timeout,
        message: '로그인 확인 시간이 초과되었습니다.',
      );
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
    } finally {
      if (shouldCloseClient) {
        activeClient.close();
      }
    }
  }

  Future<AuthResult> _post(
    String path,
    Map<String, String> body, {
    bool requiresAccessToken = false,
  }) async {
    final activeClient = client ?? http.Client();
    final shouldCloseClient = client == null;

    try {
      final response = await activeClient
          .post(
            _buildUri(path),
            headers: requestHeaders,
            body: jsonEncode(body),
          )
          .timeout(requestTimeout);
      final responseBody = utf8.decode(response.bodyBytes);

      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw AuthApiException.fromStatusCode(
          statusCode: response.statusCode,
          responseBody: responseBody,
        );
      }

      return _parseResult(
        responseBody,
        requiresAccessToken: requiresAccessToken,
      );
    } on AuthApiException {
      rethrow;
    } on SocketException catch (error) {
      throw AuthApiException(
        type: AuthApiErrorType.network,
        message: error.message,
      );
    } on http.ClientException catch (error) {
      throw AuthApiException(
        type: AuthApiErrorType.network,
        message: error.message,
      );
    } on TimeoutException {
      throw const AuthApiException(
        type: AuthApiErrorType.timeout,
        message: '인증 요청 시간이 초과되었습니다.',
      );
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
    } finally {
      if (shouldCloseClient) {
        activeClient.close();
      }
    }
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
