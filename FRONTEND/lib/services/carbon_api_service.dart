import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_environment.dart';
import '../utils/material_name.dart';
import 'api_http.dart';

/// 탄소 계산 API 오류를 사용자 안내와 대체 계산 정책에 사용할 범주로 구분한다.
enum CarbonApiErrorType {
  badRequest,
  unauthorized,
  forbidden,
  server,
  network,
  timeout,
  invalidResponse,
  unknown,
}

/// HTTP·통신·응답 오류와 서버가 알지 못한 소재 목록을 함께 전달한다.
class CarbonApiException implements Exception {
  const CarbonApiException({
    required this.type,
    required this.message,
    this.statusCode,
    this.errorCode,
    this.unknownMaterials = const [],
  });

  final CarbonApiErrorType type;
  final String message;
  final int? statusCode;

  /// 서버 응답의 `error_code` 입니다. 전송 오류처럼 응답이 없으면 null 입니다.
  final String? errorCode;
  final List<String> unknownMaterials;

  /// 서버 값 대신 앱 임시값으로 저장하면 안 되는 실패인지입니다. 404 는 서버에 이 계산 경로가
  /// 없다는 뜻이라(새 앱이 옛 서버에 붙음) 기다려도 풀리지 않고, 임시값은 나중에 서버 값으로
  /// 바뀌지 않으므로 막습니다. 코드 없는 503 같은 일반 장애는 지금처럼 임시 저장합니다.
  bool get blocksLocalEstimate =>
      statusCode == 404 || _blockingErrorCodes.contains(errorCode);

  static const Set<String> _blockingErrorCodes = {
    'CALCULATION_PROFILE_UNAVAILABLE',
    'CALCULATION_PROFILE_INVALID',
    'FACTOR_UNAVAILABLE',
    'FACTOR_INCOMPATIBLE',
    'FACTOR_INVALID',
    'COMPOSITION_SCOPE_UNSUPPORTED',
    'IDEMPOTENCY_CONFLICT',
    'V2_RESPONSE_INVALID',
  };

  // 서버가 무게 때문에 계산을 거절한 코드입니다(BACKEND/API_CONTRACT.md 주요 error_code).
  static const Set<String> _weightErrorCodes = {
    'WEIGHT_MISSING',
    'WEIGHT_INVALID',
    'WEIGHT_RANGE_INVALID',
  };

  /// 계산 기준이 없는 소재로 저장하지 못했을 때의 문장입니다. 서버가 거절했을 때와, 서버가 답하지
  /// 못해 앱 소재표로 막았을 때(DECISIONS 288) 같이 씁니다. '소재는' 을 붙여 소재 이름의 받침과
  /// 상관없이 조사가 맞게 합니다.
  static String unknownMaterialsMessage(List<String> names) {
    return '${MaterialName.summarize(names)} 소재는 탄소 계산 기준이 없어 저장하지 못했어요.';
  }

