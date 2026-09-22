# macOS 개발 환경 세팅 (Apple Silicon)

루트 `README.md`와 `BACKEND/README.md`의 실행 예시는 Windows 기준(`.venv\Scripts\python.exe`)
입니다. 맥에서는 아래를 따르세요. 검증 환경: macOS 27.0 / arm64 / Homebrew.

> 브랜치 주의 — 통합 기준은 **`develop`** 입니다. `main`은 2026-04-05 초기 세팅에서 멈춰
> 있어(커밋 9개) 앱이 동작하지 않습니다. 반드시 `git checkout develop` 후 작업하세요.

---

## 1. 설치 목록과 버전

CI(`.github/workflows/ci.yml`)가 고정한 버전에 맞춥니다. 버전이 어긋나면 로컬은 통과하는데
CI만 깨지는 상황이 생깁니다.

| 도구 | 버전 | 설치 방법 |
| --- | --- | --- |
| Flutter | **3.41.5** (Dart 3.11.3) | 공식 zip (아래) |
| Python | **3.12** | `brew install python@3.12` |
| JDK | **17** | `brew install openjdk@17` |
| Android Studio | 최신 | `brew install --cask android-studio` |
| Android SDK | API 36 / build-tools 36.0.0 | `sdkmanager` (아래) |

`pubspec.yaml`이 Dart `^3.11.3`을 요구합니다. Flutter 3.41.5가 정확히 이 Dart를 탑재합니다.
최신 stable(3.47.x)은 Dart 3.13이라 제약은 만족하지만 CI와 달라집니다.

### JDK는 반드시 17

Android Studio 번들 JDK는 25인데 이 프로젝트는 **Gradle 8.14 + AGP 8.11.1** 조합이라
맞지 않습니다. `android/app/build.gradle.kts`도 `sourceCompatibility = VERSION_17`입니다.
Homebrew **formula**(`openjdk@17`)를 쓰세요. cask(`temurin@17`)는 설치에 sudo가 필요합니다.

---

## 2. Flutter 설치

```bash
mkdir -p ~/development && cd ~/development
curl -L -o flutter.zip \
  https://storage.googleapis.com/flutter_infra_release/releases/stable/macos/flutter_macos_arm64_3.41.5-stable.zip
unzip -q flutter.zip -d ~/development
```

## 3. Android SDK 설치

Android Studio 첫 실행 마법사 대신 CLI로 표준 위치에 넣습니다.

```bash
brew install --cask android-commandlinetools
export JAVA_HOME="/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"
export PATH="$JAVA_HOME/bin:$PATH"
SDK="$HOME/Library/Android/sdk"
yes | sdkmanager --sdk_root="$SDK" --licenses
sdkmanager --sdk_root="$SDK" \
  "cmdline-tools;latest" "platform-tools" "platforms;android-36" \
  "build-tools;36.0.0" "emulator" "system-images;android-36;google_apis;arm64-v8a"
```

## 4. 셸 환경 (`~/.zshrc`)

```bash
export JAVA_HOME="/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"
export PATH="$JAVA_HOME/bin:$PATH"

export ANDROID_HOME="$HOME/Library/Android/sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"

export PATH="$HOME/development/flutter/bin:$PATH"
export PATH="/opt/homebrew/opt/python@3.12/libexec/bin:$PATH"
```

적용 후 Flutter에 경로를 알려 줍니다.

```bash
flutter config --android-sdk "$ANDROID_HOME"
flutter config --jdk-dir "$JAVA_HOME"
```

---

## 5. 백엔드 실행 (맥 경로)

README의 `.venv\Scripts\python.exe`를 `.venv/bin/python`으로 바꾸면 됩니다.

```bash
cd BACKEND
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python init_data.py
.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

확인: <http://127.0.0.1:8000/docs>

테스트:

```bash
cd BACKEND && .venv/bin/python -m pytest
```

DB 초기화는 `.venv/bin/python reset_db.py`.

## 6. 프론트엔드 실행

```bash
cd FRONTEND
flutter pub get
flutter run
```

에뮬레이터는 `http://10.0.2.2:8000`으로 호스트 맥의 백엔드에 자동 연결됩니다.

에뮬레이터 생성(1회):

