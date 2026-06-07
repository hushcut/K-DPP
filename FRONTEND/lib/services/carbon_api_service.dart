import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../config/api_environment.dart';

enum CarbonApiErrorType {
  badRequest,
  unauthorized,
  server,
  network,
  timeout,
  invalidResponse,
  unknown,
}

class CarbonApiException implements Exception {
  const CarbonApiException({
    required this.type,
    required this.message,
    this.statusCode,
    this.unknownMaterials = const [],
  });

  final CarbonApiErrorType type;
  final String message;
  final int? statusCode;
  final List<String> unknownMaterials;

  String get userMessage {
    switch (type) {
      case CarbonApiErrorType.badRequest:
        if (unknownMaterials.isNotEmpty) {
          return '탄소 기준 정보가 없는 소재가 있어요: ${unknownMaterials.join(', ')}. '
              '임시 추정값으로 저장했어요.';
        }
        return '입력한 소재 정보로 정확한 탄소량을 계산하지 못해 임시 추정값으로 저장했어요.';
      case CarbonApiErrorType.unauthorized:
        return '로그인 정보가 만료되어 임시 추정값으로 저장했어요. 다시 로그인해 주세요.';
      case CarbonApiErrorType.server:
        return '탄소 계산 서비스에 일시적인 문제가 생겨 임시 추정값으로 저장했어요.';
      case CarbonApiErrorType.network:
        return '인터넷에 연결할 수 없어 임시 추정값으로 저장했어요.';
      case CarbonApiErrorType.timeout:
        return '탄소 계산이 오래 걸려 임시 추정값으로 저장했어요.';
      case CarbonApiErrorType.invalidResponse:
        return '탄소 계산 결과를 확인하지 못해 임시 추정값으로 저장했어요.';
      case CarbonApiErrorType.unknown:
        return '정확한 탄소량을 계산하지 못해 임시 추정값으로 저장했어요.';
    }
  }

  factory CarbonApiException.fromStatusCode({
    required int statusCode,
    required String responseBody,
  }) {
    final error = _parseServerError(responseBody);

    switch (statusCode) {
      case 400:
      case 422:
        return CarbonApiException(
          type: CarbonApiErrorType.badRequest,
          statusCode: statusCode,
          message: error.message ?? '탄소 계산 요청값을 확인해 주세요.',
          unknownMaterials: error.unknownMaterials,
        );
      case 401:
      case 403:
        return CarbonApiException(
          type: CarbonApiErrorType.unauthorized,
          statusCode: statusCode,
          message: error.message ?? '로그인이 필요합니다.',
        );
      default:
        if (statusCode >= 500) {
          return CarbonApiException(
            type: CarbonApiErrorType.server,
            statusCode: statusCode,
            message: error.message ?? '서버 내부 오류입니다.',
          );
        }

        return CarbonApiException(
          type: CarbonApiErrorType.unknown,
          statusCode: statusCode,
          message: error.message ?? '탄소 계산 요청을 처리하지 못했습니다.',
        );
    }
  }

  @override
  String toString() {
    return 'CarbonApiException($type, statusCode: $statusCode): $message';
  }

  static _CarbonServerError _parseServerError(String responseBody) {
    try {
      final decoded = jsonDecode(responseBody);

      if (decoded is! Map<String, dynamic>) {
        return const _CarbonServerError();
      }

      final detail = decoded['detail'];
      final detailMap = detail is Map
          ? Map<String, dynamic>.from(detail)
          : null;
      final message =
          decoded['message']?.toString().trim() ??
          detailMap?['message']?.toString().trim() ??
          (detail is String ? detail.trim() : null);
      final rawUnknownMaterials =
          detailMap?['unknown_materials'] ?? decoded['unknown_materials'];
      final unknownMaterials = rawUnknownMaterials is List
          ? rawUnknownMaterials
                .map((item) => item.toString().trim())
                .where((item) => item.isNotEmpty)
                .toList()
          : const <String>[];

      return _CarbonServerError(
        message: message?.isEmpty == true ? null : message,
        unknownMaterials: unknownMaterials,
      );
    } catch (_) {
      return const _CarbonServerError();
    }
  }
}

class CarbonCalculationResult {
  const CarbonCalculationResult({
    required this.carbonFactor,
    required this.carbonFootprint,
    required this.carbonFootprintMin,
    required this.carbonFootprintMax,
    required this.minWeightGram,
    required this.maxWeightGram,
    required this.unit,
    required this.savedResultId,
  });

