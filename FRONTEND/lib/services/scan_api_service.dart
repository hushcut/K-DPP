import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../config/api_environment.dart';
import '../models/scan_result.dart';

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

class ScanApiService {
  ScanApiService({
    String? endpoint,
    this.requestHeaders = const {'ngrok-skip-browser-warning': 'true'},
    this.client,
  }) : endpoint = endpoint ?? ApiEnvironment.scanEndpoint;

  final String endpoint;
  final Map<String, String> requestHeaders;
  final http.Client? client;

  Future<ScanResult> scanLabel({required File imageFile}) async {
    final uri = Uri.parse(endpoint);

    try {
      final request = http.MultipartRequest('POST', uri)
        ..headers.addAll(requestHeaders)
        ..files.add(await http.MultipartFile.fromPath('image', imageFile.path));

      final streamedResponse = await (client?.send(request) ?? request.send())
          .timeout(const Duration(seconds: 35));

      final responseBody = await streamedResponse.stream.bytesToString();

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
