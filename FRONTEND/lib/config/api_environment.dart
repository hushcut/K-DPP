import 'package:flutter/foundation.dart';

abstract final class ApiEnvironment {
  static const String _baseUrlOverride = String.fromEnvironment('API_BASE_URL');
  static const String _authBaseUrlOverride = String.fromEnvironment(
    'AUTH_API_BASE_URL',
  );
  static const String _scanEndpointOverride = String.fromEnvironment(
    'SCAN_API_ENDPOINT',
  );
  static const String _carbonEndpointOverride = String.fromEnvironment(
    'CARBON_API_ENDPOINT',
  );
  static const String _materialsEndpointOverride = String.fromEnvironment(
    'MATERIALS_API_ENDPOINT',
  );

  static final String baseUrl = _baseUrlOverride.isNotEmpty
      ? _baseUrlOverride
      : defaultBaseUrlFor(defaultTargetPlatform);

  static String defaultBaseUrlFor(TargetPlatform platform) {
    return platform == TargetPlatform.android
        ? 'http://10.0.2.2:8000'
        : 'http://127.0.0.1:8000';
  }

  static final String authBaseUrl = _authBaseUrlOverride.isNotEmpty
      ? _authBaseUrlOverride
      : baseUrl;

  static final String scanEndpoint = _scanEndpointOverride.isNotEmpty
      ? _scanEndpointOverride
      : '$baseUrl/api/scan';

  static final String carbonEndpoint = _carbonEndpointOverride.isNotEmpty
      ? _carbonEndpointOverride
      : '$baseUrl/api/carbon/calculate';

  static final String materialsEndpoint = _materialsEndpointOverride.isNotEmpty
      ? _materialsEndpointOverride
      : '$baseUrl/materials';
}
