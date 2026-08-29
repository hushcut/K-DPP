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

  // 정규화 결과가 비면("/", 공백 등) 기본 주소로 안전하게 되돌아가도록
  // 비어 있는지 검사도 정규화된 값 기준으로 수행한다.
  static final String baseUrl = _resolveBaseUrl();

  static String _resolveBaseUrl() {
    final normalizedOverride = normalizeBaseUrl(_baseUrlOverride);

    return normalizedOverride.isNotEmpty
        ? normalizedOverride
        : defaultBaseUrlFor(defaultTargetPlatform);
  }

  /// 끝에 슬래시가 붙은 주소가 들어와도 `//api/...` 같은 잘못된 경로가
  /// 만들어지지 않도록 앞뒤 공백과 끝 슬래시를 정리한다.
  @visibleForTesting
  static String normalizeBaseUrl(String value) {
    var normalized = value.trim();

    while (normalized.endsWith('/')) {
      normalized = normalized.substring(0, normalized.length - 1);
    }

    return normalized;
  }

  /// Android 에뮬레이터와 그 외 플랫폼에서 사용할 개발용 기본 주소를 반환한다.
  static String defaultBaseUrlFor(TargetPlatform platform) {
    return platform == TargetPlatform.android
        ? 'http://10.0.2.2:8000'
        : 'http://127.0.0.1:8000';
  }

  static final String authBaseUrl = _resolveAuthBaseUrl();

  static String _resolveAuthBaseUrl() {
    final normalizedOverride = normalizeBaseUrl(_authBaseUrlOverride);

    return normalizedOverride.isNotEmpty ? normalizedOverride : baseUrl;
  }

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
