/// 카카오 로그인 설정입니다(DECISIONS 140·181).
///
/// 네이티브 앱 키는 저장소가 공개라 커밋하지 않습니다. `FRONTEND/kakao.env`(gitignore,
/// 모양은 `kakao.env.example`) 한 파일을 Dart 는 `--dart-define-from-file=kakao.env` 로,
/// iOS 는 `ios/Flutter/*.xcconfig` 의 `#include?` 로, Android 는 `android/app/build.gradle.kts`
/// 가 직접 읽습니다. 키가 없는 빌드(팀원 빌드·CI)는 카카오 로그인 버튼을 숨깁니다.
abstract final class KakaoConfig {
  static const String nativeAppKey = String.fromEnvironment(
    'KAKAO_NATIVE_APP_KEY',
  );

  static bool get isEnabled => nativeAppKey.isNotEmpty;
}
