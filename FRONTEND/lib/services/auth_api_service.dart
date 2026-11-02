import 'dart:convert';
import 'dart:math' as math;

import 'package:http/http.dart' as http;

import '../config/api_environment.dart';
import '../models/analysis_history_record.dart';
import 'api_http.dart';

part 'auth_api_models.dart';

/// 인증번호 요청, 회원가입, 로그인(이메일·카카오), 로그아웃, 비밀번호 변경·찾기, 회원 탈퇴,
/// 세션 검증을 수행하는 HTTP 인증 클라이언트다.
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

  /// 가입·비밀번호 찾기용 인증번호를 이메일로 보내 달라고 요청한다.
  ///
  /// 서버는 가입 여부와 상관없이 같은 용도면 같은 응답을 준다. 시간 값이 빠진 응답도 계약의
  /// 기본값(10분·60초)으로 받아, 번호가 이미 간 뒤에 오류로 보이지 않게 한다.
  Future<EmailCodeRequestResult> requestEmailCode({
    required String email,
    required EmailCodePurpose purpose,
  }) async {
    final payload = await _postForObject('/auth/email-code', {
      'email': email.trim(),
      'purpose': purpose.apiValue,
    }, timeoutMessage: '인증번호 요청 시간이 초과되었습니다.');
    final expiresIn = _parseInt(payload['expires_in']);
    final resendAfter = _parseInt(payload['resend_after']);

    return EmailCodeRequestResult(
      expiresInSeconds: expiresIn != null && expiresIn > 0 ? expiresIn : 600,
      resendAfterSeconds: resendAfter != null && resendAfter >= 0
          ? resendAfter
          : 60,
    );
  }

  /// 닉네임·이메일·인증번호의 앞뒤 공백을 제거해 회원가입을 요청하고 생성된 사용자 정보를 반환한다.
  Future<AuthResult> signup({
    required String nickname,
    required String email,
    required String password,
    required String code,
  }) {
    return _post('/auth/signup', {
      'nickname': nickname.trim(),
      'email': email.trim(),
      'password': password,
      'code': code.trim(),
    });
  }

  /// 인증번호로 확인한 뒤 새 비밀번호로 바꾼다. 서버가 그 계정의 토큰을 모두 지우고 새 토큰은
  /// 주지 않으므로, 성공하면 로그인 화면으로 돌아가 새 비밀번호로 로그인한다.
  Future<void> resetPassword({
    required String email,
    required String code,
    required String newPassword,
  }) async {
    await _postForObject('/auth/password-reset', {
      'email': email.trim(),
      'code': code.trim(),
      'new_password': newPassword,
    }, timeoutMessage: '비밀번호 재설정 요청 시간이 초과되었습니다.');
  }

  /// 로그인을 요청하며 응답에 유효한 액세스 토큰과 만료 시간이 반드시 있는지 검사한다.
  Future<AuthResult> login({required String email, required String password}) {
    return _post('/auth/login', {
      'email': email.trim(),
      'password': password,
    }, requiresAccessToken: true);
  }

  /// 카카오 SDK 로그인으로 받은 카카오 액세스 토큰으로 로그인한다. 처음 오는 카카오 계정이면
  /// 가입도 함께 되고 [AuthResult.isNewUser] 가 참이다.
  ///
  /// [nickname] 은 서버가 `SOCIAL_NICKNAME_REQUIRED` 로 닉네임을 요구한 뒤 같은 토큰으로 다시
  /// 보낼 때만 넣는다. 첫 요청에 넣으면 서버가 카카오 사용자 정보를 조회하지 않아, 카카오가
  /// 24시간 뒤 '가입 미완료'로 연결을 끊는다(DECISIONS 163).
  Future<AuthResult> kakaoLogin({
    required String accessToken,
    String? nickname,
  }) {
    return _post('/auth/kakao', {
      'access_token': accessToken,
      if (nickname != null) 'nickname': nickname.trim(),
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

  /// 현재 비밀번호를 확인해 새 비밀번호로 바꾸고, 이 기기가 계속 쓸 새 토큰을 받는다.
  ///
  /// 서버가 기존 토큰을 모두 폐기하므로 응답의 access_token을 반드시 저장해야 한다.
  Future<AuthResult> changePassword({
    required String accessToken,
    required String currentPassword,
    required String newPassword,
  }) {
    return _post(
      '/auth/password',
      {'current_password': currentPassword, 'new_password': newPassword},
      requiresAccessToken: true,
      accessToken: accessToken,
    );
  }

  /// 비밀번호를 확인한 뒤 계정과 서버 데이터 삭제를 요청한다.
  ///
  /// 성공 응답에는 사용자 정보가 없으므로 로그아웃과 같은 방식으로 성공 여부만 확인한다.
  Future<void> withdraw({
    required String accessToken,
    required String password,
  }) {
    return _withdraw(accessToken: accessToken, body: {'password': password});
  }

  /// 비밀번호가 없는 카카오 계정의 탈퇴다. [kakaoAccessToken] 은 탈퇴 확인 단계에서 카카오계정
  /// 로그인을 다시 해 받은 토큰이어야 한다(`KakaoLoginService.reauthenticate`) — 로그인 때 받아
  /// SDK 에 저장된 토큰을 쓰면 사용자 입력 없이 탈퇴된다(`docs/SCAN_API_CONTRACT.md` 2-3).
  /// 카카오 연결 끊기는 서버가 한다.
  Future<void> withdrawWithKakao({
    required String accessToken,
    required String kakaoAccessToken,
  }) {
    return _withdraw(
      accessToken: accessToken,
      body: {'kakao_access_token': kakaoAccessToken},
    );
  }

  Future<void> _withdraw({
    required String accessToken,
    required Map<String, String> body,
  }) async {
    try {
      final response = await runJsonApiRequest(
        method: 'POST',
        uri: _buildUri('/auth/withdraw'),
        headers: requestHeaders,
        timeout: requestTimeout,
        jsonBody: body,
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
      throw _fromTransport(error, timeoutMessage: '회원 탈퇴 요청 시간이 초과되었습니다.');
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
    String? accessToken,
  }) async {
    try {
      final response = await runJsonApiRequest(
        method: 'POST',
        uri: _buildUri(path),
        headers: requestHeaders,
        timeout: requestTimeout,
        jsonBody: body,
        accessToken: accessToken,
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

  /// 사용자 정보가 없는 성공 응답(`status`·`message` 와 그 API 의 값)을 JSON 객체로 받는다.
  /// 2xx 로 내려온 오류 봉투도 다른 인증 요청과 같이 서버 메시지를 살린다.
  Future<Map<String, dynamic>> _postForObject(
    String path,
    Map<String, String> body, {
    required String timeoutMessage,
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

      final decoded = jsonDecode(response.body);

      if (decoded is! Map<String, dynamic>) {
        throw const FormatException('응답이 JSON 객체 형식이 아닙니다.');
      }

      if (decoded['success'] == false || decoded['status'] == 'error') {
        throw AuthApiException(
          type: AuthApiErrorType.badRequest,
          message: decoded['message']?.toString() ?? '인증 요청에 실패했어요.',
        );
      }

      return decoded;
    } on AuthApiException {
      rethrow;
    } on ApiTransportException catch (error) {
      throw _fromTransport(error, timeoutMessage: timeoutMessage);
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
        message: decoded['message']?.toString() ?? '인증 요청에 실패했어요.',
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
      isNewUser: payload['is_new_user'] == true,
    );
  }

  int? _parseInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '');
  }
}
