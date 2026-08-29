import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:k_dpp/services/carbon_api_service.dart';

void main() {
  group('CarbonApiService configuration', () {
    test('uses the Android emulator endpoint by default', () {
      final service = CarbonApiService();

      expect(service.endpoint, 'http://10.0.2.2:8000/api/carbon/calculate');
    });
  });

  group('FastAPI carbon calculation contract', () {
    test('sends materials, weight range, and bearer token', () async {
      late http.Request capturedRequest;
      final client = MockClient((request) async {
        capturedRequest = request;

        return http.Response(
          jsonEncode({
            'status': 'success',
            'carbon_factor': 8.3,
            'carbon_footprint': 1.46,
            'carbon_footprint_min': 0.83,
            'carbon_footprint_max': 2.08,
            'min_weight_grams': 100,
            'max_weight_grams': 250,
            'unit': 'kg CO2eq',
            'saved_result_id': 21,
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      });
      final service = CarbonApiService(client: client);

      try {
        final result = await service.calculate(
          materials: const {'cotton': 100},
          minWeightGram: 100,
          maxWeightGram: 250,
          accessToken: 'access-token',
        );
        final requestBody =
            jsonDecode(capturedRequest.body) as Map<String, dynamic>;

        expect(capturedRequest.method, 'POST');
        expect(
          capturedRequest.url,
          Uri.parse('http://10.0.2.2:8000/api/carbon/calculate'),
        );
        expect(capturedRequest.headers['authorization'], 'Bearer access-token');
        expect(capturedRequest.headers['ngrok-skip-browser-warning'], 'true');
        expect(requestBody, {
          'materials': {'cotton': 100.0},
          'min_weight_grams': 100.0,
          'max_weight_grams': 250.0,
        });
        expect(result.carbonFactor, 8.3);
        expect(result.carbonFootprint, 1.46);
        expect(result.carbonFootprintMin, 0.83);
        expect(result.carbonFootprintMax, 2.08);
        expect(result.savedResultId, 21);
      } finally {
        client.close();
      }
    });

    test('평균 배출량과 계산 기준 설명 필드도 함께 파싱한다', () async {
      final client = MockClient(
        (_) async => http.Response(
          jsonEncode({
            'status': 'success',
            'carbon_factor': 8.3,
            'carbon_footprint': 1.46,
            'carbon_footprint_min': 0.83,
            'carbon_footprint_max': 2.08,
            'average_carbon_footprint': 1.45,
            'min_weight_grams': 100,
            'max_weight_grams': 250,
            'unit': 'kg CO2eq',
            'saved_result_id': 22,
            'weight_source': 'category_average',
            'calculation_scope': 'material_production_estimate',
            'calculation_basis': '소재 배출계수 × 의류 무게',
            'calculation_source': '소재별 공개 배출계수 정리표',
            'calculation_note': '운송·사용 단계는 포함하지 않습니다.',
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        ),
      );
      final service = CarbonApiService(client: client);

      try {
        final result = await service.calculate(
          materials: const {'cotton': 100},
          minWeightGram: 100,
          maxWeightGram: 250,
          accessToken: 'access-token',
        );

        expect(result.averageCarbonFootprint, 1.45);
        expect(result.weightSource, 'category_average');
        expect(result.calculationScope, 'material_production_estimate');
        expect(result.calculationBasis, '소재 배출계수 × 의류 무게');
        expect(result.calculationSource, '소재별 공개 배출계수 정리표');
        expect(result.calculationNote, '운송·사용 단계는 포함하지 않습니다.');
      } finally {
        client.close();
      }
    });

    test('maps an unauthenticated response to unauthorized', () async {
      final client = MockClient(
        (_) async => http.Response(
          jsonEncode({'status': 'error', 'message': '로그인이 필요합니다.'}),
          401,
          headers: {'content-type': 'application/json; charset=utf-8'},
        ),
      );
      final service = CarbonApiService(client: client);

      try {
        await expectLater(
          service.calculate(
            materials: const {'cotton': 100},
            minWeightGram: 100,
            maxWeightGram: 250,
            accessToken: 'expired-token',
          ),
          throwsA(
            isA<CarbonApiException>()
                .having(
                  (error) => error.type,
                  'type',
                  CarbonApiErrorType.unauthorized,
                )
                .having((error) => error.statusCode, 'statusCode', 401),
          ),
        );
      } finally {
        client.close();
      }
    });

    test('keeps unknown material names from a bad request', () async {
      final client = MockClient(
        (_) async => http.Response(
          jsonEncode({
            'status': 'error',
            'message': 'DB에 등록되지 않은 소재가 있습니다.',
            'detail': {
              'message': 'DB에 등록되지 않은 소재가 있습니다.',
              'unknown_materials': ['unknown_fiber'],
            },
          }),
          400,
          headers: {'content-type': 'application/json; charset=utf-8'},
        ),
      );
      final service = CarbonApiService(client: client);

      try {
        await expectLater(
          service.calculate(
            materials: const {'unknown_fiber': 100},
            minWeightGram: 100,
            maxWeightGram: 250,
            accessToken: 'access-token',
          ),
          throwsA(
            isA<CarbonApiException>()
                .having(
                  (error) => error.type,
                  'type',
                  CarbonApiErrorType.badRequest,
                )
                .having((error) => error.unknownMaterials, 'unknownMaterials', [
                  'unknown_fiber',
                ]),
          ),
        );
      } finally {
        client.close();
      }
    });

    test('rejects an incomplete success response', () async {
      final client = MockClient(
        (_) async => http.Response(
          jsonEncode({'status': 'success', 'carbon_footprint': 1.46}),
          200,
        ),
      );
      final service = CarbonApiService(client: client);

      try {
        await expectLater(
          service.calculate(
            materials: const {'cotton': 100},
            minWeightGram: 100,
            maxWeightGram: 250,
            accessToken: 'access-token',
          ),
          throwsA(
            isA<CarbonApiException>().having(
              (error) => error.type,
              'type',
              CarbonApiErrorType.invalidResponse,
            ),
          ),
        );
      } finally {
        client.close();
      }
    });
  });
}
