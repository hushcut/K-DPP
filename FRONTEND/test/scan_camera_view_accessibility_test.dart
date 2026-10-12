import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/widgets/scan_camera_view.dart';

void main() {
  testWidgets('카메라 권한 오류에서 권한 확인 안내를 제공한다', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ScanCameraView(
            cameraController: null,
            selectedImage: null,
            isScanning: false,
            isCameraInitializing: false,
            cameraErrorMessage:
                '카메라 권한이 꺼져 있어요.\n기기 설정에서 K-DPP의 카메라 권한을 허용해 주세요.',
            onRetryCamera: () {},
            onPickFromGallery: () {},
            onTakePicture: () {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('권한 확인 방법'), findsOneWidget);
    expect(find.text('앨범 사진 선택은 계속 사용할 수 있어요.'), findsOneWidget);

    await tester.tap(find.text('권한 확인 방법'));
    await tester.pumpAndSettle();

    expect(find.text('카메라 권한 확인'), findsOneWidget);
    expect(
      find.text('기기 설정에서 K-DPP의 카메라 권한을 허용한 뒤 스캔 화면으로 돌아와 다시 시도해 주세요.'),
      findsOneWidget,
    );
    expect(find.textContaining('앨범 버튼으로 이미 찍어둔 라벨 사진'), findsOneWidget);
  });

  testWidgets('카메라 권한 안내는 스크롤 없이 한 번에 보인다(SM-N986N 실제 배율·글자 크기)', (
    tester,
  ) async {
    // 2026-09-19 폰 확인: 안내 일부가 카메라 틀 아래로 가려져 스크롤해야 했다.
    // 그 폰은 밀도 450(배율 2.8125), 글자 크기 1.1이다(adb로 확인). 스캔 탭에서 카메라 영역
    // 높이는 위 앱바를 뺀 약 694dp(2026-09-18 스크린샷 기준)라 그 높이 안에 띄운다.
    tester.view.physicalSize = const Size(1080, 2316);
    tester.view.devicePixelRatio = 2.8125;
    tester.platformDispatcher.textScaleFactorTestValue = 1.1;
    addTearDown(tester.view.reset);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Align(
            alignment: Alignment.topCenter,
            child: SizedBox(
              height: 694,
              child: ScanCameraView(
                cameraController: null,
                selectedImage: null,
                isScanning: false,
                isCameraInitializing: false,
                cameraErrorMessage:
                    '카메라 권한이 꺼져 있어요.\n기기 설정에서 K-DPP의 카메라 권한을 허용해 주세요.',
                onRetryCamera: () {},
                onPickFromGallery: () {},
                onTakePicture: () {},
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final overlayScroll = tester.state<ScrollableState>(
      find
          .ancestor(
            of: find.text('권한 확인 방법'),
            matching: find.byType(Scrollable),
          )
          .first,
    );
    expect(overlayScroll.position.maxScrollExtent, 0);
    expect(find.text('다시 시도'), findsOneWidget);
    expect(find.text('앨범 사진 선택은 계속 사용할 수 있어요.'), findsOneWidget);
  });

  testWidgets('작은 화면과 큰 글자에서 카메라 화면이 스크롤되고 버튼 이름을 제공한다', (tester) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final semantics = tester.ensureSemantics();

    await tester.pumpWidget(
      MaterialApp(
        home: MediaQuery(
          data: const MediaQueryData(textScaler: TextScaler.linear(1.8)),
          child: Scaffold(
            body: ScanCameraView(
              cameraController: null,
              selectedImage: null,
              isScanning: false,
              isCameraInitializing: false,
              cameraErrorMessage: '카메라 권한이 꺼져 있어요.',
              onRetryCamera: () {},
              onPickFromGallery: () {},
              onTakePicture: () {},
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.bySemanticsLabel('앨범에서 라벨 사진 선택'), findsOneWidget);
    expect(find.bySemanticsLabel('라벨 사진 촬영'), findsOneWidget);
    semantics.dispose();
  });
}
