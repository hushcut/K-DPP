// 회원가입·비밀번호 찾기 화면이 함께 쓰는 입력 검사입니다.
// 서버(main.py `ensure_email_format`·`ensure_password_rules`)보다 느슨하거나 같게 두어
// 서버가 받는 값을 앱이 막지 않게 합니다.

/// 이메일이 비었거나 '@'·'.' 이 없으면 오류 문장을 돌려줍니다.
String? validateEmailInput(String? value) {
  final text = value?.trim() ?? '';

  if (text.isEmpty) {
    return '이메일을 입력해 주세요';
  }

  if (!text.contains('@') || !text.contains('.')) {
    return '올바른 이메일 형식을 입력해 주세요';
  }

  return null;
}

/// 새로 정하는 비밀번호의 규칙(8자 이상, 앞뒤 공백 없음)을 검사합니다.
///
/// 서버에는 입력값을 그대로 보내므로 검증도 trim 없이 같은 값으로 수행합니다.
String? validateNewPassword(String? value) {
  final text = value ?? '';

  if (text.trim().isEmpty) {
    return '비밀번호를 입력해 주세요';
  }

  if (text != text.trim()) {
    return '비밀번호 앞뒤 공백은 사용할 수 없어요';
  }

  if (text.length < 8) {
    return '비밀번호는 8자 이상 입력해 주세요';
  }

  return null;
}

/// 비밀번호 확인 칸이 [password] 와 글자 그대로 같은지 검사합니다.
String? validatePasswordConfirmation(String? value, String password) {
  final text = value ?? '';

  if (text.trim().isEmpty) {
    return '비밀번호 확인을 입력해 주세요';
  }

  if (text != password) {
    return '비밀번호가 일치하지 않습니다';
  }

  return null;
}

/// 이메일로 받은 인증번호 칸을 검사합니다. 서버도 앞뒤 공백을 지우고 숫자 6자리만 받습니다.
String? validateVerificationCode(String? value) {
  final text = value?.trim() ?? '';

  if (text.isEmpty) {
    return '인증번호를 받아 입력해 주세요';
  }

  if (!RegExp(r'^\d{6}$').hasMatch(text)) {
    return '인증번호 6자리를 입력해 주세요';
  }

  return null;
}