```bash
avdmanager create avd -n K_DPP_API36 \
  -k "system-images;android-36;google_apis;arm64-v8a" -d pixel_7
emulator -avd K_DPP_API36 &
```

검사:

```bash
cd FRONTEND && flutter analyze && flutter test
```

### 첫 빌드는 5분 이상 걸립니다

첫 `flutter run`(또는 `flutter build apk`)은 Gradle 8.14 배포판(약 700MB)과 AGP·Kotlin
의존성을 내려받고, 추가로 **NDK 28.2.13676358 · build-tools 35 · Android Platform 35 ·
CMake 3.22.1**을 자동 설치합니다. 실측 `assembleDebug` 290초, `~/.gradle` 약 2.3GB.
두 번째부터는 캐시가 있어 훨씬 빠릅니다. 멈춘 것처럼 보여도 기다리세요.

### 실기기(USB) 연결

맥에서도 `adb reverse`는 동일합니다. USB 디버깅을 켜고 케이블을 연결한 뒤:

```bash
adb reverse tcp:8000 tcp:8000
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

---

## 7. 알려진 문제

### `flutter doctor`의 Android 라이선스 경고

```
✗ Android license status unknown.
```

**빌드에는 영향이 없습니다.** `$ANDROID_HOME/licenses/`에 동의 파일이 생성돼 있고 Gradle은
이 파일을 직접 읽습니다. Flutter 3.41.5는 `sdkmanager --licenses` 출력에서
"All SDK package licenses accepted" 문구를 찾는데, 새 cmdline-tools 23.0이 `sdkmanager`를
`android` CLI로 대체하면서 해당 문구 대신 "더 이상 필요 없음" 경고만 출력해 생기는 오탐입니다.

확인 방법:

```bash
ls $ANDROID_HOME/licenses/   # android-sdk-license 등이 있으면 정상
```

실제 빌드 로그에서도 Gradle이 이 파일을 읽어 동의를 확인합니다:

```
Checking the license for package Android SDK Build-Tools 35 in .../Android/sdk/licenses
License for package Android SDK Build-Tools 35 accepted.
```

### Xcode / iOS

Android만 할 거라면 Xcode는 필요 없습니다. `flutter doctor`의 Xcode·CocoaPods 항목
실패는 무시해도 Android 빌드에 영향이 없습니다. iOS는 8장을 보세요.

---

## 8. iOS 빌드 (선택)

iOS 시뮬레이터/실기기 빌드는 **정식 Xcode**가 필요합니다. Command Line Tools만으로는
안 됩니다. Homebrew로는 설치할 수 없고(Apple이 재배포를 허용하지 않음) App Store 또는
developer.apple.com에서 Apple ID로 받아야 합니다.

용량: 다운로드 약 14GB, 설치 후 시뮬레이터 런타임까지 포함해 40GB대를 씁니다.

### 8.1 설치와 1회성 설정

App Store에서 Xcode를 설치한 뒤, **관리자 비밀번호가 필요한 3줄**을 직접 실행합니다.

```bash
sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept
sudo xcodebuild -runFirstLaunch
```

iOS 시뮬레이터 런타임이 없다면 추가로 받습니다(최근 Xcode는 별도 다운로드입니다).

```bash
xcodebuild -downloadPlatform iOS
```

### 8.2 CocoaPods

```bash
brew install cocoapods
```

CocoaPods는 UTF-8 로캘을 요구합니다. `~/.zshrc`에 다음이 없으면 경고가 뜹니다.

```bash
export LANG=en_US.UTF-8
```

### 8.3 빌드

`pod install` 전에 `flutter pub get`이 먼저 돌아야 합니다
(`ios/Flutter/Generated.xcconfig`가 있어야 Podfile이 FLUTTER_ROOT를 읽습니다).

```bash
cd FRONTEND
flutter pub get
cd ios && pod install && cd ..

