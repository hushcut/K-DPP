part of 'auth_api_service.dart';

/// 인증 API 실패를 HTTP 상태·네트워크·시간 초과·응답 형식 오류 등으로 구분합니다.
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

/// 인증 요청의 오류 유형, 메시지, HTTP 상태를 보존합니다.
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

  /// HTTP 상태와 서버 메시지를 화면에서 처리할 인증 예외로 변환합니다.
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

/// 인증 응답에 포함된 최소 사용자 프로필 DTO입니다.
class AuthUser {
  const AuthUser({
    required this.id,
    required this.email,
    required this.nickname,
  });

  final int id;
  final String email;
  final String nickname;

  /// 필수 필드가 빠진 응답은 [FormatException]으로 거부합니다.
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

/// 회원가입·로그인의 사용자 정보와 선택적 세션 토큰 DTO입니다.
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

/// 현재 사용자와 서버 분석 이력을 함께 전달하는 세션 DTO입니다.
class AuthSessionSnapshot {
  const AuthSessionSnapshot({required this.user, required this.history});

  final AuthUser user;
  final List<AnalysisHistoryRecord> history;
}
