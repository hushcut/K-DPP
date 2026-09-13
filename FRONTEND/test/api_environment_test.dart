import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/config/api_environment.dart';
import 'package:k_dpp/services/auth_api_service.dart';
import 'package:k_dpp/services/carbon_api_service.dart';
import 'package:k_dpp/services/material_catalog_api_service.dart';
import 'package:k_dpp/services/scan_api_service.dart';

void main() {
  test('all API services share the configured base URL', () {
    expect(AuthApiService().baseUrl, ApiEnvironment.authBaseUrl);
    expect(ScanApiService().endpoint, ApiEnvironment.scanEndpoint);
    expect(CarbonApiService().endpoint, ApiEnvironment.carbonEndpoint);
    expect(
      MaterialCatalogApiService().endpoint,
      ApiEnvironment.materialsEndpoint,
    );

    expect(ApiEnvironment.authBaseUrl, ApiEnvironment.baseUrl);
    expect(ApiEnvironment.scanEndpoint, '${ApiEnvironment.baseUrl}/api/scan');
    expect(
      ApiEnvironment.carbonEndpoint,
      '${ApiEnvironment.baseUrl}/api/carbon/calculate',
    );
    expect(
      ApiEnvironment.materialsEndpoint,
      '${ApiEnvironment.baseUrl}/materials',
    );
  });

  test('uses platform-specific local backend URLs', () {
    expect(
      ApiEnvironment.defaultBaseUrlFor(TargetPlatform.android),
      'http://10.0.2.2:8000',
    );
    expect(
      ApiEnvironment.defaultBaseUrlFor(TargetPlatform.iOS),
      'http://127.0.0.1:8000',
    );
  });

  test('normalizes a trailing slash so endpoint paths stay valid', () {
    expect(
      ApiEnvironment.normalizeBaseUrl('https://example.ngrok-free.app/'),
      'https://example.ngrok-free.app',
    );
    expect(
      ApiEnvironment.normalizeBaseUrl(' https://example.ngrok-free.app// '),
      'https://example.ngrok-free.app',
    );
    expect(
      ApiEnvironment.normalizeBaseUrl('http://10.0.2.2:8000'),
      'http://10.0.2.2:8000',
    );
  });
}
