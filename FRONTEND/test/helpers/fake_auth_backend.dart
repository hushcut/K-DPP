import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// 경로별로 응답을 정해 두고 받은 요청을 기록하는 가짜 인증 서버입니다.
///
/// 같은 경로에 응답을 여러 개 걸면 차례로 쓰고, 마지막 응답은 계속 씁니다.
class FakeAuthBackend {
  FakeAuthBackend() {
    client = MockClient((request) async {
      requests.add(request);

      final queue = _responses[request.url.path];
      if (queue == null || queue.isEmpty) {
        return jsonResponse({'detail': 'Not Found'}, 404);
      }

      final respond = queue.length > 1 ? queue.removeAt(0) : queue.first;
      return respond(request);
    });
  }

  late final MockClient client;
  final List<http.Request> requests = [];
  final Map<String, List<http.Response Function(http.Request)>> _responses = {};

  /// [path] 로 오는 다음 요청에 [response] 를 돌려줍니다.
  void on(String path, http.Response response) {
    _responses.putIfAbsent(path, () => []).add((_) => response);
  }

  /// [path] 로 온 요청 본문들입니다.
  List<Map<String, dynamic>> bodiesFor(String path) => [
    for (final request in requests)
      if (request.url.path == path)
        jsonDecode(request.body) as Map<String, dynamic>,
  ];
}

http.Response jsonResponse(Object body, int statusCode) {
  return http.Response(
    jsonEncode(body),
    statusCode,
    headers: {'content-type': 'application/json; charset=utf-8'},
  );
}

/// 서버(`main.py` http_exception_handler + build_error_detail)가 만드는 오류 봉투입니다.
http.Response serverErrorResponse(
  int statusCode,
  String errorCode,
  String message, {
  Map<String, Object> extra = const {},
}) {
  return jsonResponse({
    'status': 'error',
    'error_code': errorCode,
    'message': message,
    'detail': {'message': message, 'error_code': errorCode, ...extra},
  }, statusCode);
}

/// `POST /auth/email-code` 성공 응답입니다.
http.Response emailCodeSentResponse({
  int expiresIn = 600,
  int resendAfter = 60,
  String message = '인증번호를 보냈습니다. 메일이 오지 않으면 주소를 확인해 주세요.',
}) {
  return jsonResponse({
    'status': 'success',
    'message': message,
    'expires_in': expiresIn,
    'resend_after': resendAfter,
  }, 200);
}
