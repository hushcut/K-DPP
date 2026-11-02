part of 'auth_api_service.dart';

/// 인증 API 실패를 HTTP 상태·네트워크·시간 초과·응답 형식 오류 등으로 구분합니다.
enum AuthApiErrorType {
  badRequest,
  unauthorized,
  forbidden,
  conflict,
  server,
  network,
  timeout,
  invalidResponse,
  unknown,
}

/// 화면이 따로 다루는 서버 `error_code` 값입니다(`BACKEND/API_CONTRACT.md` 공통 오류 응답).
abstract final class AuthErrorCode {
  /// 400 의 기본값 — 닉네임 규칙 위반(`nickname_rule_error`) 등 입력 형식 오류입니다.
  static const badRequest = 'BAD_REQUEST';

  /// 422 — 요청 모델 검사(닉네임 50자 초과 등)에 걸렸습니다.
  static const validationError = 'VALIDATION_ERROR';

  /// 인증번호가 틀림 — 다시 입력할 기회가 남음(400, `detail.remaining_attempts`).
  static const verificationCodeInvalid = 'VERIFICATION_CODE_INVALID';

  /// 받은 번호가 없거나 만료됐거나 5번 틀림 — 다시 받아야 함(400).
  static const verificationCodeResendRequired =
      'VERIFICATION_CODE_RESEND_REQUIRED';

  /// 같은 이메일로 인증번호를 너무 빨리 다시 요청(429, `detail.retry_after`).
  static const emailCodeResendTooSoon = 'EMAIL_CODE_RESEND_TOO_SOON';

  /// 서버의 하루 인증 메일 발송 상한에 닿음(503).
  static const emailSendUnavailable = 'EMAIL_SEND_UNAVAILABLE';

  /// 시도·요청 횟수 한도 초과(429). 인증번호 요청이면 `detail.retry_after` 가 있습니다.
  static const tooManyAttempts = 'TOO_MANY_ATTEMPTS';

  /// 처음 온 카카오 계정인데 쓸 닉네임이 없음 — 닉네임을 받아 같은 카카오 토큰으로 다시(400).
  static const socialNicknameRequired = 'SOCIAL_NICKNAME_REQUIRED';

  /// 카카오가 토큰을 거부했거나 다른 앱이 받은 토큰 — 카카오 로그인부터 다시(로그인 401·탈퇴 400).
  static const socialTokenInvalid = 'SOCIAL_TOKEN_INVALID';

  /// 탈퇴 확인에 이 계정과 다른 카카오 계정으로 로그인함(400).
  static const socialAccountMismatch = 'SOCIAL_ACCOUNT_MISMATCH';

  /// 카카오가 답하지 않음(502). 계정을 바꾸기 전에 나므로 탈퇴는 진행되지 않은 것입니다.
  static const socialProviderUnavailable = 'SOCIAL_PROVIDER_UNAVAILABLE';

  /// 서버에 카카오 설정이 없음(503). 역시 탈퇴는 진행되지 않은 것입니다.
  static const socialLoginUnavailable = 'SOCIAL_LOGIN_UNAVAILABLE';
}

/// 사용자 객체의 `login_methods` 값입니다(`BACKEND/API_CONTRACT.md` '사용자 객체').
/// 목록에 '들어 있는지'로만 판단하고, 모르는 값은 무시합니다.
abstract final class LoginMethod {
  static const password = 'password';
  static const kakao = 'kakao';
}

/// 기다릴 시간을 줄여 씁니다. 60초까지는 초(다시 받기 대기가 '1분'에서 '59초'로 튀지 않게),
/// 1시간 미만은 분, 그 이상은 시간으로 올려 씁니다(서버 대기 문구와 같은 올림).
String formatAuthWait(int seconds) {
  if (seconds <= 60) return '${math.max(seconds, 1)}초';

  final minutes = (seconds / 60).ceil();
  if (minutes < 60) return '$minutes분';

  return '${(seconds / 3600).ceil()}시간';
}

/// 인증 요청의 오류 유형, 메시지, HTTP 상태와 서버가 보낸 분기 정보를 보존합니다.
class AuthApiException implements Exception {
  const AuthApiException({
    required this.type,
    required this.message,
    this.statusCode,
    this.errorCode,
    this.retryAfterSeconds,
    this.remainingAttempts,
  });

  final AuthApiErrorType type;
  final String message;
  final int? statusCode;

  /// 서버 응답의 `error_code` 입니다. 전송 오류처럼 응답이 없으면 null 입니다.
  final String? errorCode;

  /// 다시 요청할 수 있을 때까지 남은 초(`detail.retry_after`)입니다.
  final int? retryAfterSeconds;

