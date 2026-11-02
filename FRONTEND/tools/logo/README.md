# K-DPP 로고 내보내기

확정 디자인은 **D 직립 채움 택 + 초록 잎, a1 흰 타일**입니다. 잎 둘레에 투명 틈,
잎맥, 그림자를 넣지 않습니다. 태그 상단 중앙의 구멍만 투명합니다.

## 실행 환경

- Node.js 22.12 이상, `sharp` **0.35.4** (`package.json`에 고정).
- `sharp`가 포함하는 SVG 렌더러와 PNG 인코더를 사용합니다. Python, Cairo,
  Inkscape, ImageMagick을 따로 설치할 필요가 없습니다.
- 일반 개발 환경에서는 이 폴더에서 `npm install`을 한 번 실행합니다.
  네이티브 바이너리 설치를 위해 npm의 optional dependencies를 끄지 마세요.
- 이 작업은 Codex의 기존 Node 패키지 경로를 `NODE_PATH`로 지정해 실행했습니다.
  그 개인 경로는 스크립트에 하드코딩하지 않았습니다. 일반 환경은 위 설치법을 씁니다.

```sh
cd FRONTEND/tools/logo
npm install
npm run export
npm run verify
```

내보내기는 검증까지 자동 실행합니다. 저장소 루트에서도
`node FRONTEND/tools/logo/export.cjs`로 실행할 수 있습니다.
모든 경로는 실행한 현재 폴더가 아니라 스크립트 위치를 기준으로 계산합니다.

## 원본과 색상

| 역할 | 값 | 사용 |
| --- | --- | --- |
| 브랜드 파랑 | `#4A4EFE` | 택의 면 |
| 눌림 상태 | `#383CDB` | 기존 AppPalette 상태색. 정적 로고에는 사용하지 않음 |
| 잎 | `#63D68B` | 모든 마크·아이콘에 동일하게 사용 |
| 중립 흰색 | `#FFFFFF` | 타일 및 플랫폼 아이콘 배경 |

잎/파란 면의 원색 대비는 **3.0225:1**, 파랑/흰 타일은 **5.5088:1**입니다.
안티앨리어싱된 경계 픽셀까지 이 값을 가진다는 뜻은 아닙니다.
`app_palette.dart`를 로고에 맞춰 변경하지 않습니다.

원본 위치:

- `FRONTEND/assets/images/kdpp_logo_mark.svg`: 투명 마크, 100×100 좌표계.
- `FRONTEND/assets/images/kdpp_logo_tile.svg`: 흰 타일, 반경 27, 마크 배율 76%.

요청한 원본 경로를 유지하되, `pubspec.yaml`에는 PNG 파일만 명시합니다.
따라서 SVG 원본은 앱 번들에 들어가지 않습니다. Flutter는 PNG의 `2.0x/`,
`3.0x/` 변형을 자동으로 묶습니다. 디렉터리 전체를 assets에 선언하지 마세요.
두 SVG의 마크 경로가 다르면 내보내기가 실패합니다.

## 타깃별 규칙 — 서로 혼용하지 말 것

| 타깃 | 라운딩 | 알파 | 배경·아트워크 |
| --- | --- | --- | --- |
| 앱 내 마크 | 없음 | 필요 | 투명 배경 위 마크만 |
| Android 레거시 mipmap | SVG에 포함 | 모서리 알파 0 | 흰 타일 + 마크 |
| Android 어댑티브 전경 | 없음 | 필요 | 108dp 투명 캔버스에 마크만 |
| iOS AppIcon 15장 | 없음 | **RGB, 알파 채널 없음** | 흰색 풀블리드 + 마크 |
| macOS AppIcon 7장 | 필요 | 투명 여백 유지 | 이번 범위 밖, 내보내기 안 함 |

iOS는 시스템 마스크를 적용하므로 SVG 타일의 `rx`만 0으로 바꿔 렌더링합니다.
모든 iOS 파일은 RGB truecolour PNG로 저장합니다. 알파를 평탄화하면서 모서리를
흰색으로 채웁니다. 마케팅 1024px도 동일합니다. iOS용 이미지를 macOS에 복사하면
안 됩니다. macOS는 라운드 + 투명 여백 규칙을 유지해야 하며 별도 요청 후 작업합니다.

