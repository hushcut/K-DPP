import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:k_dpp/services/material_catalog_api_service.dart';

void main() {
  test('FastAPI 소재 기준표를 파싱하고 별칭 검색을 지원한다', () async {
    late http.Request capturedRequest;
    final client = MockClient((request) async {
      capturedRequest = request;

      return http.Response(
        jsonEncode([
          {
            'id': 1,
            'name_ko': '면',
            'name_en': 'cotton',
            'aliases': ['면', '코튼', 'cotton', 'COTTON'],
            'carbon_factor': 8.3,
            'unit': 'kg CO2eq/kg textile',
          },
          {
            'id': 2,
            'name_ko': '폴리에스터',
            'name_en': 'polyester',
            'aliases': ['폴리에스터', 'polyester', 'poly'],
            'carbon_factor': 9.5,
            'unit': 'kg CO2eq/kg textile',
          },
        ]),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    });
    final service = MaterialCatalogApiService(client: client);

    try {
      final materials = await service.fetchMaterials();

      expect(capturedRequest.method, 'GET');
      expect(capturedRequest.url, Uri.parse('http://10.0.2.2:8000/materials'));
      expect(capturedRequest.headers['ngrok-skip-browser-warning'], 'true');
      expect(materials, hasLength(2));
      expect(materials.first.label, '면 (cotton)');
      expect(materials.first.matches('코튼'), isTrue);
      expect(materials.last.matches('poly'), isTrue);
    } finally {
      client.close();
    }
  });

  test('필수 소재명이 없는 응답은 거부한다', () async {
    final client = MockClient(
      (_) async => http.Response(
        jsonEncode([
          {'id': 1, 'name_ko': '면', 'aliases': []},
        ]),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      ),
    );
    final service = MaterialCatalogApiService(client: client);

    try {
      await expectLater(
        service.fetchMaterials(),
        throwsA(isA<FormatException>()),
      );
    } finally {
      client.close();
    }
  });
}
