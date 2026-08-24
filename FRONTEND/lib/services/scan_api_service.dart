import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import '../config/api_environment.dart';
import '../models/scan_result.dart';

/// 스캔 API 오류를 화면 안내와 후속 처리 분기에 사용할 범주로 구분한다.
enum ScanApiErrorType {
  badRequest,
  unauthorized,
  payloadTooLarge,
  unsupportedMediaType,
  aiRecognitionFailed,
  server,
  network,
  timeout,
  invalidResponse,
  unknown,
}

/// HTTP 상태, 통신 오류, 응답 파싱 오류를 일관된 스캔 오류로 표현한다.
class ScanApiException implements Exception {
  const ScanApiException({
    required this.type,
    required this.message,
    this.statusCode,
  });

  final ScanApiErrorType type;
  final String message;
  final int? statusCode;

  String get userMessage {
    switch (type) {
      case ScanApiErrorType.badRequest:
        return '사진을 처리하지 못했어요. 다른 사진을 선택해 다시 시도해 주세요.';
      case ScanApiErrorType.unauthorized:
        return '로그인 정보가 만료되었어요. 다시 로그인한 뒤 스캔해 주세요.';
      case ScanApiErrorType.payloadTooLarge:
        return '사진 용량이 너무 커요. 사진을 줄이거나 다른 사진을 선택해 주세요.';
      case ScanApiErrorType.unsupportedMediaType:
        return '이 사진 형식은 분석할 수 없어요. JPG 또는 PNG 사진을 사용해 주세요.';
      case ScanApiErrorType.aiRecognitionFailed:
        return 'AI가 라벨 정보를 정확히 인식하지 못했어요. 소재와 혼용률을 직접 입력해 주세요.';
      case ScanApiErrorType.server:
        return '분석 서비스에 일시적인 문제가 생겼어요. 다시 시도하거나 직접 입력해 주세요.';
      case ScanApiErrorType.network:
        return '인터넷에 연결할 수 없어요. 연결을 확인하거나 직접 입력해 주세요.';
      case ScanApiErrorType.timeout:
        return '분석이 예상보다 오래 걸렸어요. 다시 시도하거나 직접 입력해 주세요.';
      case ScanApiErrorType.invalidResponse:
        return '분석 결과를 불러오지 못했어요. 소재와 혼용률을 직접 입력해 주세요.';
      case ScanApiErrorType.unknown:
        return '사진 분석을 완료하지 못했어요. 소재와 혼용률을 직접 입력해 주세요.';
    }
  }

  /// 실패한 HTTP 상태와 서버 메시지를 대응하는 오류 유형으로 변환한다.
  factory ScanApiException.fromStatusCode({
    required int statusCode,
    required String responseBody,
  }) {
    final serverMessage = _extractServerMessage(responseBody);

    switch (statusCode) {
      case 400:
        return ScanApiException(
          type: ScanApiErrorType.badRequest,
          statusCode: statusCode,
          message: serverMessage ?? '잘못된 이미지 요청입니다.',
        );
      case 401:
      case 403:
        return ScanApiException(
          type: ScanApiErrorType.unauthorized,
          statusCode: statusCode,
          message: serverMessage ?? '인증 또는 접근 권한 오류입니다.',
        );
      case 413:
        return ScanApiException(
          type: ScanApiErrorType.payloadTooLarge,
          statusCode: statusCode,
          message: serverMessage ?? '이미지 용량이 너무 큽니다.',
        );
      case 415:
        return ScanApiException(
          type: ScanApiErrorType.unsupportedMediaType,
          statusCode: statusCode,
          message: serverMessage ?? '지원하지 않는 이미지 형식입니다.',
        );
      case 422:
        return ScanApiException(
          type: ScanApiErrorType.aiRecognitionFailed,
          statusCode: statusCode,
          message: serverMessage ?? 'AI가 라벨을 인식하지 못했습니다.',
        );
      default:
        if (statusCode >= 500) {
          return ScanApiException(
            type: ScanApiErrorType.server,
            statusCode: statusCode,
            message: serverMessage ?? '서버 내부 오류입니다.',
          );
        }

        return ScanApiException(
          type: ScanApiErrorType.unknown,
          statusCode: statusCode,
          message: serverMessage ?? '알 수 없는 서버 오류입니다.',
        );
    }
  }

  @override
  String toString() {
    if (statusCode == null) {
      return 'ScanApiException($type): $message';
    }

    return 'ScanApiException($type, statusCode: $statusCode): $message';
  }