  /// 인증번호를 더 입력할 수 있는 횟수(`detail.remaining_attempts`)입니다.
  final int? remainingAttempts;

  /// 인증번호 칸에 붙여 보여야 하는 오류인지 알려 줍니다.
  bool get isVerificationCodeError =>
      errorCode == AuthErrorCode.verificationCodeInvalid ||
      errorCode == AuthErrorCode.verificationCodeResendRequired;

  String get userMessage {
    // 인증번호 오류는 서버 문장('~습니다') 대신 앱 말투로 고릅니다(DECISIONS 170 ⑥).
    // 대기 시간이 든 TOO_MANY_ATTEMPTS 는 아래 badRequest 로 서버 문구를 그대로 씁니다.
    switch (errorCode) {
      case AuthErrorCode.verificationCodeInvalid:
        final remaining = remainingAttempts;
        return remaining == null
            ? '인증번호가 맞지 않아요. 다시 확인해 주세요.'
            : '인증번호가 맞지 않아요. $remaining번 더 입력할 수 있어요.';
      case AuthErrorCode.verificationCodeResendRequired:
        return '이 인증번호는 더 쓸 수 없어요. 인증번호를 다시 받아 주세요.';
      case AuthErrorCode.emailCodeResendTooSoon:
        final retryAfter = retryAfterSeconds;
        return retryAfter == null
            ? '인증번호는 잠시 후에 다시 받을 수 있어요.'
            : '인증번호는 ${formatAuthWait(retryAfter)} 후에 다시 받을 수 있어요.';
      case AuthErrorCode.emailSendUnavailable:
        return '지금은 인증 메일을 보낼 수 없어요. 나중에 다시 시도해 주세요.';
      // 카카오 오류도 앱 말투로 고릅니다. 로그인 API 의 401 이 이메일 로그인 문구
      // ('이메일 또는 비밀번호…')로, 502·503 이 서버 오류 문구로 보이지 않게 합니다.
      case AuthErrorCode.socialTokenInvalid:
        return '카카오 로그인을 확인하지 못했어요. 카카오 로그인부터 다시 해 주세요.';
      case AuthErrorCode.socialAccountMismatch:
        return '가입한 카카오 계정이 아니에요. 가입한 카카오 계정으로 다시 확인해 주세요.';
      case AuthErrorCode.socialProviderUnavailable:
        return '카카오가 응답하지 않아요. 잠시 후 다시 시도해 주세요.';
      case AuthErrorCode.socialLoginUnavailable:
        return '지금은 카카오 로그인을 쓸 수 없어요.';
    }

    switch (type) {
      case AuthApiErrorType.badRequest:
      case AuthApiErrorType.unauthorized:
      case AuthApiErrorType.conflict:
        return message;
      case AuthApiErrorType.forbidden:
        return '이 기능을 사용할 권한이 없어요. 계속되면 관리자에게 문의해 주세요.';
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
    final body = _decodeObject(responseBody);
    final serverMessage = _extractServerMessage(body);
    final detail = body?['detail'];
    final detailMap = detail is Map ? detail : null;
    final rawErrorCode = body?['error_code'] ?? detailMap?['error_code'];
    final errorCode = rawErrorCode is String && rawErrorCode.isNotEmpty
        ? rawErrorCode
        : null;
    final retryAfterSeconds = _parseNonNegativeInt(detailMap?['retry_after']);
    final remainingAttempts = _parseNonNegativeInt(
      detailMap?['remaining_attempts'],
    );

    AuthApiException build(AuthApiErrorType type, String fallbackMessage) {
      return AuthApiException(
        type: type,
        statusCode: statusCode,
        message: serverMessage ?? fallbackMessage,
        errorCode: errorCode,
        retryAfterSeconds: retryAfterSeconds,
        remainingAttempts: remainingAttempts,
      );
    }

    switch (statusCode) {
      case 400:
      case 422:
        return build(AuthApiErrorType.badRequest, '입력한 계정 정보를 다시 확인해 주세요.');
      case 401:
        return build(AuthApiErrorType.unauthorized, '이메일 또는 비밀번호가 올바르지 않아요.');
      // 403은 재로그인으로 해결되지 않는 '권한 없음'으로 예약합니다.
      case 403:
        return build(AuthApiErrorType.forbidden, '접근 권한이 없습니다.');
      case 409:
        return build(AuthApiErrorType.conflict, '이미 가입된 이메일이에요.');
      // 로그인 시도 제한(잠금). 서버가 보내는 대기 안내를 그대로 보여줍니다.
      case 429:
        return build(
          AuthApiErrorType.badRequest,
          '로그인 시도가 너무 많아요. 잠시 후 다시 시도해 주세요.',
        );
      default:
        if (statusCode >= 500) {
          return build(AuthApiErrorType.server, '서버 내부 오류입니다.');
        }

        return build(AuthApiErrorType.unknown, '인증 요청을 처리하지 못했습니다.');
    }
  }

  @override
  String toString() {
    if (statusCode == null) {
      return 'AuthApiException($type): $message';
    }

    return 'AuthApiException($type, statusCode: $statusCode): $message';
  }

  static Map<String, dynamic>? _decodeObject(String responseBody) {
    try {
      final decoded = jsonDecode(responseBody);
      return decoded is Map<String, dynamic> ? decoded : null;
    } catch (_) {
      return null;
    }
  }

  static String? _extractServerMessage(Map<String, dynamic>? decoded) {
    if (decoded == null) return null;

    final detail = decoded['detail'];
    final message =
        decoded['message'] ??
        decoded['error'] ??
        decoded['reason'] ??
        (detail is String ? detail : null);

    if (message != null && message.toString().trim().isNotEmpty) {
      return message.toString().trim();
    }

    return null;
  }

  static int? _parseNonNegativeInt(dynamic value) {
    final parsed = switch (value) {
      int() => value,
      num() => value.ceil(),
      String() => int.tryParse(value.trim()),
      _ => null,
    };

    return parsed != null && parsed >= 0 ? parsed : null;
  }
}

/// 인증번호를 어디에 쓸지(`POST /auth/email-code` 의 `purpose`)입니다.
enum EmailCodePurpose {
  signup('signup'),
  passwordReset('password_reset');

