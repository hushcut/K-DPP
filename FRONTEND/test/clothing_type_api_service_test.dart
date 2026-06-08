import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:k_dpp/services/clothing_type_api_service.dart';

void main() {
  test('loads clothing weight options from the backend contract', () async {
    late http.Request capturedRequest;
    final client = MockClient((request) async {
      capturedRequest = request;
      return http.Response(
        jsonEncode({
          'status': 'success',
          'source': 'backend',
          'unit': 'g',
          'items': [
            {
              'id': 'short_sleeve_tshirt',
              'label': '반팔 티셔츠',
              'category': '상의',
              'min_weight_grams': 100,
              'max_weight_grams': 250,
              'estimated_weight_grams': 180,
            },
          ],
        }),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    });
    final service = ClothingTypeApiService(
      baseUrl: 'http://192.168.0.2:8000',
      client: client,
    );

    try {
      final options = await service.fetchOptions();

      expect(
        capturedRequest.url,
        Uri.parse('http://192.168.0.2:8000/clothing-types'),
      );
      expect(options, hasLength(2));
      expect(options.first.label, '반팔 티셔츠');
      expect(options.first.minWeightGram, 100);
      expect(options.first.maxWeightGram, 250);
      expect(options.first.estimatedWeightGram, 180);
      expect(options.last.isDirectWeightPlaceholder, isTrue);
    } finally {
      client.close();
    }
  });

  test('rejects an invalid clothing type response', () async {
    final client = MockClient(
      (_) async => http.Response(jsonEncode({'status': 'success'}), 200),
    );
    final service = ClothingTypeApiService(client: client);

    try {
      await expectLater(service.fetchOptions(), throwsFormatException);
    } finally {
      client.close();
    }
  });
}
