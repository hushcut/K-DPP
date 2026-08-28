// 모든 API 서비스가 공유하는 HTTP 전송 계층입니다.
// 클라이언트 생명주기, 타임아웃, UTF-8 디코딩, 전송 오류 분류를 한곳에서 처리해
// 서비스마다 복사되던 요청 골격이 서로 어긋나지 않게 합니다.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

/// 주입된 클라이언트가 없을 때 앱 수명 동안 재사용하는 공용 클라이언트입니다.
/// 연결(keep-alive)을 재사용해 요청마다 TCP/TLS 연결 비용을 내지 않게 합니다.
final http.Client _sharedApiClient = http.Client();

/// 여러 서비스가 공유하는 기본 JSON 요청 헤더입니다.
const Map<String, String> kDefaultJsonApiHeaders = {
  'Content-Type': 'application/json',
  'Accept': 'application/json',
  'ngrok-skip-browser-warning': 'true',
};

/// 상태 코드 해석 이전, 전송 단계에서 발생한 오류의 분류입니다.
enum ApiTransportErrorType { network, timeout }

/// 전송 단계 오류(연결 끊김·시간 초과)를 각 서비스의 예외로 바꾸기 전의
/// 공통 표현입니다. 서비스는 이 예외를 받아 자신의 오류 유형으로 변환합니다.
class ApiTransportException implements Exception {
  const ApiTransportException({required this.type, required this.message});

  final ApiTransportErrorType type;
  final String message;

  @override
  String toString() => 'ApiTransportException($type): $message';
}

/// 상태 코드와 UTF-8로 디코딩한 본문만 담는 공통 응답입니다.
class ApiHttpResponse {
  const ApiHttpResponse({required this.statusCode, required this.body});

  final int statusCode;
  final String body;

  bool get isSuccess => statusCode >= 200 && statusCode < 300;
}

/// JSON 기반 GET/POST 요청을 실행합니다.
/// 주입된 [client]가 없으면 임시 클라이언트를 만들고 요청 후 닫습니다.
/// 연결·시간 초과 오류는 [ApiTransportException]으로 통일해 던집니다.
Future<ApiHttpResponse> runJsonApiRequest({
  required String method,
  required Uri uri,
  required Map<String, String> headers,
  required Duration timeout,
  Object? jsonBody,
  String? accessToken,
  http.Client? client,
}) async {
  final activeClient = client ?? _sharedApiClient;
  final requestHeaders = {
    ...headers,
    if (accessToken != null && accessToken.isNotEmpty)
      'Authorization': 'Bearer $accessToken',
  };

  try {
    final http.Response response;

    if (method == 'GET') {
      response = await activeClient
          .get(uri, headers: requestHeaders)
          .timeout(timeout);
    } else {
      response = await activeClient
          .post(
            uri,
            headers: requestHeaders,
            body: jsonBody == null ? null : jsonEncode(jsonBody),
          )
          .timeout(timeout);
    }

    return ApiHttpResponse(
      statusCode: response.statusCode,
      body: utf8.decode(response.bodyBytes),
    );
  } on SocketException catch (error) {
    throw ApiTransportException(
      type: ApiTransportErrorType.network,
      message: error.message,
    );
  } on http.ClientException catch (error) {
    throw ApiTransportException(
      type: ApiTransportErrorType.network,
      message: error.message,
    );
  } on TimeoutException {
    throw const ApiTransportException(
      type: ApiTransportErrorType.timeout,
      message: '요청 시간이 초과되었습니다.',
    );
  }
}

/// 이미지 파일을 multipart로 업로드합니다.
/// send()는 응답 헤더가 오면 완료되므로, 본문 수신이 중간에 멈춰도
/// 무한 대기하지 않도록 헤더와 본문 읽기 모두에 [timeout]을 적용합니다.
Future<ApiHttpResponse> runImageUploadRequest({
  required Uri uri,
  required Map<String, String> headers,
  required Duration timeout,
  required File imageFile,
  required String fieldName,
  String? accessToken,
  http.Client? client,
}) async {
  final request = http.MultipartRequest('POST', uri)
    ..headers.addAll(headers)
    ..files.add(
      await http.MultipartFile.fromPath(
        fieldName,
        imageFile.path,
        // Content-Type을 명시하지 않으면 application/octet-stream으로 전송되어
        // 서버의 이미지 형식 검사(415)에 걸리므로 확장자 기준으로 지정한다.
        contentType: imageMediaTypeForPath(imageFile.path),
      ),
    );

  if (accessToken != null && accessToken.isNotEmpty) {
    request.headers['Authorization'] = 'Bearer $accessToken';
  }

  try {
    final streamedResponse = await (client ?? _sharedApiClient)
        .send(request)
        .timeout(timeout);
    final body = await streamedResponse.stream.bytesToString().timeout(timeout);

    return ApiHttpResponse(statusCode: streamedResponse.statusCode, body: body);
  } on SocketException catch (error) {
    throw ApiTransportException(
      type: ApiTransportErrorType.network,
      message: error.message,
    );
  } on http.ClientException catch (error) {
    throw ApiTransportException(
      type: ApiTransportErrorType.network,
      message: error.message,
    );
  } on TimeoutException {
    throw const ApiTransportException(
      type: ApiTransportErrorType.timeout,
      message: '요청 시간이 초과되었습니다.',
    );
  }
}

/// 서버가 지원하는 형식(jpeg/png/webp)만 구분하고, 카메라 기본 출력이
/// JPEG이므로 그 외 확장자는 image/jpeg로 처리합니다.
MediaType imageMediaTypeForPath(String path) {
  final extension = path.toLowerCase().split('.').last;

  switch (extension) {
    case 'png':
      return MediaType('image', 'png');
    case 'webp':
      return MediaType('image', 'webp');
    default:
      return MediaType('image', 'jpeg');
  }
}