  /// 배너에 띄우는 문장입니다. 원인마다 길게 다르던 문장은 한 문장으로 줄이고,
  /// 기준 없는 소재·인터넷 끊김·로그인 만료만 따로 알립니다(DECISIONS 98).
  /// 입력 거절(400/422)은 저장하지 않으므로 저장하지 못했다고 알립니다(AI 연동 협의안 R1).
  String get userMessage {
    if (errorCode == 'CALCULATION_PROFILE_UNAVAILABLE' ||
        errorCode == 'CALCULATION_PROFILE_INVALID') {
      return '탄소 계산 기준이 아직 준비되지 않아 저장하지 못했어요. 잠시 후 다시 시도해 주세요.';
    }
    if (blocksLocalEstimate && type != CarbonApiErrorType.badRequest) {
      return '탄소 계산 근거를 확인할 수 없어 저장하지 못했어요. 잠시 후 다시 시도해 주세요.';
    }
    switch (type) {
      case CarbonApiErrorType.badRequest:
        if (unknownMaterials.isNotEmpty) {
          // 계수가 없다는 거절(FACTOR_UNAVAILABLE)은 서버가 표준명('cashmere')으로 돌려주므로
          // 한글명('캐시미어')으로 바꿉니다. 표준명이 아닌 이름은 받은 그대로입니다.
          return unknownMaterialsMessage(
            unknownMaterials.map(MaterialName.koreanForStandardName).toList(),
          );
        }
        // 무게 거절을 소재 문구로 안내하면 사용자가 고칠 곳을 찾지 못합니다.
        if (_weightErrorCodes.contains(errorCode)) {
          return '탄소량을 계산할 수 없어 저장하지 못했어요. 의류 무게를 확인해 주세요.';
        }
        return '탄소량을 계산할 수 없어 저장하지 못했어요. 소재와 혼용률을 확인해 주세요.';
      case CarbonApiErrorType.unauthorized:
        return '로그인이 만료됐어요. 탄소량은 임시 추정값으로 저장했어요.';
      case CarbonApiErrorType.network:
        return '인터넷에 연결할 수 없어 임시 추정값으로 저장했어요.';
      case CarbonApiErrorType.forbidden:
      case CarbonApiErrorType.server:
      case CarbonApiErrorType.timeout:
      case CarbonApiErrorType.invalidResponse:
      case CarbonApiErrorType.unknown:
        return _estimatedMessage;
    }
  }

  static const String _estimatedMessage = '탄소량은 임시 추정값으로 저장했어요.';

  /// HTTP 상태와 서버 오류 본문을 정규화된 탄소 API 예외로 변환한다.
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
          errorCode: error.errorCode,
          unknownMaterials: error.unknownMaterials,
        );
      case 401:
        return CarbonApiException(
          type: CarbonApiErrorType.unauthorized,
          statusCode: statusCode,
          message: error.message ?? '로그인이 필요합니다.',
        );
      // 403은 재로그인으로 해결되지 않는 '권한 없음'으로 예약되어 있어
      // 세션 만료 처리 대상에서 제외합니다.
      case 403:
        return CarbonApiException(
          type: CarbonApiErrorType.forbidden,
          statusCode: statusCode,
          message: error.message ?? '접근 권한이 없습니다.',
        );
      default:
        if (statusCode >= 500) {
          return CarbonApiException(
            type: CarbonApiErrorType.server,
            statusCode: statusCode,
            message: error.message ?? '서버 내부 오류입니다.',
            errorCode: error.errorCode,
          );
        }

        return CarbonApiException(
          type: CarbonApiErrorType.unknown,
          statusCode: statusCode,
          message: error.message ?? '탄소 계산 요청을 처리하지 못했습니다.',
          errorCode: error.errorCode,
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
      final rawErrorCode = decoded['error_code'] ?? detailMap?['error_code'];
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
        errorCode: rawErrorCode is String && rawErrorCode.isNotEmpty
            ? rawErrorCode
            : null,
        unknownMaterials: unknownMaterials,
      );
    } catch (_) {
      return const _CarbonServerError();
    }
  }
}

/// 서버가 계산하고 저장한 탄소 계수, 배출량 범위, 적용 무게를 담는다.
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
    this.averageCarbonFootprint,
    this.weightSource,
    this.calculationScope,
    this.calculationBasis,
    this.calculationSource,
    this.calculationNote,
  });

  final double carbonFactor;
  final double carbonFootprint;
  final double carbonFootprintMin;
  final double carbonFootprintMax;
  final double minWeightGram;
  final double maxWeightGram;
  final String unit;
  final int savedResultId;
  // 서버가 함께 내려주는 선택 필드: 평균 배출량과 계산 기준 설명입니다.
  final double? averageCarbonFootprint;
  final String? weightSource;
  final String? calculationScope;
  final String? calculationBasis;
  final String? calculationSource;
  final String? calculationNote;

  /// 숫자 필드를 변환하고 단위를 포함한 필수값이 누락되거나 형식이 잘못되면 [FormatException]을 던진다.
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
      averageCarbonFootprint: _parseDouble(json['average_carbon_footprint']),
      weightSource: _parseNullableString(json['weight_source']),
      calculationScope: _parseNullableString(json['calculation_scope']),
      calculationBasis: _parseNullableString(json['calculation_basis']),
      calculationSource: _parseNullableString(json['calculation_source']),
      calculationNote: _parseNullableString(json['calculation_note']),
    );
  }

  static double? _parseDouble(dynamic value) {
    if (value is double) return value;
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString() ?? '');
  }

  static String? _parseNullableString(dynamic value) {
    final text = value?.toString().trim();
    return text?.isNotEmpty == true ? text : null;
  }

  static int? _parseInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '');
  }
}