xcrun simctl list devices available          # 시뮬레이터 UDID 확인
xcrun simctl boot <simulator-udid>
flutter run -d <simulator-udid>
```

> **`flutter build ios --simulator`는 이 조합에서 쓰지 마세요.** 8.6 참고.

Xcode 26부터 독립 `Simulator.app`이 사라지고 `DeviceHub.app`으로 대체됐습니다
(`/Applications/Xcode.app/Contents/Applications/`). GUI 없이 `simctl`과 `flutter run`
만으로 부팅·설치·실행이 모두 됩니다.

### 8.4 iOS 프로젝트 현황

| 항목 | 값 |
| --- | --- |
| 배포 타깃 | iOS 15.0 (8.6 참고 — 13.0에서 올림) |
| Bundle ID | `com.example.kDpp` |
| DEVELOPMENT_TEAM | **미설정** |
| 권한 | 카메라·사진 보관함·로컬 네트워크 (한국어 설명 등록됨) |
| ATS | `NSAllowsLocalNetworking = true` (로컬 백엔드 HTTP 허용) |

시뮬레이터는 위 상태로 바로 됩니다. **실기기**에 올리려면 Xcode에서
`Runner` 타깃 → Signing & Capabilities에서 본인 Apple Developer 팀을 지정하고
Bundle ID를 고유한 값으로 바꿔야 합니다(`com.example.*`는 충돌합니다).

### 8.5 백엔드 주소

iOS 시뮬레이터는 맥의 `127.0.0.1`을 그대로 공유하므로 Android의 `10.0.2.2`와 달리
기본값 그대로 연결됩니다. 실제 iPhone은 맥과 같은 Wi-Fi에 두고 **맥의 호스트 이름**(`.local`)을
넘깁니다. IP를 넣으면 공유기가 IP를 바꿀 때마다 다시 빌드해야 하지만 이름은 그대로입니다.

```bash
scutil --get LocalHostName        # 맥 이름 확인
flutter run --dart-define=API_BASE_URL=http://<맥 이름>.local:8000
```

케이블이 연결돼 있으면 USB 경로로 통신하기도 해서 백엔드 로그에 `169.254.x.x`가 찍힙니다.
정상입니다.

### 8.6 Flutter 3.41.5 × Xcode 27 충돌 2건

두 건 모두 2026-09-20에 실제로 부딪혀 해결한 내용입니다.

**(1) 배포 타깃 13.0 → 15.0** *(수정 완료)*

Xcode 27은 `IPHONEOS_DEPLOYMENT_TARGET` 15.0 미만을 빌드하지 못합니다. Flutter 3.41.5
템플릿이 13.0이라 그대로 두면 다음이 반복됩니다.

```
Target Integrity (Xcode): The iOS Simulator deployment target
'IPHONEOS_DEPLOYMENT_TARGET' is set to 13.0, but the range of supported
deployment target versions is 15.0 to 27.0.x.
```

`Podfile`의 `platform`과 `project.pbxproj` 3곳을 15.0으로 올리는 것만으로는 부족합니다.
Flutter의 `podhelper.rb`(`s.ios.deployment_target = '13.0'`)가 `pod install` 때마다 pod
타깃을 13.0으로 되돌리기 때문에, `Podfile`의 `post_install`에서 다시 덮어써야 합니다.
이 블록이 이미 들어가 있으니 지우지 마세요.

**(2) `flutter build ios --simulator` 사용 금지** *(우회 필요)*

Flutter가 유니버설 바이너리를 검증할 때 `lipo`에 아키텍처를 한 번에 두 개 넘깁니다.

```
lipo <Flutter.framework/Flutter> -verify_arch arm64 x86_64
→ lipo: -verify_arch requires exactly one input file
```

Xcode 27의 `lipo`는 이를 거부합니다. 하나씩 주면 둘 다 통과하므로 **바이너리는 정상이고
Flutter의 검사 코드가 깨진 것**입니다. 실패 메시지는 엉뚱하게 나옵니다.

```
Binary .../Flutter.framework/Flutter does not contain architectures "arm64 x86_64".
lipo -info: Architectures in the fat file: ... are: x86_64 arm64
```

요구한 것과 실제가 같은데 실패한다면 이 버그입니다. 단일 아키텍처로 빌드되는
`flutter run -d <simulator-udid>`를 쓰면 우회됩니다(검증 완료: Xcode build 28.6초,
앱 정상 실행). Flutter를 올리면 해결되지만 CI 고정 버전(3.41.5)과 어긋나므로
그때는 `ci.yml`의 `flutter-version`도 함께 바꿔야 합니다.

### 8.7 실제 iPhone에 올리기

2026-09-20~21, iPhone 16 Pro Max(iOS 27.0)에서 확인한 순서입니다.

**기기 준비** — 아이폰에서 직접 합니다.

1. 케이블 연결 → 잠금 해제 → "이 컴퓨터를 신뢰하시겠습니까?" → 신뢰
2. 설정 → 개인정보 보호 및 보안 → 개발자 모드 켜기 → 재시동
3. `xcrun devicectl list devices`에서 `connected` / `paired`로 보이면 준비 끝

**서명** — Xcode에서 한 번만 합니다. 무료 Apple ID로도 됩니다(인증서 7일 유효).

1. Xcode → Settings(`Cmd+,`) → Accounts → `+` → Apple ID 로그인
2. `Runner.xcworkspace` → TARGETS Runner → Signing & Capabilities
3. Automatically manage signing 체크 → Team 선택
4. Bundle Identifier를 고유 값으로 (`com.example.*`는 거부됩니다)

> Bundle ID와 `DEVELOPMENT_TEAM`은 `project.pbxproj`에 기록됩니다. **개인 값이므로
> 커밋하지 마세요.** 다른 사람의 빌드가 깨집니다.

**첫 빌드에서 만나는 것 3가지**

| 증상 | 원인 | 해결 |
|---|---|---|
| `errSecInternalComponent`, `Failed to codesign` | 새로 만든 서명 키가 "쓸 때마다 물어보기"로 설정됨. 백그라운드 실행에서는 그 창을 띄울 수 없음 | 터미널에서 직접 `flutter run` → 키체인 창에서 **항상 허용** (여러 번 뜸) |
| `Flutter could not access the local network`, `port = 5353` | 디버거 탐색용 mDNS를 macOS가 차단 | 시스템 설정 → 개인정보 보호 및 보안 → **로컬 네트워크** → `flutter run`을 실행한 앱 켜기 (Claude 앱 터미널이면 Claude) |
| 홈 화면에서 앱을 누르면 즉시 종료 | 아래 참고 | `--release`로 설치 |

**디버그 빌드는 홈 화면에서 실행할 수 없습니다.** 디버그 모드는 JIT가 필요한데 iOS는
디버거가 붙어 있지 않으면 JIT를 허용하지 않습니다. 이 엔진 버전은 ProMotion(120Hz)
기기에서 흰 화면이 아니라 크래시로 나타납니다. 크래시 로그 특징:

```
EXC_BAD_ACCESS (SIGSEGV) at 0x0000000000000000
Flutter | -[VSyncClient initWithTaskRunner:callback:]
Flutter | -[FlutterViewController createTouchRateCorrectionVSyncClientIfNeeded]
```

크래시 시점에 `io.flutter.*` 스레드가 하나도 없으면(엔진이 기동조차 못 함) 이 경우입니다.

용도별로 나눠 쓰세요.

```bash
# 코드 고치며 확인 (핫리로드) — 디버거 연결 필요, 홈 화면 실행 불가
flutter run -d <iphone-udid> --dart-define=API_BASE_URL=http://<맥 이름>.local:8000

# 폰에 깔아두고 써보기 — 홈 화면에서 실행 가능
flutter run --release -d <iphone-udid> --dart-define=API_BASE_URL=http://<맥 이름>.local:8000
```

아이폰은 맥과 **같은 Wi-Fi**여야 백엔드에 닿습니다. 맥 이름은 8.5를 보세요.

크래시 로그를 맥으로 가져오려면:

```bash
xcrun devicectl device copy from --device <iphone-udid> \
  --domain-type systemCrashLogs --source / --destination ./crashlogs
```

### OCR

`README.md`에 적힌 대로 Google Cloud Vision 연결이 끊겨 있어 `POST /api/scan`이
`502 OCR_FAILED`를 반환하고 앱은 소재 직접 입력으로 폴백합니다. 맥 환경 문제가 아닙니다.

### `AI/` 모듈

`AI/kdpp_ai_ocr_integrated/requirements.txt`는 `torch`·`torchvision`을 포함해 수 GB입니다.
백엔드 구동과 앱 실행에는 필요 없습니다(CI도 설치하지 않음). OCR 모델을 직접 다룰 때만
별도 venv로 설치하세요.