PNG는 원본 SVG에서 각 크기로 직접 렌더링합니다. 큰 PNG를 반복 축소하지 않습니다.
팔레트 양자화로 브랜드 원색이 변하는 것을 피하기 위해 truecolour와 PNG 압축 레벨 9를
사용합니다. 검증 예산은 iOS 전체 32KiB, 이번 산출 PNG 전체 150KiB입니다.

## 전체 출력 경로

아래 경로는 모두 `FRONTEND/` 기준입니다.

| 경로 | 크기 |
| --- | --- |
| `assets/images/kdpp_logo.png` | 96px |
| `assets/images/2.0x/kdpp_logo.png` | 192px |
| `assets/images/3.0x/kdpp_logo.png` | 288px |
| `android/app/src/main/res/mipmap-mdpi/ic_launcher.png` | 48px |
| `android/app/src/main/res/mipmap-hdpi/ic_launcher.png` | 72px |
| `android/app/src/main/res/mipmap-xhdpi/ic_launcher.png` | 96px |
| `android/app/src/main/res/mipmap-xxhdpi/ic_launcher.png` | 144px |
| `android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png` | 192px |
| `android/app/src/main/res/mipmap-mdpi/ic_launcher_foreground.png` | 108px |
| `android/app/src/main/res/mipmap-hdpi/ic_launcher_foreground.png` | 162px |
| `android/app/src/main/res/mipmap-xhdpi/ic_launcher_foreground.png` | 216px |
| `android/app/src/main/res/mipmap-xxhdpi/ic_launcher_foreground.png` | 324px |
| `android/app/src/main/res/mipmap-xxxhdpi/ic_launcher_foreground.png` | 432px |
| `android/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml` | 레이어 참조 |
| `ios/Runner/Assets.xcassets/AppIcon.appiconset/*.png` | 기존 15개 파일 |

iOS의 `Contents.json` **19개 엔트리에서 파일명과 크기를 읽고 중복 파일명을 합쳐
15장만 교체**합니다. 현재 해상도는 20, 29, 40, 58, 60, 76, 80, 87, 120, 152,
167, 180, 1024px이며 40/80px 등은 서로 다른 파일명에도 사용됩니다.
`Contents.json`은 쓰지 않습니다. 파일명 수나 크기가 충돌하면 검토하도록 실패합니다.

`ios/Runner/Info.plist`, `android/app/src/main/AndroidManifest.xml`,
`android/app/src/main/res/values-night/`, macOS 아이콘, `LaunchImage.imageset/`는
수정하지 않습니다. iOS 다크/틴티드, Android monochrome, 앱 표시 이름도 별도 범위입니다.

## Android 어댑티브

최소 SDK는 조사 당시 API 24입니다. API 24~25는 `mipmap-anydpi-v26`을 읽지 못하므로
**레거시 5장을 반드시 남깁니다.** API 26 이상은 같은 리소스 이름의 XML을 사용합니다.
어댑티브를 추가하지 않으면 런처가 레거시 흰 타일을 추가 배경판 안에서 작게 표시할 수
있습니다. 실제 마스크 형태는 런처가 정하며 둥근 사각형으로 고정하지 않습니다.

```xml
<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@android:color/white" />
    <foreground android:drawable="@mipmap/ic_launcher_foreground" />
</adaptive-icon>
```

배경은 시스템 흰색을 직접 참조하므로 **`values/colors.xml`은 만들지 않습니다.**
전경에는 흰 타일이나 라운딩을 굽지 않습니다. 108dp 전체 크기의 투명 캔버스 위에
마크만 둡니다. 마크는 중앙 **지름 66dp 안전 원** 안에 들어갑니다.

어댑티브 전경만 100단위 마크를 `translate(19 19) scale(.70)`으로 배치합니다.
레거시/앱 타일의 76% 배율을 그대로 옮기면 아래 어깨·하단 부근이 안전 원을 넘을 수
있으므로, 이 전용 배율을 구분합니다. 검증기는 안티앨리어싱 픽셀을 포함한 모든
불투명 픽셀의 가장 먼 모서리까지 안전 원 안에 있는지 확인합니다.