  final double carbonFactor;
  final double carbonFootprint;
  final double carbonFootprintMin;
  final double carbonFootprintMax;
  final double minWeightGram;
  final double maxWeightGram;
  final String unit;
  final int savedResultId;

  factory CarbonCalculationResult.fromJson(Map<String, dynamic> json) {
    final carbonFactor = _parseDouble(json['carbon_factor']);
    final carbonFootprint = _parseDouble(json['carbon_footprint']);
    final carbonFootprintMin = _parseDouble(json['carbon_footprint_min']);
    final carbonFootprintMax = _parseDouble(json['carbon_footprint_max']);
    final minWeightGram = _parseDouble(json['min_weight_grams']);
    final maxWeightGram = _parseDouble(json['max_weight_grams']);
    final unit = json['unit']?.toString().trim() ?? '';
    final savedResultId = _parseInt(json['saved_result_id']);

    if (carbonFactor == null ||
        carbonFootprint == null ||
        carbonFootprintMin == null ||
        carbonFootprintMax == null ||
        minWeightGram == null ||
        maxWeightGram == null ||
        unit.isEmpty ||
        savedResultId == null) {
      throw const FormatException('탄소 계산 결과가 올바르지 않습니다.');
    }

    return CarbonCalculationResult(
      carbonFactor: carbonFactor,
      carbonFootprint: carbonFootprint,
      carbonFootprintMin: carbonFootprintMin,
      carbonFootprintMax: carbonFootprintMax,
      minWeightGram: minWeightGram,
      maxWeightGram: maxWeightGram,
      unit: unit,
      savedResultId: savedResultId,
    );
  }

  static double? _parseDouble(dynamic value) {
    if (value is double) return value;
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString() ?? '');
  }

  static int? _parseInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '');
  }
}

class CarbonApiService {
  CarbonApiService({
    String? endpoint,
    this.requestHeaders = const {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'ngrok-skip-browser-warning': 'true',
    },
    this.requestTimeout = const Duration(seconds: 20),
    this.client,
  }) : endpoint = endpoint ?? ApiEnvironment.carbonEndpoint;

  final String endpoint;
  final Map<String, String> requestHeaders;
  final Duration requestTimeout;
  final http.Client? client;

  Future<CarbonCalculationResult> calculate({
    required Map<String, double> materials,
    required double minWeightGram,
    required double maxWeightGram,
    required String accessToken,
  }) async {
    final activeClient = client ?? http.Client();
    final shouldCloseClient = client == null;

    try {
      final response = await activeClient
          .post(
            Uri.parse(endpoint),
            headers: {
              ...requestHeaders,
              'Authorization': 'Bearer $accessToken',
            },
            body: jsonEncode({
              'materials': materials,
              'min_weight_grams': minWeightGram,
              'max_weight_grams': maxWeightGram,
            }),
          )
          .timeout(requestTimeout);
      final responseBody = utf8.decode(response.bodyBytes);

      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CarbonApiException.fromStatusCode(
          statusCode: response.statusCode,
          responseBody: responseBody,
        );
      }

      final decoded = jsonDecode(responseBody);

      if (decoded is! Map<String, dynamic>) {
        throw const FormatException('응답이 JSON 객체 형식이 아닙니다.');
      }

      return CarbonCalculationResult.fromJson(decoded);
    } on CarbonApiException {
      rethrow;
    } on SocketException catch (error) {
      throw CarbonApiException(
        type: CarbonApiErrorType.network,
        message: error.message,
      );
    } on http.ClientException catch (error) {
      throw CarbonApiException(
        type: CarbonApiErrorType.network,
        message: error.message,
      );
    } on TimeoutException {
      throw const CarbonApiException(
        type: CarbonApiErrorType.timeout,
        message: '탄소 계산 요청 시간이 초과되었습니다.',
      );
    } on FormatException catch (error) {
      throw CarbonApiException(
        type: CarbonApiErrorType.invalidResponse,
        message: error.message,
      );
    } catch (error) {
      throw CarbonApiException(
        type: CarbonApiErrorType.unknown,
        message: error.toString(),
      );
    } finally {
      if (shouldCloseClient) {
        activeClient.close();
      }
    }
  }
}

class _CarbonServerError {
  const _CarbonServerError({this.message, this.unknownMaterials = const []});

  final String? message;
  final List<String> unknownMaterials;
}
