import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../config/api_environment.dart';
import '../models/scan_result.dart';
import 'api_http.dart';

/// 스캔 API 오류를 화면 안내와 후속 처리 분기에 사용할 범주로 구분한다.
enum ScanApiErrorType {
  badRequest,
  unauthorized,
  forbidden,
  payloadTooLarge,
  unsupportedMediaType,
  ocrFailed,
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
    this.partialMaterials = const {},
    this.careInstruction,
    this.rawOcrPreview,
  });

  final ScanApiErrorType type;
  final String message;
  final int? statusCode;

  /// 서버가 오류 본문(detail)에 함께 실어 보낸 부분 인식 결과다.
  /// 자동 분석이 실패해도 직접 입력 폼을 처음부터 채우지 않도록 보존한다.
  /// 서버가 보내지 않으면 비어 있으며, 그때는 기존 빈 폼과 동작이 같다.
  final Map<String, double> partialMaterials;

  /// 서버가 라벨에서 읽어낸 관리 지침이다. 값이 없으면 null이다.
  final String? careInstruction;

  /// 서버가 인식한 라벨 원문 미리보기다. 값이 없으면 null이다.
  final String? rawOcrPreview;

  String get userMessage {
    switch (type) {
      case ScanApiErrorType.badRequest:
        return '사진을 처리하지 못했어요. 다른 사진을 선택해 다시 시도해 주세요.';
      case ScanApiErrorType.unauthorized:
        return '로그인 정보가 만료되었어요. 다시 로그인한 뒤 스캔해 주세요.';
      case ScanApiErrorType.forbidden:
        return '이 기능을 사용할 권한이 없어요. 계속되면 관리자에게 문의해 주세요.';
      case ScanApiErrorType.payloadTooLarge:
        return '사진 용량이 너무 커요. 사진을 줄이거나 다른 사진을 선택해 주세요.';
      case ScanApiErrorType.unsupportedMediaType:
        return '이 사진 형식은 분석할 수 없어요. JPG 또는 PNG 사진을 사용해 주세요.';
      case ScanApiErrorType.ocrFailed:
        return '라벨을 자동으로 인식하지 못했어요. 소재와 혼용률을 직접 입력해 주세요.';
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
  ///
  /// 오류 본문에 부분 인식 결과가 실려 있으면 함께 보존해, 직접 입력 흐름이
  /// 이미 인식된 값을 버리지 않도록 한다.
  factory ScanApiException.fromStatusCode({
    required int statusCode,
    required String responseBody,
  }) {
    final decoded = _decodeResponseBody(responseBody);
    final detail = _extractErrorDetail(decoded);
    final serverMessage = _extractServerMessage(decoded);

    ScanApiException build(ScanApiErrorType type, String fallbackMessage) {
      return ScanApiException(
        type: type,
        statusCode: statusCode,
        message: serverMessage ?? fallbackMessage,
        partialMaterials: _extractPartialMaterials(detail),
        careInstruction: _readDetailText(detail, const [
          'care_instruction',
          'careInstruction',
        ]),
        rawOcrPreview: _readDetailText(detail, const [
          'raw_ocr_preview',
          'rawOcrPreview',
        ]),
      );
    }

    switch (statusCode) {
      case 400:
        return build(ScanApiErrorType.badRequest, '잘못된 이미지 요청입니다.');
      case 401:
        return build(ScanApiErrorType.unauthorized, '로그인이 필요합니다.');
      // 403은 재로그인으로 해결되지 않는 '권한 없음'으로 예약되어 있어
      // 세션을 지우지 않고 안내만 합니다.
      case 403:
        return build(ScanApiErrorType.forbidden, '접근 권한이 없습니다.');
      case 413:
        return build(ScanApiErrorType.payloadTooLarge, '이미지 용량이 너무 큽니다.');
      case 415:
        return build(
          ScanApiErrorType.unsupportedMediaType,
          '지원하지 않는 이미지 형식입니다.',
        );
      case 422:
        return build(
          ScanApiErrorType.aiRecognitionFailed,
          'AI가 라벨을 인식하지 못했습니다.',
        );
      // 백엔드 계약상 502는 OCR 처리 실패다. 422(소재 추출 실패)와 원인이 다르므로
      // 타입을 분리하되, 안내는 두 경우 모두 직접 입력으로 유도한다
      // (재촬영은 화면의 '다시 촬영' 버튼으로 별도 제공).
      case 502:
        return build(ScanApiErrorType.ocrFailed, 'AI OCR 처리에 실패했습니다.');
      // AI 파트가 요청한 504 OCR_TIMEOUT 대응이다. 백엔드는 아직 504를 내지
      // 않지만, 내기 시작하면 일반 서버 오류가 아니라 시간 초과 안내로 보낸다.
      case 504:
        return build(ScanApiErrorType.timeout, '분석 요청 시간이 초과되었습니다.');
      default:
        if (statusCode >= 500) {
          return build(ScanApiErrorType.server, '서버 내부 오류입니다.');
        }

        return build(ScanApiErrorType.unknown, '알 수 없는 서버 오류입니다.');
    }
  }

  @override
  String toString() {
    if (statusCode == null) {
      return 'ScanApiException($type): $message';
    }

    return 'ScanApiException($type, statusCode: $statusCode): $message';
  }

  static Map<String, dynamic>? _decodeResponseBody(String responseBody) {
    try {
      final decoded = jsonDecode(responseBody);

      return decoded is Map<String, dynamic> ? decoded : null;
    } catch (_) {
      return null;
    }
  }

  /// 백엔드 공통 오류 처리기는 원본을 detail에 담고 message만 위로 올린다.
  /// detail이 없거나 문자열이면 본문 자체에서 읽는다.
  static Map<String, dynamic> _extractErrorDetail(
    Map<String, dynamic>? decoded,
  ) {
    if (decoded == null) return const {};

    final detail = decoded['detail'];

    return detail is Map<String, dynamic> ? detail : decoded;
  }

  static String? _extractServerMessage(Map<String, dynamic>? decoded) {
    if (decoded == null) return null;

    final detail = decoded['detail'];
    final candidates = <dynamic>[
      decoded['message'],
      if (detail is Map) detail['message'] else detail,
      decoded['error'],
      decoded['reason'],
    ];

    for (final candidate in candidates) {
      final text = candidate?.toString().trim();

      if (text != null && text.isNotEmpty) {
        return text;
      }
    }

    return null;
  }

  /// 비율이 숫자가 아니거나 음수인 항목은 폼에서 고칠 수 없는 값이므로 버린다.
  /// (백엔드는 NaN 비율을 null로 바꿔 돌려주므로 그 경우도 여기서 걸러진다.)
  static Map<String, double> _extractPartialMaterials(
    Map<String, dynamic> detail,
  ) {
    final rawMaterials =
        detail['partial_materials'] ??
        detail['partialMaterials'] ??
        detail['materials'];

    if (rawMaterials is! Map) return const {};

    final materials = <String, double>{};

    rawMaterials.forEach((key, value) {
      final name = key.toString().trim();
      final ratio = value is num
          ? value.toDouble()
          : double.tryParse(value.toString().replaceAll('%', '').trim());

      if (name.isEmpty || ratio == null || !ratio.isFinite || ratio < 0) return;

      materials[name] = ratio;
    });

    return Map.unmodifiable(materials);
  }

  static String? _readDetailText(
    Map<String, dynamic> detail,
    List<String> keys,
  ) {
    for (final key in keys) {
      final text = detail[key]?.toString().trim();

      if (text != null && text.isNotEmpty) {
        return text;
      }
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
    try {
      final response = await runImageUploadRequest(
        uri: Uri.parse(endpoint),
        headers: requestHeaders,
        timeout: _requestTimeout,
        imageFile: imageFile,
        fieldName: 'image',
        accessToken: accessToken,
        client: client,
      );

      if (!response.isSuccess) {
        throw ScanApiException.fromStatusCode(
          statusCode: response.statusCode,
          responseBody: response.body,
        );
      }

      return _parseScanResult(response.body);
    } on ScanApiException {
      rethrow;
    } on ApiTransportException catch (e) {
      throw switch (e.type) {
        ApiTransportErrorType.network => ScanApiException(
          type: ScanApiErrorType.network,
          message: e.message,
        ),
        ApiTransportErrorType.timeout => const ScanApiException(
          type: ScanApiErrorType.timeout,
          message: '분석 요청 시간이 초과되었습니다.',
        ),
      };
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
    if (decoded['ai_success'] == false || payload['ai_success'] == false) {
      throw ScanApiException(
        type: ScanApiErrorType.aiRecognitionFailed,
        statusCode: 200,
        message:
            ScanApiException._extractServerMessage(payload) ??
            ScanApiException._extractServerMessage(decoded) ??
            '라벨을 일부만 인식했습니다.',
        partialMaterials: ScanApiException._extractPartialMaterials(payload),
        careInstruction: ScanApiException._readDetailText(payload, const [
          'care_instruction',
          'careInstruction',
        ]),
        rawOcrPreview: ScanApiException._readDetailText(payload, const [
          'raw_ocr_preview',
          'rawOcrPreview',
        ]),
      );
    }
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
