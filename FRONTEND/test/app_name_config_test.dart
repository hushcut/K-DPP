import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

// DECISIONS 209: 사용자에게 보이는 앱 이름은 플랫폼 설정 파일마다 따로 적혀 있다. iOS 홈 화면
// 이름만 'K-DPP' 이고 나머지가 Flutter 기본값 'k_dpp' 로 남아, 카카오 로그인 확인 창(iOS
// CFBundleName)과 Android 홈 화면에 'k_dpp' 가 보였다.
void main() {
  test('iOS 홈 화면 이름·번들 이름과 Android 기본 앱 이름이 모두 K-DPP 다', () {
    final plist = File('ios/Runner/Info.plist').readAsStringSync();
    final gradle = File('android/app/build.gradle.kts').readAsStringSync();
    final manifest = File(
      'android/app/src/main/AndroidManifest.xml',
    ).readAsStringSync();

    String? plistValue(String key) => RegExp(
      '<key>$key</key>\\s*<string>([^<]*)</string>',
    ).firstMatch(plist)?.group(1);

    expect(plistValue('CFBundleDisplayName'), 'K-DPP');
    expect(plistValue('CFBundleName'), 'K-DPP');

    // Gradle 속성 kdppAppLabel 을 주지 않았을 때의 값이 매니페스트 android:label 로 들어간다(DECISIONS 42).
    expect(manifest, contains(r'android:label="${kdppAppLabel}"'));
    expect(
      RegExp(
        r'manifestPlaceholders\["kdppAppLabel"\][^\n]*\?: "([^"]*)"',
      ).firstMatch(gradle)?.group(1),
      'K-DPP',
    );
  });
}
