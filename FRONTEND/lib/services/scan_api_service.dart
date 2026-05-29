import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
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
        return '이미지 요청 형식이 올바르지 않아요. 다른 사진으로 다시 시도해 주세요.';
      case ScanApiErrorType.unauthorized:
        return '서버 인증이 필요해요. 백엔드 설정을 확인해 주세요.';
      case ScanApiErrorType.payloadTooLarge:
        return '사진 용량이 너무 커요. 더 작은 이미지로 다시 시도해 주세요.';
      case ScanApiErrorType.unsupportedMediaType:
        return '지원하지 않는 이미지 형식이에요. JPG 또는 PNG 사진을 사용해 주세요.';
      case ScanApiErrorType.aiRecognitionFailed:
        return 'AI가 라벨 정보를 정확히 인식하지 못했어요. 소재와 혼용률을 직접 입력해 주세요.';
      case ScanApiErrorType.server:
        return '서버에서 문제가 발생했어요. 잠시 후 다시 시도하거나 직접 입력해 주세요.';
      case ScanApiErrorType.network:
        return '서버에 연결할 수 없어요. 네트워크 상태를 확인하거나 직접 입력해 주세요.';
      case ScanApiErrorType.timeout:
        return '분석 시간이 너무 오래 걸렸어요. 다시 시도하거나 직접 입력해 주세요.';
      case ScanApiErrorType.invalidResponse:
        return '서버 응답 형식이 올바르지 않아요. 직접 입력으로 계속 진행해 주세요.';
      case ScanApiErrorType.unknown:
        return '알 수 없는 오류가 발생했어요. 직접 입력으로 계속 진행해 주세요.';
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
        final message = decoded['message'] ??
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
  const ScanApiService({
    this.baseUrl = 'http://10.0.2.2:8000',
  });

  final String baseUrl;

  static const String _scanPath = '/scan';

  Future<ScanResult> scanLabel({
    required File imageFile,
  }) async {
    final uri = Uri.parse('$baseUrl$_scanPath');

    try {
      final request = http.MultipartRequest('POST', uri)
        ..files.add(
          await http.MultipartFile.fromPath(
            'image',
            imageFile.path,
          ),
        );

      final streamedResponse = await request.send().timeout(
        const Duration(seconds: 35),
      );

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

    if (decoded['success'] == false) {
      throw ScanApiException(
        type: ScanApiErrorType.aiRecognitionFailed,
        message: decoded['message']?.toString() ?? 'AI 분석 실패',
      );
    }

    final payload = _extractPayload(decoded);
    final materials = _parseMaterials(payload);

    if (materials.isEmpty) {
      throw const ScanApiException(
        type: ScanApiErrorType.aiRecognitionFailed,
        message: '소재 정보를 인식하지 못했습니다.',
      );
    }

    return ScanResult(
      title: _readOptionalString(payload, ['title', 'name', 'clothingName']),
      category: _readOptionalString(payload, ['category', 'type']),
      materials: materials,
      careInstruction: _readString(
        payload,
        ['careInstruction', 'care_instruction', 'care', 'washingInstruction'],
        fallback: '라벨의 세탁 지침을 확인해 주세요.',
      ),
    );
  }

  Map<String, dynamic> _extractPayload(Map<String, dynamic> decoded) {
    final data = decoded['data'];
    final result = decoded['result'];

    if (data is Map<String, dynamic>) return data;
    if (result is Map<String, dynamic>) return result;

    return decoded;
  }

  Map<String, double> _parseMaterials(Map<String, dynamic> payload) {
    final rawMaterials =
        payload['materials'] ?? payload['material'] ?? payload['composition'];

    final materials = <String, double>{};

    if (rawMaterials is Map) {
      rawMaterials.forEach((key, value) {
        final name = key.toString().trim();
        final percent = _parsePercent(value);

        if (name.isNotEmpty && percent != null) {
          materials[name] = percent;
        }
      });
    }

    if (rawMaterials is List) {
      for (final item in rawMaterials) {
        if (item is Map) {
          final name = (item['name'] ??
              item['material'] ??
              item['label'] ??
              item['type'])
              ?.toString()
              .trim();

          final percent = _parsePercent(
            item['percent'] ??
                item['percentage'] ??
                item['ratio'] ??
                item['value'],
          );

          if (name != null && name.isNotEmpty && percent != null) {
            materials[name] = percent;
          }
        }
      }
    }

    return materials;
  }

  double? _parsePercent(dynamic value) {
    if (value == null) return null;

    if (value is num) {
      return value.toDouble();
    }

    final text = value.toString().replaceAll('%', '').trim();
    return double.tryParse(text);
  }

  String? _readOptionalString(
      Map<String, dynamic> payload,
      List<String> keys,
      ) {
    for (final key in keys) {
      final value = payload[key];

      if (value != null && value.toString().trim().isNotEmpty) {
        return value.toString().trim();
      }
    }

    return null;
  }

  String _readString(
      Map<String, dynamic> payload,
      List<String> keys, {
        required String fallback,
      }) {
    return _readOptionalString(payload, keys) ?? fallback;
  }
}