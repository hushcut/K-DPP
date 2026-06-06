import 'dart:convert';

import 'package:http/http.dart' as http;

import 'auth_session_service.dart';

class CarbonCalculation {
  const CarbonCalculation({
    required this.midpoint,
    required this.min,
    required this.max,
  });

  final double midpoint;
  final double min;
  final double max;
}

class CarbonApiException implements Exception {
  const CarbonApiException(this.message);

  final String message;

  @override
  String toString() => message;
}

class CarbonApiService {
  const CarbonApiService({
    this.endpoint = const String.fromEnvironment(
      'CARBON_API_ENDPOINT',
      defaultValue: 'http://10.0.2.2:8000/api/carbon/calculate',
    ),
    this.sessionService = const AuthSessionService(),
  });

  final String endpoint;
  final AuthSessionService sessionService;

  Future<CarbonCalculation> calculate({
    required Map<String, double> materials,
    required double minWeightGrams,
    required double maxWeightGrams,
  }) async {
    final accessToken = await sessionService.readAccessToken();
    if (accessToken == null || accessToken.isEmpty) {
      throw const CarbonApiException('로그인이 필요합니다. 다시 로그인해 주세요.');
    }

    final response = await http.post(
      Uri.parse(endpoint),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $accessToken',
        'ngrok-skip-browser-warning': 'true',
      },
      body: jsonEncode({
        'materials': materials,
        'min_weight_grams': minWeightGrams,
        'max_weight_grams': maxWeightGrams,
      }),
    );
    final rawBody = utf8.decode(response.bodyBytes);

    Map<String, dynamic> decoded;
    try {
      decoded = jsonDecode(rawBody) as Map<String, dynamic>;
    } catch (_) {
      throw const CarbonApiException('탄소배출량 계산 응답을 읽지 못했습니다.');
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw CarbonApiException(
        decoded['message']?.toString() ?? '탄소배출량 계산에 실패했습니다.',
      );
    }

    final midpoint = _parseDouble(decoded['carbon_footprint']);
    final min = _parseDouble(decoded['carbon_footprint_min']);
    final max = _parseDouble(decoded['carbon_footprint_max']);

    if (midpoint == null || min == null || max == null) {
      throw const CarbonApiException('탄소배출량 계산 결과 형식이 올바르지 않습니다.');
    }

    return CarbonCalculation(midpoint: midpoint, min: min, max: max);
  }

  static double? _parseDouble(dynamic value) {
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString() ?? '');
  }
}
