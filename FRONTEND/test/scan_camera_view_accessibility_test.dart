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