## Flutter와 폴백

`KdppLogoMark`는 PNG를 `BoxFit.contain`으로 표시하며 추가 ClipRRect를 사용하지 않습니다.
96/84/34 크기 호출부와 승인된 100×100 원본 여백을 유지합니다. 현재 SVG의 택 실제
높이는 박스의 78%로, 타이트하게 잘라 1.37배 확대하는 변경은 하지 않았습니다.

기본 접근성 이름은 `K-DPP`입니다. 로그인·스플래시에서는 바로 옆 제목이 같은 이름을
읽으므로 `semanticLabel: null`로 이미지의 중복 이름을 생략합니다.
로딩 실패 시 `CustomPainter`가 SVG와 동일한 좌표·구멍·잎을 그립니다.
**SVG 경로를 바꾸면 폴백도 함께 바꾸고** 다음 테스트로 두 렌더링을 비교하세요.

```sh
cd FRONTEND
flutter analyze
flutter test
```

`test/kdpp_logo_mark_test.dart`는 중복 접근성 이름과 34/96px 폴백 래스터의
원본 대비 실루엣·잎·투명 구멍을 확인합니다. 그림자나 배경판을 마크에 넣지 않으므로
스플래시 FadeTransition/ScaleTransition에서도 흰 판이 생기지 않습니다.
실기기 애니메이션 확인과 플랫폼 빌드는 별도이며 픽셀/위젯 테스트로 대체했다고
간주하지 않습니다.

## 검증 범위

`verify.cjs`는 다음을 자동 확인합니다.

- 28개 PNG의 크기·알파, iOS PNG IHDR의 RGB 형식, 모서리 흰색/투명 여부
- 불투명 검정 픽셀 부재, 파랑·초록 원색 잔존, SVG 색상 목록
- SVG와 산출물의 일치, 어댑티브 XML의 올바른 레이어 참조
- 전경의 66dp 안전 원, 전경에 흰 타일이 없는지
- 34px 마크·타일과 20/29px iOS 아이콘에 초록 면이 남는지
- 잎 주변에 배경이 비치는 틈이 없는지, PNG 합계 용량

색상/픽셀 검사는 사람의 시각적 식별 판정을 완전히 대신하지 않습니다.
Windows에서는 iOS/macOS 빌드를 검증할 수 없습니다.
로컬 XML 문법은 PowerShell의 `[xml](Get-Content -Raw <파일>)`로도 확인할 수 있습니다.

기존 `FRONTEND/.gitignore`에는 이 작업과 무관한 충돌 마커가 있으므로 여기서 고치지
않습니다. 새 자산이 무시되는지 `git check-ignore -v <경로>`로 확인하세요.
이 README는 일회성 `LOGO_SPEC.md`의 내보내기 규칙·경로·어댑티브 규격을 이관한 문서입니다.

## 이번 교체 검증 결과

- `flutter analyze --no-pub`: 0건.
- `flutter test --no-pub`: 158개 통과 (새 로고 테스트 3개 포함).
- PNG 28장 합계 **55,705 bytes**. 기존 앱 마크 1장(1,382,475 bytes) 대비 약 96% 감소.
- 앱 마크 1x는 **1,335 bytes**, 1x/2x/3x 합계 **7,852 bytes**.
- iOS 15장 합계 **25,364 bytes** (기존 21,327 bytes와 비슷한 규모).
- iOS 20px/29px에도 원색 초록 픽셀이 각각 6/17개 남으며 시각 확인 완료.
- PNG 검증기 통과, PIL에서도 iOS 15장 모두 RGB 확인, SVG/Android XML 문법 확인.
- 실제 테스트 번들에는 PNG 1x/2x/3x만 포함되고 SVG는 제외됨.
- iOS Contents.json 해시 유지, 팔레트·매니페스트·Info.plist·macOS 변경 없음.
- 실기기 hot reload/스플래시 영상, Android·iOS 네이티브 빌드는 실행하지 않음.