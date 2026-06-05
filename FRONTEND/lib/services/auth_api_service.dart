import 'dart:convert';

import 'package:http/http.dart' as http;

import 'auth_session_service.dart';

class AuthApiException implements Exception {
  final String message;

  const AuthApiException(this.message);

  @override
  String toString() => message;
}

class AuthUser {
  final int id;
  final String email;
  final String nickname;

  const AuthUser({
    required this.id,
    required this.email,
    required this.nickname,
  });

  factory AuthUser.fromJson(Map<String, dynamic> json) {
    return AuthUser(
      id: (json['id'] as num).toInt(),
      email: json['email']?.toString() ?? '',
      nickname: json['nickname']?.toString() ?? '',
    );
  }
}

class AuthResult {
  final AuthUser user;
  final String? accessToken;

  const AuthResult({required this.user, this.accessToken});
}

class AuthApiService {
  final String baseUrl;
  final AuthSessionService sessionService;

  const AuthApiService({
    this.baseUrl = const String.fromEnvironment(
      'AUTH_API_BASE_URL',
      defaultValue: 'http://10.0.2.2:8000',
    ),
    this.sessionService = const AuthSessionService(),
  });

  Future<AuthResult> signup({
    required String nickname,
    required String email,
    required String password,
  }) {
    return _post('/auth/signup', {
      'nickname': nickname,
      'email': email,
      'password': password,
    });
  }

  Future<AuthResult> login({required String email, required String password}) {
    return _post('/auth/login', {'email': email, 'password': password});
  }

  Future<void> logout() async {
    final accessToken = await sessionService.readAccessToken();

    try {
      if (accessToken != null && accessToken.isNotEmpty) {
        await http.post(
          Uri.parse('$baseUrl/auth/logout'),
          headers: {'Authorization': 'Bearer $accessToken'},
        );
      }
    } finally {
      await sessionService.clear();
    }
  }

  Future<AuthResult> _post(String path, Map<String, String> body) async {
    final response = await http.post(
      Uri.parse('$baseUrl$path'),
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    final rawBody = utf8.decode(response.bodyBytes);

    Map<String, dynamic> decoded;
    try {
      decoded = jsonDecode(rawBody) as Map<String, dynamic>;
    } catch (_) {
      throw const AuthApiException('서버 응답을 읽지 못했습니다.');
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw AuthApiException(
        decoded['message']?.toString() ?? '요청 처리 중 오류가 발생했습니다.',
      );
    }

    final userJson = decoded['user'];
    if (userJson is! Map<String, dynamic>) {
      throw const AuthApiException('사용자 정보 응답이 올바르지 않습니다.');
    }

    return AuthResult(
      user: AuthUser.fromJson(userJson),
      accessToken: decoded['access_token']?.toString(),
    );
  }
}
