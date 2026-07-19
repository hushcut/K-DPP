import 'package:flutter/foundation.dart';

/// 빌드 시 전달된 `--dart-define` 값을 우선 사용해 API 주소를 한곳에서 관리한다.
/// 별도 설정이 없으면 Android에는 에뮬레이터용 주소를, 그 외 플랫폼에는 loopback 주소를 선택한다.
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

  /// Android 에뮬레이터와 그 외 플랫폼에서 사용할 개발용 기본 주소를 반환한다.
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
