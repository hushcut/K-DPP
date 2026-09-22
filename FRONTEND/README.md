# K-DPP Flutter Frontend

의류 케어 라벨을 스캔하고 소재, 관리 방법, 건강도와 탄소발자국을 확인하는 Flutter 앱입니다.

## 기본 실행

Android Emulator와 로컬 FastAPI 서버를 사용할 때는 기본 API 주소인
`http://10.0.2.2:8000`이 자동으로 적용됩니다.

iOS Simulator에서는 Mac에서 실행 중인 로컬 서버를
`http://127.0.0.1:8000`으로 자동 연결합니다.

```powershell
flutter pub get
flutter run
```

백엔드는 호스트 PC의 `8000` 포트에서 실행되어 있어야 합니다.

## API 주소 설정

인증, 스캔, 탄소 계산 API가 같은 서버를 사용하면 `API_BASE_URL` 하나만
지정합니다.

```powershell
flutter run --dart-define=API_BASE_URL=http://192.168.0.10:8000
```

실제 Android 기기에서는 `10.0.2.2` 대신 백엔드가 실행 중인 PC의 같은
네트워크 IP 주소를 사용합니다.

실제 iPhone에서도 Mac과 같은 Wi-Fi에 연결한 뒤 Mac의 네트워크 IP를
전달합니다.

```bash
flutter run \
  --dart-define=API_BASE_URL=http://192.168.0.10:8000
```

각 API 주소를 따로 지정해야 할 때는 기존 환경변수도 사용할 수 있습니다.

```powershell
flutter run `
  --dart-define=AUTH_API_BASE_URL=https://api.example.com `
  --dart-define=SCAN_API_ENDPOINT=https://api.example.com/api/scan `
  --dart-define=CARBON_API_ENDPOINT=https://api.example.com/api/carbon/calculate
```

## Android 네트워크 정책

- Debug/Profile 빌드는 로컬 FastAPI 연결을 위해 HTTP 통신을 허용합니다.
- Release 빌드는 평문 HTTP를 허용하지 않으므로 HTTPS 운영 주소를
  `API_BASE_URL`로 전달해야 합니다.
- 카메라 권한은 라벨 스캔 화면에서 사용합니다.

## iOS 실행 준비

iOS 빌드와 시뮬레이터 실행은 macOS와 Xcode가 필요합니다.

```bash
flutter pub get
cd ios
pod install
cd ..
flutter run
```

- iOS 최소 버전은 13.0입니다.
- 카메라, 앨범, 로컬 네트워크 권한 설명이 등록되어 있습니다.
- 로그인 세션은 iOS Keychain에 저장됩니다.
- 화면 방향은 iPhone과 iPad 모두 세로로 고정됩니다.
- 운영 빌드는 평문 HTTP 대신 HTTPS API 주소를 사용해야 합니다.
- Xcode의 Runner 타깃에서 실제 Apple Developer Team과 고유 Bundle
  Identifier를 설정해야 실기기 설치와 배포가 가능합니다.

## 검사

```powershell
flutter analyze
flutter test
```