/// 인증된 사용자의 소재 구성과 유형 ID/실측 무게를 V2 탄소 계산 API에 전달한다.
class CarbonApiService {
  CarbonApiService({
    String? endpoint,
    this.requestHeaders = kDefaultJsonApiHeaders,
    this.requestTimeout = const Duration(seconds: 20),
    this.client,
  }) : endpoint = endpoint ?? ApiEnvironment.carbonEndpoint;

  final String endpoint;
  final Map<String, String> requestHeaders;
  final Duration requestTimeout;
  final http.Client? client;

  /// Bearer 토큰을 포함해 계산을 요청하고 모든 실패를 [CarbonApiException]으로 통일한다.
  /// 외부에서 클라이언트를 주입하지 않은 경우 요청 종료 시 직접 닫는다.
  ///
  /// [weightGram]은 사용자 입력 실측 무게로, [clothingTypeId]보다 우선한다.
  /// 유형 무게의 대표/범위는 서버 카탈로그에서 결정한다. min/maxWeightGram은
  /// 기존 화면 호출부 호환용이며 V2 요청 본문에는 전송하지 않는다.
  Future<CarbonCalculationResult> calculate({
    required Map<String, double> materials,
    required double minWeightGram,
    required double maxWeightGram,
    required String accessToken,
    double? weightGram,
    String? clothingTypeId,
  }) async {
    try {
      final response = await runJsonApiRequest(
        method: 'POST',
        uri: Uri.parse(endpoint),
        headers: requestHeaders,
        timeout: requestTimeout,
        jsonBody: {
          'materials': materials,
          'composition_scope': 'single',
          'clothing_type_id': ?clothingTypeId,
          'weight_grams': ?weightGram,
        },
        accessToken: accessToken,
        client: client,
      );

      if (!response.isSuccess) {
        throw CarbonApiException.fromStatusCode(
          statusCode: response.statusCode,
          responseBody: response.body,
        );
      }

      final decoded = jsonDecode(response.body);

      if (decoded is! Map<String, dynamic>) {
        throw const FormatException('응답이 JSON 객체 형식이 아닙니다.');
      }

      if (decoded['formula_version'] != 'fiber_mass_v2' ||
          decoded['calculation_scope'] != 'fiber_production_estimate' ||
          decoded['usage_scope'] != 'public_estimate' ||
          decoded['research_only'] != false ||
          decoded['calculation_source'] is! String ||
          (decoded['calculation_source'] as String).trim().isEmpty) {
        throw const CarbonApiException(
          type: CarbonApiErrorType.invalidResponse,
          errorCode: 'V2_RESPONSE_INVALID',
          message: '공개용 V2 계산 근거가 없는 응답입니다.',
        );
      }

      return CarbonCalculationResult.fromJson(decoded);
    } on CarbonApiException {
      rethrow;
    } on ApiTransportException catch (error) {
      throw switch (error.type) {
        ApiTransportErrorType.network => CarbonApiException(
          type: CarbonApiErrorType.network,
          message: error.message,
        ),
        ApiTransportErrorType.timeout => const CarbonApiException(
          type: CarbonApiErrorType.timeout,
          message: '탄소 계산 요청 시간이 초과되었습니다.',
        ),
      };
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
    }
  }
}

class _CarbonServerError {
  const _CarbonServerError({
    this.message,
    this.errorCode,
    this.unknownMaterials = const [],
  });

  final String? message;
  final String? errorCode;
  final List<String> unknownMaterials;
}
