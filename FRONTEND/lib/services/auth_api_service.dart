import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../config/api_environment.dart';
import '../models/analysis_history_record.dart';

enum AuthApiErrorType {
  badRequest,
  unauthorized,
  conflict,
  server,
  network,
  timeout,
  invalidResponse,
  unknown,
}

class AuthApiException implements Exception {
  const AuthApiException({
    required this.type,
    required this.message,
    this.statusCode,
  });

  final AuthApiErrorType type;
  final String message;
  final int? statusCode;

  String get userMessage {
    switch (type) {
      case AuthApiErrorType.badRequest:
      case AuthApiErrorType.unauthorized:
      case AuthApiErrorType.conflict:
        return message;
      case AuthApiErrorType.server:
        return '서비스에 일시적인 문제가 생겼어요. 잠시 후 다시 시도해 주세요.';
      case AuthApiErrorType.network:
        return '인터넷에 연결할 수 없어요. Wi-Fi나 모바일 데이터를 확인해 주세요.';
      case AuthApiErrorType.timeout:
        return '응답이 늦어지고 있어요. 네트워크를 확인한 뒤 다시 시도해 주세요.';
      case AuthApiErrorType.invalidResponse:
        return '로그인 정보를 확인하지 못했어요. 앱을 다시 시작한 뒤 시도해 주세요.';
      case AuthApiErrorType.unknown:
        return '요청을 완료하지 못했어요. 잠시 후 다시 시도해 주세요.';
    }
  }

  factory AuthApiException.fromStatusCode({
    required int statusCode,
    required String responseBody,
  }) {
    final serverMessage = _extractServerMessage(responseBody);

    switch (statusCode) {
      case 400:
      case 422:
        return AuthApiException(
          type: AuthApiErrorType.badRequest,
          statusCode: statusCode,
          message: serverMessage ?? '입력한 계정 정보를 다시 확인해 주세요.',
        );
      case 401:
      case 403:
        return AuthApiException(
          type: AuthApiErrorType.unauthorized,
          statusCode: statusCode,
          message: serverMessage ?? '이메일 또는 비밀번호가 올바르지 않습니다.',
        );
      case 409:
        return AuthApiException(
          type: AuthApiErrorType.conflict,
          statusCode: statusCode,
          message: serverMessage ?? '이미 가입된 이메일입니다.',
        );
      default:
        if (statusCode >= 500) {
          return AuthApiException(
            type: AuthApiErrorType.server,
            statusCode: statusCode,
            message: serverMessage ?? '서버 내부 오류입니다.',
          );
        }

        return AuthApiException(
          type: AuthApiErrorType.unknown,
          statusCode: statusCode,
          message: serverMessage ?? '인증 요청을 처리하지 못했습니다.',
        );
    }
  }

  @override
  String toString() {
    if (statusCode == null) {
      return 'AuthApiException($type): $message';
    }

    return 'AuthApiException($type, statusCode: $statusCode): $message';
  }

  static String? _extractServerMessage(String responseBody) {
    try {
      final decoded = jsonDecode(responseBody);

      if (decoded is Map<String, dynamic>) {
        final detail = decoded['detail'];
        final message =
            decoded['message'] ??
            decoded['error'] ??
            decoded['reason'] ??
            (detail is String ? detail : null);

        if (message != null && message.toString().trim().isNotEmpty) {
          return message.toString().trim();
        }
      }
    } catch (_) {
      return null;
    }

    return null;
  }
}

class AuthUser {
  const AuthUser({
    required this.id,
    required this.email,
    required this.nickname,
  });

  final int id;
  final String email;
  final String nickname;

  factory AuthUser.fromJson(Map<String, dynamic> json) {
    final id = _parseInt(json['id']);
    final email = json['email']?.toString().trim() ?? '';
    final nickname = json['nickname']?.toString().trim() ?? '';

    if (id == null || email.isEmpty || nickname.isEmpty) {
      throw const FormatException('사용자 정보 응답이 올바르지 않습니다.');
    }

    return AuthUser(id: id, email: email, nickname: nickname);
  }

  static int? _parseInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '');
  }
}

class AuthResult {
  const AuthResult({
    required this.user,
    this.accessToken,
    this.tokenType,
    this.expiresInSeconds,
  });

  final AuthUser user;
  final String? accessToken;
  final String? tokenType;
  final int? expiresInSeconds;
}

class AuthSessionSnapshot {
  const AuthSessionSnapshot({required this.user, required this.history});

  final AuthUser user;
  final List<AnalysisHistoryRecord> history;
}

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

  Future<AuthResult> login({required String email, required String password}) {
    return _post('/auth/login', {
      'email': email.trim(),
      'password': password,
    }, requiresAccessToken: true);
  }

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

  Future<AuthUser> validateSession({required String accessToken}) async {
    final snapshot = await fetchSessionSnapshot(accessToken: accessToken);
    return snapshot.user;
  }

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
