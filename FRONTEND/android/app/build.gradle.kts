plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.example.k_dpp"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        // 다른 PC 서명으로 만든 앱을 폰의 기존 앱 옆에 나란히 설치하려면 접미사와 이름을 준다(기본은 없음).
        // 예: ORG_GRADLE_PROJECT_kdppAppIdSuffix=.mac ORG_GRADLE_PROJECT_kdppAppLabel="K-DPP 맥" flutter build apk --release
        val kdppAppIdSuffix = (project.findProperty("kdppAppIdSuffix") as String?) ?: ""
        applicationId = "com.example.k_dpp$kdppAppIdSuffix"
        manifestPlaceholders["kdppAppLabel"] = (project.findProperty("kdppAppLabel") as String?) ?: "k_dpp"
        // 카카오 네이티브 앱 키는 커밋하지 않고 FRONTEND/kakao.env(gitignore)에서 읽는다(DECISIONS 181).
        // 파일이 없으면 none 으로 둬 로그인 복귀 스킴이 'kakao' 하나만 남지 않게 한다.
        manifestPlaceholders["kakaoNativeAppKey"] = readKakaoNativeAppKey() ?: "none"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

flutter {
    source = "../.."
}

/** FRONTEND/kakao.env 의 KAKAO_NATIVE_APP_KEY 값(Dart 의 --dart-define-from-file 과 같은 파일). */
fun readKakaoNativeAppKey(): String? {
    val envFile = rootProject.file("../kakao.env")
    if (!envFile.isFile) return null

    return envFile.readLines()
        .map { it.trim() }
        .firstOrNull { it.startsWith("KAKAO_NATIVE_APP_KEY=") }
        ?.substringAfter("=")
        ?.trim()
        ?.takeIf { it.isNotEmpty() }
}