  const EmailCodePurpose(this.apiValue);

  final String apiValue;
}

/// 인증번호 요청이 받아들여졌을 때 서버가 알려 주는 시간입니다.
class EmailCodeRequestResult {
  const EmailCodeRequestResult({
    required this.expiresInSeconds,
    required this.resendAfterSeconds,
  });

  /// 번호 유효 시간(초)입니다.
  final int expiresInSeconds;

  /// 다시 요청할 수 있을 때까지 남은 시간(초)입니다. 한도에 닿으면 최대 약 24시간입니다.
  final int resendAfterSeconds;
}

/// 인증 응답에 포함된 최소 사용자 프로필 DTO입니다.
class AuthUser {
  const AuthUser({
    required this.id,
    required this.email,
    required this.nickname,
    this.loginMethods = const [LoginMethod.password],
  });

  final int id;

  /// 카카오 계정은 이메일이 없어 null 입니다.
  final String? email;
  final String nickname;

  /// 이 계정으로 로그인하는 방법(`login_methods`)입니다.
  final List<String> loginMethods;

  /// 비밀번호로 로그인하는 계정인지 — 비밀번호 변경·탈퇴 확인 방식을 고릅니다.
  bool get hasPasswordLogin => loginMethods.contains(LoginMethod.password);

  /// id·닉네임이 빠진 응답은 [FormatException]으로 거부합니다.
  ///
  /// `login_methods` 가 없으면(그 칸이 생기기 전 서버) 이메일이 있을 때 비밀번호 계정으로 봅니다.
  factory AuthUser.fromJson(Map<String, dynamic> json) {
    final id = _parseInt(json['id']);
    final email = json['email']?.toString().trim() ?? '';
    final nickname = json['nickname']?.toString().trim() ?? '';

    if (id == null || nickname.isEmpty) {
      throw const FormatException('사용자 정보 응답이 올바르지 않습니다.');
    }

    final rawLoginMethods = json['login_methods'];
    final loginMethods = rawLoginMethods is List
        ? List<String>.unmodifiable(rawLoginMethods.whereType<String>())
        : email.isEmpty
        ? const <String>[]
        : const [LoginMethod.password];

    return AuthUser(
      id: id,
      email: email.isEmpty ? null : email,
      nickname: nickname,
      loginMethods: loginMethods,
    );
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
    this.isNewUser = false,
  });

  final AuthUser user;
  final String? accessToken;
  final String? tokenType;
  final int? expiresInSeconds;

  /// 카카오 로그인으로 계정이 방금 만들어졌는지(`is_new_user`)입니다. 다른 응답은 거짓입니다.
  final bool isNewUser;
}

/// 현재 사용자와 서버 분석 이력을 함께 전달하는 세션 DTO입니다.
class AuthSessionSnapshot {
  const AuthSessionSnapshot({required this.user, required this.history});

  final AuthUser user;
  final List<AnalysisHistoryRecord> history;
}