  static String? _extractServerMessage(String responseBody) {
    try {
      final decoded = jsonDecode(responseBody);

      if (decoded is Map<String, dynamic>) {
        final message =
            decoded['message'] ??
            decoded['detail'] ??
            decoded['error'] ??
            decoded['reason'];

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

/// 의류 라벨 이미지를 multipart 요청으로 전송하고 분석 결과를 파싱한다.
class ScanApiService {
  ScanApiService({
    String? endpoint,
    this.requestHeaders = const {'ngrok-skip-browser-warning': 'true'},
    this.client,
  }) : endpoint = endpoint ?? ApiEnvironment.scanEndpoint;

  final String endpoint;
  final Map<String, String> requestHeaders;
  final http.Client? client;

  static const Duration _requestTimeout = Duration(seconds: 35);

  /// 이미지를 전송해 [ScanResult]를 반환하며 네트워크·시간 초과·응답 오류를
  /// [ScanApiException]으로 통일한다.
  /// [accessToken]이 있으면 다른 API와 동일하게 Bearer 헤더를 첨부한다.
  Future<ScanResult> scanLabel({
    required File imageFile,
    String? accessToken,
  }) async {
    final uri = Uri.parse(endpoint);

    try {
      final request = http.MultipartRequest('POST', uri)
        ..headers.addAll(requestHeaders)
        ..files.add(
          await http.MultipartFile.fromPath(
            'image',
            imageFile.path,
            // Content-Type을 명시하지 않으면 application/octet-stream으로 전송되어
            // 서버의 이미지 형식 검사(415)에 걸리므로 확장자 기준으로 지정한다.
            contentType: _imageMediaTypeFor(imageFile.path),
          ),
        );

      if (accessToken != null && accessToken.isNotEmpty) {
        request.headers['Authorization'] = 'Bearer $accessToken';
      }

      final streamedResponse = await (client?.send(request) ?? request.send())
          .timeout(_requestTimeout);

      // send()는 응답 헤더가 오면 완료되므로, 본문 수신이 중간에 멈춰도
      // 무한 대기하지 않도록 본문 읽기에도 시간 제한을 둡니다.
      final responseBody = await streamedResponse.stream
          .bytesToString()
          .timeout(_requestTimeout);

      if (streamedResponse.statusCode < 200 ||
          streamedResponse.statusCode >= 300) {
        throw ScanApiException.fromStatusCode(
          statusCode: streamedResponse.statusCode,
          responseBody: responseBody,
        );
      }

      return _parseScanResult(responseBody);
    } on ScanApiException {
      rethrow;
    } on SocketException catch (e) {
      throw ScanApiException(
        type: ScanApiErrorType.network,
        message: e.message,
      );
    } on http.ClientException catch (e) {
      // 업로드 도중 끊긴 연결도 다른 서비스처럼 네트워크 오류로 안내한다.
      throw ScanApiException(
        type: ScanApiErrorType.network,
        message: e.message,
      );
    } on TimeoutException {
      throw const ScanApiException(
        type: ScanApiErrorType.timeout,
        message: '분석 요청 시간이 초과되었습니다.',
      );
    } on FormatException catch (e) {
      throw ScanApiException(
        type: ScanApiErrorType.invalidResponse,
        message: e.message,
      );
    } catch (e) {
      throw ScanApiException(
        type: ScanApiErrorType.unknown,
        message: e.toString(),
      );
    }
  }

  // 서버가 지원하는 형식(jpeg/png/webp)만 구분하고, 카메라 기본 출력이
  // JPEG이므로 그 외 확장자는 image/jpeg로 처리한다.
  static MediaType _imageMediaTypeFor(String path) {
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

  ScanResult _parseScanResult(String responseBody) {
    final decoded = jsonDecode(responseBody);

    if (decoded is! Map<String, dynamic>) {
      throw const ScanApiException(
        type: ScanApiErrorType.invalidResponse,
        message: '응답이 JSON 객체 형식이 아닙니다.',
      );
    }

    if (decoded['success'] == false || decoded['status'] == 'error') {
      throw ScanApiException(
        type: ScanApiErrorType.aiRecognitionFailed,
        message: decoded['message']?.toString() ?? 'AI 분석 실패',
      );
    }

    final payload = _extractPayload(decoded);
    final result = ScanResult.fromJson(payload);

    if (result.materials.isEmpty) {
      throw const ScanApiException(
        type: ScanApiErrorType.aiRecognitionFailed,
        message: '소재 정보를 인식하지 못했습니다.',
      );
    }

    return result;
  }

  Map<String, dynamic> _extractPayload(Map<String, dynamic> decoded) {
    final data = decoded['data'];
    final result = decoded['result'];

    if (data is Map<String, dynamic>) return data;
    if (result is Map<String, dynamic>) return result;

    return decoded;
  }
}
